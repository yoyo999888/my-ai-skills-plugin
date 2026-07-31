#!/usr/bin/env python3
"""reasonix ACP 执行者池：一个进程里并发跑 N 个隔离会话。

用法：
    acp_pool.py --cwd /path/to/repo "任务A" "任务B" "任务C"
    acp_pool.py --cwd /path/to/repo --tasks tasks.json
    echo '[{"prompt":"..."},{"prompt":"...","resume":"/path/x.jsonl"}]' | acp_pool.py --cwd . --tasks -

输出：stdout 一行 JSON 数组，每项含 sessionId / transcriptPath / stopReason / text。
      transcriptPath 之后可用 `reasonix run -p --resume <path> "追问"` 继续（已验证互通）。
进度：写到 stderr，不污染 stdout。
"""
import argparse, json, pathlib, subprocess, sys, threading, time

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", required=True, help="执行者的工作目录（绝对路径）")
    ap.add_argument("--model", help="覆盖默认模型")
    ap.add_argument("--tasks", help="任务 JSON 文件，'-' 表示读 stdin；每项 {prompt, resume?}")
    ap.add_argument("--timeout", type=float, default=1800, help="总超时秒数")
    ap.add_argument("--emit", help="每完成一个执行者就往该文件追加一行 JSON（用于外部实时监听）")
    ap.add_argument("--trace", help="记录所有工具调用（含 read_file/ask 等不触发审批的只读工具）到该 JSONL")
    ap.add_argument("--no-guard", action="store_true",
                    help="不追加无人值守守则（默认追加 scripts/guard.md，防止代理编造「用户已确认」）")
    ap.add_argument("--guard-file", help="用自定义守则文件替换内置 guard.md")
    ap.add_argument("prompts", nargs="*", help="直接给的任务文本")
    a = ap.parse_args()

    if a.tasks:
        raw = sys.stdin.read() if a.tasks == "-" else open(a.tasks).read()
        tasks = json.loads(raw)
        tasks = [t if isinstance(t, dict) else {"prompt": t} for t in tasks]
    else:
        tasks = [{"prompt": p} for p in a.prompts]
    if not tasks:
        sys.exit("没有任务")

    # 无人值守守则：默认给每个任务追加，调度者不必手抄
    if not a.no_guard:
        gf = pathlib.Path(a.guard_file) if a.guard_file else pathlib.Path(__file__).parent / "guard.md"
        if gf.exists():
            guard = gf.read_text().strip()
            for t in tasks:
                t["prompt"] = t["prompt"].rstrip() + "\n\n---\n\n" + guard
        elif a.guard_file:
            sys.exit(f"守则文件不存在：{gf}")

    # F3：同一会话被多个任务 resume 是调度配置错误 —— 投递前直接拒绝，避免运行期串台
    seen_resume = {}
    for i, t in enumerate(tasks):
        r = t.get("resume")
        if r:
            if r in seen_resume:
                sys.exit(f"任务 #{seen_resume[r]} 与 #{i} 重复 resume 同一会话 {r!r}；"
                         f"同一会话只能被一个任务续接，请去重后重试")
            seen_resume[r] = i

    cmd = ["reasonix", "acp"] + (["--model", a.model] if a.model else [])
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, bufsize=1, cwd=a.cwd)

    wlock = threading.Lock()
    def send(m):
        with wlock:
            p.stdin.write(json.dumps(m) + "\n")
            p.stdin.flush()

    t0 = time.time()
    def log(s):
        print(f"[{time.time()-t0:6.1f}s] {s}", file=sys.stderr, flush=True)

    n = len(tasks)
    results = [None] * n
    sid_of = {}          # index -> sessionId
    idx_of = {}          # sessionId -> index
    text = [[] for _ in range(n)]
    live = [False] * n
    finished = threading.Event()
    done = 0

    def finish(i, entry):
        """幂等地记录任务 i 的结果（完成或失败都从这里收口）。仅 reader 线程调用。"""
        nonlocal done
        if results[i] is not None:
            return
        results[i] = entry
        done += 1
        if a.emit:
            try:
                with open(a.emit, "a") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    fh.flush()
            except Exception as e:
                log(f"emit 写入失败：{e}")
        if done == n:
            finished.set()

    def fail(i, error):
        """F2/F3 的任务级失败：立即收口，不拖到全局超时。"""
        msg = error.get("message") if isinstance(error, dict) else str(error)
        log(f"#{i} 失败：{msg}")
        finish(i, {"index": i, "sessionId": sid_of.get(i), "transcriptPath": None,
                   "stopReason": "error", "error": error,
                   "text": "".join(text[i]).strip()})

    send({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
        "protocolVersion": 1,
        "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}}}})

    def _handle(m, line):
        """处理单条 JSON-RPC 消息。任何异常都被 reader() 的边界捕获，不会杀死整个池（F1）。"""
        mid, meth = m.get("id"), m.get("method")

        # 代理反向请求：权限审批 —— 自动放行，否则会永远挂住
        if meth == "session/request_permission":
            opts = m.get("params", {}).get("options", [])
            pick = next((o for o in opts if "allow" in str(o.get("kind", "")).lower()),
                        opts[0] if opts else None)
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "outcome": {"outcome": "selected", "optionId": pick.get("optionId")} if pick
                           else {"outcome": "cancelled"}}})
            if a.trace:
                with open(a.trace, "a") as fh:
                    fh.write(json.dumps({"kind": "permission_request",
                                         "params": m.get("params")}, ensure_ascii=False) + "\n")
            log(f"auto-approve: {m['params'].get('toolCall', {}).get('title', '?')}")
            return
        if meth and mid is not None and meth.startswith(("fs/", "terminal/")):
            send({"jsonrpc": "2.0", "id": mid,
                  "error": {"code": -32601, "message": "capability not offered"}})
            return

        # session/new、session/load 的响应：id 用 1000+index
        if isinstance(mid, int) and 1000 <= mid < 2000:
            i = mid - 1000
            # F2：error 响应、或 result 缺失/非对象（如 result:null）→ 任务立即失败，
            #     不再静默丢弃或拿 resume 顶替后继续（那两种都会拖到全局超时）。
            if "error" in m or not isinstance(m.get("result"), dict):
                fail(i, m.get("error") or {"message": f"会话未就绪（响应缺少 result）：{str(m)[:200]}"})
                return
            # session/load 的响应不回 sessionId（是我们自己给的），要 fallback
            sid = m["result"].get("sessionId") or tasks[i].get("resume")
            if not sid:
                fail(i, {"message": f"拿不到 sessionId：{str(m)[:200]}"})
                return
            # F3 运行期防御：服务端若返回重复会话 id，后到任务立即失败而非覆盖 idx_of
            if sid in idx_of:
                fail(i, {"message": f"会话 {sid[:12]}… 已被任务 #{idx_of[sid]} 占用，禁止多任务复用同一会话"})
                return
            sid_of[i], idx_of[sid] = sid, i
            live[i] = True          # 之后的 chunk 才算数（load 会重放历史）
            log(f"#{i} session {sid[:8]} 就绪")
            send({"jsonrpc": "2.0", "id": 2000 + i, "method": "session/prompt", "params": {
                "sessionId": sid,
                "prompt": [{"type": "text", "text": tasks[i]["prompt"]}]}})
            return

        if meth == "session/update":
            sid = m["params"].get("sessionId")
            i = idx_of.get(sid)
            u = m["params"].get("update", {})
            kind = u.get("sessionUpdate")
            if i is not None and live[i] and kind == "agent_message_chunk":
                text[i].append(u.get("content", {}).get("text", ""))
            elif a.trace and kind in ("tool_call", "tool_call_update"):
                rec = {"index": i, "kind": kind, "status": u.get("status"),
                       "title": u.get("title"), "toolName": u.get("toolName") or u.get("kind"),
                       "rawInput": u.get("rawInput"), "toolCallId": u.get("toolCallId")}
                with open(a.trace, "a") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n"); fh.flush()
                if kind == "tool_call":
                    nm = rec["toolName"] or rec["title"] or "?"
                    log(f"#{i} tool: {str(nm)[:60]}")
            return

        # session/prompt 的响应：id 用 2000+index
        if isinstance(mid, int) and 2000 <= mid < 3000:
            i = mid - 2000
            r = m.get("result") or {}
            finish(i, {"index": i, "sessionId": sid_of.get(i),
                       "transcriptPath": r.get("transcriptPath"),
                       "stopReason": r.get("stopReason") or "error",
                       "error": m.get("error"),
                       "text": "".join(text[i]).strip()})
            log(f"#{i} 完成 ({r.get('stopReason')}) {done}/{n}")

    def reader():
        for line in p.stdout:
            try:
                m = json.loads(line)
            except Exception:
                continue
            try:
                # F1：单条消息处理异常只跳过该消息并记日志，不让 reader 线程死掉
                _handle(m, line)
            except Exception as e:
                log(f"reader 跳过异常消息（{type(e).__name__}: {e}）：{str(line)[:200]}")

        # 子进程 stdout 关闭（reasonix 提前退出/崩溃，或全部完成后正常退出）。
        # 把所有未收口任务标记为失败并借 finish() 置位 finished，让主线程立即结束等待，
        # 不再拖到全局 --timeout。仍在 reader 线程内，不引入跨线程写。
        rc = p.poll()
        log(f"reasonix acp 子进程输出已关闭（returncode={rc}）")
        for i in range(n):
            if results[i] is None:
                fail(i, {"code": "child_exited",
                         "message": f"reasonix 子进程提前退出（returncode={rc}），任务未收到完成响应",
                         "returncode": rc})

    threading.Thread(target=reader, daemon=True).start()

    for i, t in enumerate(tasks):
        params = {"cwd": a.cwd, "mcpServers": []}
        if t.get("resume"):
            send({"jsonrpc": "2.0", "id": 1000 + i, "method": "session/load",
                  "params": dict(params, sessionId=t["resume"])})
        else:
            send({"jsonrpc": "2.0", "id": 1000 + i, "method": "session/new", "params": params})
    log(f"已投递 {n} 个任务")

    ok = finished.wait(a.timeout)
    if not ok:
        log("超时，返回已完成部分")
    try:
        p.stdin.close()
    except Exception:
        pass
    p.terminate()
    print(json.dumps([r for r in results if r], ensure_ascii=False, indent=2))
    # 全部在超时内完成且无任何任务失败才算成功；有失败任务时调用方应能感知
    failed = any((r or {}).get("error") for r in results)
    sys.exit(0 if (ok and not failed) else 1)

if __name__ == "__main__":
    main()
