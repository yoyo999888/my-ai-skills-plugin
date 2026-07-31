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
import argparse, json, subprocess, sys, threading, time

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", required=True, help="执行者的工作目录（绝对路径）")
    ap.add_argument("--model", help="覆盖默认模型")
    ap.add_argument("--tasks", help="任务 JSON 文件，'-' 表示读 stdin；每项 {prompt, resume?}")
    ap.add_argument("--timeout", type=float, default=1800, help="总超时秒数")
    ap.add_argument("--emit", help="每完成一个执行者就往该文件追加一行 JSON（用于外部实时监听）")
    ap.add_argument("--trace", help="记录所有工具调用（含 read_file/ask 等不触发审批的只读工具）到该 JSONL")
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

    send({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
        "protocolVersion": 1,
        "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}}}})

    def reader():
        nonlocal done
        for line in p.stdout:
            try:
                m = json.loads(line)
            except Exception:
                continue
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
                continue
            if meth and mid is not None and meth.startswith(("fs/", "terminal/")):
                send({"jsonrpc": "2.0", "id": mid,
                      "error": {"code": -32601, "message": "capability not offered"}})
                continue

            # session/new 的响应：id 用 1000+index
            if isinstance(mid, int) and 1000 <= mid < 2000 and "result" in m:
                i = mid - 1000
                # session/load 的响应不回 sessionId（是我们自己给的），要 fallback
                sid = (m["result"] or {}).get("sessionId") or tasks[i].get("resume")
                if not sid:
                    log(f"#{i} 拿不到 sessionId，跳过：{m}")
                    continue
                sid_of[i], idx_of[sid] = sid, i
                live[i] = True          # 之后的 chunk 才算数（load 会重放历史）
                log(f"#{i} session {sid[:8]} 就绪")
                send({"jsonrpc": "2.0", "id": 2000 + i, "method": "session/prompt", "params": {
                    "sessionId": sid,
                    "prompt": [{"type": "text", "text": tasks[i]["prompt"]}]}})

            elif meth == "session/update":
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

            # session/prompt 的响应：id 用 2000+index
            elif isinstance(mid, int) and 2000 <= mid < 3000:
                i = mid - 2000
                r = m.get("result") or {}
                results[i] = {"index": i, "sessionId": sid_of.get(i),
                              "transcriptPath": r.get("transcriptPath"),
                              "stopReason": r.get("stopReason") or "error",
                              "error": m.get("error"),
                              "text": "".join(text[i]).strip()}
                done += 1
                if a.emit:
                    with open(a.emit, "a") as fh:
                        fh.write(json.dumps(results[i], ensure_ascii=False) + "\n")
                        fh.flush()
                log(f"#{i} 完成 ({r.get('stopReason')}) {done}/{n}")
                if done == n:
                    finished.set()
                    return

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
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
