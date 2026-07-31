---
name: reasonix-executor
description: 把 reasonix CLI 当成有状态的执行代理来调度——具名执行者可随时追问并记住上下文，或一次并发拉起多个隔离执行者。当用户想把实现/调研/批量任务外包给 reasonix、要多个 agent 并行干活、或要一个能持续推进的长期执行者时使用。触发词：reasonix、执行代理、执行者池、并发 agent、外包给 reasonix、acp、reasonix serve。
---

# reasonix-executor

把 `reasonix` 当**有状态的执行代理**调度。两个脚本封好了全部细节，调度者只给命令：

| 需求 | 命令 |
|---|---|
| 一次性问一句 | `reasonix -p "..."` |
| **一个执行者，持续推进** | `scripts/rx`（模式 A） |
| **一批任务并发** | `scripts/acp_pool.py`（模式 B） |
| 要给人看界面 / 跨机访问 | `reasonix serve`，见 `references/interfaces.md` |

两种模式**共用同一份会话文件、可互相接管**：`acp_pool` 产出的 sessionId 能被 `rx adopt` 收编继续推进。

两个脚本都**默认注入无人值守守则**（`scripts/guard.md`），不必在每个任务里手抄，用 `--no-guard` 关掉。守则为什么必须存在见文末。

## 何时使用

- 要把编码/调研/审查任务外包给 reasonix 执行。
- 需要多个执行者并行处理互不相干的子任务。
- 需要一个记得上下文、能被反复追问推进的长期执行者。

## 模式 A：具名执行者，持续推进

```bash
rx spawn api-work "把 handlers/ 里的重复校验抽成中间件" --dir /path/to/repo
rx ask   api-work "补上单元测试"          # 接着上次的上下文
rx ls                                     # 看所有执行者：轮次、累计成本、session_id
rx show  api-work                         # 看完整登记信息
```

**session_id 始终可见、且可直接当句柄用**——名字只是别名，登记文件丢了 session_id 照样能接：

```bash
rx ask 20260731-095631.635102000-deepseek-v4-flash "继续"   # 裸 session id
rx ask ~/.reasonix/sessions/7cc8787f-....jsonl "继续"        # 会话文件路径
rx adopt frompool 7cc8787f-263c-4795-9d17-e878bda9d3fe --dir /path/to/repo  # 收编已有会话
```

每轮都会把 `session_id` 和会话路径打到 stderr，成本累计写进登记。
登记默认在 `~/.reasonix-crew/`（`RX_HOME` 可改）；`rx rm` 只删登记，不删会话文件。

参数：`--dir` 工作目录、`--model` 换模型、`--perm` 权限模式（默认 `auto`，否则非交互下工具调用会被静默挡住）。

## 模式 B：一批执行者并发

一个 reasonix 进程里开 N 个隔离会话并发跑，输出 JSON 数组：

```bash
python3 scripts/acp_pool.py --cwd /path/to/repo "任务A" "任务B" "任务C"

# 从文件/stdin 投递，可混合「新建」和「接管已有会话」
echo '[{"prompt":"新任务"},{"prompt":"追问","resume":"<sessionId>"}]' \
  | python3 scripts/acp_pool.py --cwd /path/to/repo --tasks -
```

输出（stdout 纯 JSON，进度走 stderr）：

```json
[{"index":0,"sessionId":"6c68be10-...","transcriptPath":"/Users/me/.reasonix/sessions/6c68be10-....jsonl",
  "stopReason":"end_turn","text":"..."}]
```

参数：

- `--emit results.jsonl` — **完成一个就追加一行**，别等整批。外部监听这个文件拿逐任务进度
- `--trace trace.jsonl` — 记录**全部**工具调用。只读工具（`read_file`、`ask`）不触发审批，光看审批流看不见，排查必开
- `--model` 换模型、`--timeout` 总超时（默认 1800s）、`--no-guard` / `--guard-file` 控制守则

拿到 `sessionId` 后用 `rx adopt` 收编，就能转成具名执行者继续追问。

## 为什么必须有那份守则

A/B 实测（同模型同任务，唯一变量是 `guard.md`）：

| | 开头指出需求冲突 | 幻觉出「用户已确认」 | 写明服从哪条+理由 |
|---|---|---|---|
| 裸 spec | 2/3 | **3/3 全中** | 0/3 |
| 注入守则 | **3/3** | **0/3** | **3/3** |

真正的失效模式**不是**"看不出矛盾"——裸 spec 下它多半看得出来，但看出来之后会**调 `ask` 工具、拿不到答复、然后凭空编一句「用户已确认：XXX」把矛盾抹平**再往下写。无人值守时根本没有用户。这个失效稳定复现，不开 `--trace` 完全看不见。

## 注意（都是实测踩出来的）

- **执行者的工作目录里不许放任何日志、判分器、参照文件**。`--cwd` 是它们的共享沙盒，它们会读。实测出现过一个执行者读到 `progress.log` 里另一个执行者的测试断言，据此反推出"正确答案"。`--emit` / `--trace` / stderr 一律指向 `--cwd` 之外。
- **要做「改造前后行为一致」类任务，先把原件复制一份到工作目录外**，否则执行者原地改完就没有对拍基准了。
- **`--resume` 只吃全路径**，裸 session id 会 `no such file or directory`（`rx` 已代为定位）。
- **别自己拼项目目录 slug**。`--dir` 传的路径和落盘目录名可能对不上（符号链接会让 `/ssd/workspace` 的会话落进 `-Users-kk-workspace/`），一律 `find ~/.reasonix/projects -name "$id.jsonl"`。
- **只有 `--output-format json` 带 `session_id`**；`-p` 纯文本和 `--events-jsonl` 都没有。
- **别用「取 mtime 最新的 jsonl」猜会话**，并发时必然抢错。
- **一个 serve 进程只有一个活跃会话**（`/new` 会把当前会话换掉，跑起来时连切换都被禁）。要 N 个并发执行者用模式 B。

接口细节（serve 完整 HTTP API、ACP 能力与事件、会话文件布局）见 `references/interfaces.md`。
