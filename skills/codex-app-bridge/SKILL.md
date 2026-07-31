---
name: codex-app-bridge
description: 从 Claude Code 侧连上 Codex 桌面 app 的 app-server，向已有 thread 续聊、派发新任务，并通过异步回调（后台进程 + 结果 JSON，或让 codex 自己写哨兵文件）拿回结果而不空等。当用户给出 codex://threads/<id>、要求"和这个 codex 任务沟通"、"给 codex app 派活"、"让 codex 做完后回调/通知"时使用。触发词：codex app、codex desktop、codex://threads、app-server、和 codex 沟通、给 codex 派任务、resume codex thread、codex 异步回调。
---

# codex-app-bridge

Codex 桌面 app 背后是一个常驻的 **app-server**（JSON-RPC daemon）。Claude Code 侧可以直接连上去，对**同一条 thread** 续聊或新开 thread 派任务——即 app 界面里的会话和你在 Claude 里发的消息落在同一条历史上。

依赖已安装的 `openai-codex` 插件（复用它的 `scripts/lib/codex.mjs`）。本技能自带 `scripts/codex-app.mjs` 作为唯一入口，它会自动定位插件路径，不写死版本号。

## 何时使用

- 用户丢来 `codex://threads/<uuid>`，要求和那条任务沟通、追问、续派工作。
- 要把一段活派给 Codex（GPT-5.x）跑，且不想同步阻塞在那里等。
- 要枚举/回看 codex app 的会话历史。

## 步骤

### 1. 定位 thread 与它的 cwd

`codex://threads/<id>` 里的 `<id>` 就是 thread id。它的落盘 rollout 在：

```bash
ls ~/.codex/sessions/*/*/*/rollout-*-<threadId>.jsonl
```

**先离线读这个 jsonl 拿上下文**（`session_meta` 里有 `cwd`、`model`、`originator`），比连上去问它便宜得多：

```bash
python3 -c "
import json,sys
for line in open(sys.argv[1]):
    d=json.loads(line); t=d.get('type'); p=d.get('payload',{})
    if t=='session_meta': print('cwd', p.get('cwd'), '| model_provider', p.get('model_provider'))
    if t=='event_msg' and p.get('type') in ('user_message','agent_message','task_complete'):
        print(p['type'],'|',(p.get('message') or p.get('last_agent_message') or '')[:400])
" <rollout.jsonl>
```

也可以在线枚举：`node scripts/codex-app.mjs list <cwd>`。

### 2. 同步续聊（短问答）

```bash
node scripts/codex-app.mjs send <threadId> <cwd> read-only - "你的消息"
```

stdout 是一个 JSON，`finalMessage` 就是 codex 的回复。

### 3. 异步派发（默认做法，长任务必用）

用后台 Bash 跑同一条命令，把结果写进 JSON，进程退出时 harness 会通知你：

```bash
node scripts/codex-app.mjs send <threadId> <cwd> read-only /tmp/cb/task1.json "任务描述" 2>/dev/null
```

以 `run_in_background: true` 调用。收到完成通知后读 `/tmp/cb/task1.json` 拿 `finalMessage`。实测一个 du 统计任务约 30 秒。

**要 codex 写盘**就不能续聊，必须新开 thread：

```bash
node scripts/codex-app.mjs new <cwd> workspace-write /tmp/cb/task2.json "任务描述"
```

### 4. 让 codex 自己回调（Claude 侧不挂进程）

只在 `new` + `workspace-write` 下可行。在 prompt 里明确要求它把结果写成文件，且**路径必须在 workspace root 内**：

```
完成后必须把结果写入 <cwd>/callback.json，格式 {"done":true,"summary":"..."}。写文件是本次任务的必要交付。
```

然后 Claude 侧 detach 掉进程（`nohup ... &`），用一个后台 `until [ -s <file> ]; do sleep 2; done` 等文件落地即可。

## 实测坑（2026-07-31 验证）

1. **broker 单飞**：一个 turn 在跑时，任何其它 app-server 请求会直接报 `-32001 Shared Codex broker is busy.`。派了异步任务就别同时 `list`——串行排队。
2. **resume 已有 thread 一律 read-only**。`send` 传 `workspace-write` 或 `danger-full-access` 都**静默无效**，codex 会回「只读沙箱拒绝写入」。要写盘只能 `new`。
3. `danger-full-access` 不是合法值，会静默退回 read-only。合法值只有 `read-only` / `workspace-write`。
4. **写入范围受 workspace root 限制**：`/tmp` 下的路径写不进去，回调文件要放 `cwd` 所在的 workspace 内。
5. app-server 是**不随 app 重启的常驻 daemon**；认证/配置改动要 `pkill -f "codex.*app-server"` 才生效（且 Claude 侧插件脚本会把它拉回来）。
6. `approvalPolicy` 被固定成 `never`，任务里不要设计需要人工批准的步骤。

## 注意

- 续聊会真实写进用户 app 里的那条会话历史，用户在界面上看得到。派发前确认这是用户想要的。
- 破坏性操作（删文件、改仓库）不要直接甩给 codex 跑，先让它只做诊断并回报。
