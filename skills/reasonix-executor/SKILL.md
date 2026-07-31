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

参数：

- `--model` 换模型、`--timeout` 总超时（默认 1800s）
- `--emit results.jsonl`：**完成一个就追加一行**，别等整批。外部可以直接监听这个文件拿逐任务进度
- `--trace trace.jsonl`：记录**全部**工具调用。只读工具（`read_file`、`ask`）不触发审批，光看审批流是看不见的，排查时必开

脚本会自动放行工具审批请求，否则会永久挂起。

## 委派提示词模板（必加，不是可选项）

无人值守委派时，**每个任务的 prompt 末尾都要追加下面这段**。这不是锦上添花——A/B 实测（同模型同任务，唯一变量是这段话）：

| | 开头指出需求冲突 | 幻觉出「用户已确认」 | 写明服从哪条+理由 |
|---|---|---|---|
| 裸 spec | 2/3 | **3/3 全中** | 0/3 |
| 加下面这段 | **3/3** | **0/3** | **3/3** |

```
在动手写代码之前，先把需求本身审一遍：如果存在互相矛盾、无法同时满足的条款——
包括只在语义层面冲突、不会被任何断言撞破的那种——不要自行折中和稀泥，也不要默默
挑一条实现。请先在回答开头用「需求冲突」小节列出：冲突的是哪几条、给出一个具体
反例说明为什么无法同时成立、你决定服从哪一条及理由。然后再实现。

你现在是无人值守执行，没有人能实时回答你。不要向用户提问，更不要在没有收到真实
答复的情况下宣称"用户已确认"或"已和用户对齐"。所有悬而未决的取舍都写进产出里，
交给调用方事后裁决。
```

第二段才是关键。真正的失效模式**不是**"看不出矛盾"——裸 spec 下它多半看得出来，但看出来之后会**调 `ask` 工具、拿不到答复、然后凭空编一句「用户已确认：XXX」把矛盾抹平**再往下写。无人值守时根本没有用户。这个失效稳定复现，且不加 `--trace` 完全看不见。

## 注意（都是实测踩出来的）

- **执行者的工作目录里不许放任何日志、判分器、参照文件**。`--cwd` 是它们的共享沙盒，它们会读。实测出现过一个执行者读到 `progress.log` 里另一个执行者的测试断言，据此反推出「正确答案」。`--emit` / `--trace` / stderr 一律指向 `--cwd` 之外。
- **要做「改造前后行为一致」类任务，先把原件复制一份到工作目录外**，否则执行者原地改完就没有对拍基准了。

- **`--resume` 只吃全路径**，给裸 session id 会 `no such file or directory`。
- **别自己拼项目目录 slug**。`--dir` 传的路径和落盘目录名可能对不上（符号链接会让 `/ssd/workspace` 的会话落进 `-Users-kk-workspace/`），一律 `find ~/.reasonix/projects -name "$id.jsonl"` 定位。
- **`--output-format json` 才有 `session_id`**；`-p` 纯文本和 `--events-jsonl` 都没有。
- **别用「取 mtime 最新的 jsonl」猜 session**，并发起多个执行者时必然抢错。
- **一个 serve 进程只有一个活跃会话**（`/status` 单份 history，`/new` 会把当前会话换掉，跑起来时连切换都被禁）。要 N 个并发执行者只能起 N 个进程，所以并发场景优先用模式 B。
- **非交互下工具审批会静默卡住**：模式 A 用 `--permission-mode auto`，serve 用 `POST /tool-approval-mode {"mode":"auto"}`，模式 B 脚本已内建自动放行。

接口细节（serve 的完整 HTTP API、ACP 握手能力、会话文件布局）见 `references/interfaces.md`。
