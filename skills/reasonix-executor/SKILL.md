---
name: reasonix-executor
description: 把 reasonix CLI 当成有状态的执行代理来调度——单个执行者跨调用续接会话、一次并发拉起多个隔离执行者、需要人看时开网页面板。当用户想把实现/调研/批量任务外包给 reasonix、要多个 agent 并行干活、或要一个能随时追问且记得上下文的执行者时使用。触发词：reasonix、执行代理、执行者池、并发 agent、外包给 reasonix、acp、reasonix serve。
---

# reasonix-executor

把 `reasonix` 当**有状态的执行代理**调度：会话状态落在磁盘上，可以随时追问；多个执行者能真并发，互不阻塞。

三种接法各有适用面，**别混用**：

| 需求 | 用法 |
|---|---|
| 一次性问一句 | `reasonix -p "..."` |
| 单个执行者，跨多次调用记住上下文 | `run --resume`（本文「模式 A」） |
| 一批任务并发跑，各自隔离 | `scripts/acp_pool.py`（本文「模式 B」） |
| 要给人看界面 / 跨机访问 | `reasonix serve`（见 `references/interfaces.md`） |

模式 A 和 B **共用同一份会话文件，可互相接管**：B 产出的 `transcriptPath` 能直接喂给 A 的 `--resume`。

## 何时使用

- 用户要把编码/调研/审查任务外包给 reasonix 执行，而不是自己动手。
- 需要多个执行者并行处理互不相干的子任务。
- 需要一个"记得上下文、可以随时追问"的长期执行者。

## 模式 A：单执行者，跨调用有状态

第一轮**不需要预先知道 session id**——问完它告诉你：

```bash
id=$(reasonix run --dir /path/to/repo --output-format json "第一轮任务" | jq -r .session_id)
sess=$(find ~/.reasonix/projects -name "$id.jsonl")     # 定位落盘文件
reasonix run -p --dir /path/to/repo --resume "$sess" "追问"   # 之后每轮都用这个
```

把 `$sess` 记下来（写进笔记或临时文件），后续每次追问复用。

要它真能动手干活，加 `--permission-mode`（默认 `ask` 在非交互下会挡住工具调用）：

```bash
reasonix run -p --dir "$repo" --resume "$sess" --permission-mode auto "改代码的任务"
```

## 模式 B：一批执行者并发

`scripts/acp_pool.py` 在**一个 reasonix 进程里**开 N 个隔离会话并发跑，输出 JSON 数组。

```bash
# 新建 3 个执行者并发干活
python3 scripts/acp_pool.py --cwd /path/to/repo "任务A" "任务B" "任务C"

# 从文件/stdin 投递，可混合「新建」和「接管已有会话」
echo '[{"prompt":"新任务"},{"prompt":"追问","resume":"<sessionId>"}]' \
  | python3 scripts/acp_pool.py --cwd /path/to/repo --tasks -
```

输出（stdout 是纯 JSON，进度写在 stderr）：

```json
[{"index":0,"sessionId":"6c68be10-...","transcriptPath":"/Users/me/.reasonix/sessions/6c68be10-....jsonl",
  "stopReason":"end_turn","text":"..."}]
```

拿到 `transcriptPath` 后，之后可以换回模式 A 单独追问某一个执行者。

参数：`--model` 换模型、`--timeout` 总超时（默认 1800s）。脚本会自动放行工具审批请求，否则会永久挂起。

## 注意（都是实测踩出来的）

- **`--resume` 只吃全路径**，给裸 session id 会 `no such file or directory`。
- **别自己拼项目目录 slug**。`--dir` 传的路径和落盘目录名可能对不上（符号链接会让 `/ssd/workspace` 的会话落进 `-Users-kk-workspace/`），一律 `find ~/.reasonix/projects -name "$id.jsonl"` 定位。
- **`--output-format json` 才有 `session_id`**；`-p` 纯文本和 `--events-jsonl` 都没有。
- **别用「取 mtime 最新的 jsonl」猜 session**，并发起多个执行者时必然抢错。
- **一个 serve 进程只有一个活跃会话**（`/status` 单份 history，`/new` 会把当前会话换掉，跑起来时连切换都被禁）。要 N 个并发执行者只能起 N 个进程，所以并发场景优先用模式 B。
- **非交互下工具审批会静默卡住**：模式 A 用 `--permission-mode auto`，serve 用 `POST /tool-approval-mode {"mode":"auto"}`，模式 B 脚本已内建自动放行。

接口细节（serve 的完整 HTTP API、ACP 握手能力、会话文件布局）见 `references/interfaces.md`。
