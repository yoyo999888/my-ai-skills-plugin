---
name: reasonix-executor
description: 把 reasonix CLI 当成有状态执行代理调度，用于已裁决、已拆分的实现、自测、机械执行或只读盘点；调度者必须先冻结方案与验收合同，Reasonix 不负责架构决策和最终验收。适用于持续具名执行者、隔离并发任务、返工续聊或 ACP 批处理。触发词：reasonix、执行代理、执行者池、并发 agent、外包给 reasonix、acp、reasonix serve。
---

# reasonix-executor

把 reasonix 当**有状态执行者**，不要把它当方案制定者或验收者。

## 快速选型

| 需求 | 命令 |
|---|---|
| 一次性只读问答 | reasonix -p "..." |
| 一个执行者持续推进 | scripts/rx（模式 A） |
| 一批隔离任务并发 | scripts/acp_pool.py（模式 B） |
| 展示界面或跨机访问 | reasonix serve，见 references/interfaces.md |

## 角色边界

- **调度者**：盘点依赖、冻结架构与语义、拆分任务、定义反例和验收合同、安排独立验收。
- **Reasonix**：在给定边界内实现、编写或运行指定自测、交付实际 diff 与原始证据；遇到实质未裁决事项返回 BLOCKED。
- **验收者**：依据实际 diff、独立判分器或外部测试给出最终结论。

状态只能按以下方向推进：

PLANNED → DISPATCHABLE → EXECUTING → SELF_TESTED → REVIEW_REQUIRED → ACCEPTED

Reasonix 最多报告 SELF_TESTED，不得自行宣称 ACCEPTED、允许合并或已经对齐用户。
BLOCKED 与 FAILED 是执行阶段的旁路终态，返回调度者处理，不得由执行者自行改合同后继续。

## 调度流程

1. **分类**：把任务标成 inventory、implement、test 或 mechanical-review。
2. **先裁决再实现**：若仓库事实未知，先派独立只读 inventory；由调度者根据结果裁决后再派实现。
3. **执行拆包门**：一个任务包只保留一个可观察目标、一个同源失败域和一组共享 fixture。按行为边界拆，不按文件数量凑包。
4. **冻结任务包**：记录基线 commit、已知基线失败、允许/禁止路径、实现合同、反例、自测命令、时间预算和非目标。
5. **隔离执行**：变更任务使用独立 worktree；并发任务必须写集不相交，且不能让不同 session 同时写同一 worktree。
6. **收取证据**：读取实际 diff、命令退出码、耗时和未决事项；不要用执行者的总结替代检查。
7. **独立验收**：关键任务使用工作区外的判分器或独立验收者；判分器先回灌坏版本，证明能撞破缺陷。

任何变更、多文件任务、并发任务或返工任务，投递前必须阅读并使用
[references/task-packet.md](references/task-packet.md)。简单只读问答可使用最小任务包。

出现以下任一情况时先拆包或裁决，不要直接投递：

- 同时包含多个可以独立失败、回退或验收的行为；
- 不同验收项不共享同一运行序列或 fixture；
- 需要执行者选择架构、兼容语义、数值阈值、范围或最终 PASS 标准；
- 实现前仍需确认穷举集合、入口、调用契约或基线事实；
- 并发写集重叠，或无法明确合并顺序。

## 四类任务

| 类型 | Reasonix 可以做 | Reasonix 不可以做 |
|---|---|---|
| inventory | 只读搜索、列事实与出处、标未知项 | 修改文件、根据事实代替调度者裁决 |
| implement | 按冻结合同实现并自测 | 扩范围、改架构、选择未给定语义 |
| test | 实现或运行调度者指定的判据与反例 | 自行降低门槛、把结构门冒充行为门 |
| mechanical-review | 给候选 finding、证据和置信度 | 签最终验收、把推断写成已确认事实 |

## 模式 A：具名执行者持续推进

~~~bash
rx spawn api-work "按任务包实现 handlers 校验中间件" --dir /path/to/repo
rx ask   api-work "只处理验收项 A3 的具体反例，其他项保持不动"
rx ls
rx show  api-work
~~~

session_id 始终可见，也可直接当句柄：

~~~bash
rx ask 20260731-095631.635102000-deepseek-v4-flash "继续当前原子任务"
rx ask ~/.reasonix/sessions/7cc8787f-....jsonl "继续当前原子任务"
rx adopt frompool 7cc8787f-263c-4795-9d17-e878bda9d3fe --dir /path/to/repo
~~~

登记默认位于 ~/.reasonix-crew/（可用 RX_HOME 修改）。rx rm 只删除登记，不删除会话文件。

常用参数：

- --dir：工作目录；
- --model：模型；
- --perm：权限模式，默认 auto；
- --timeout：单轮超时，默认 3600 秒；
- --copy：会话被占用时复制后继续。

同一合同下的正常返工继续原 session。若发生基线 rebase、合同实质变化或连续两轮语义返工，
先由调度者重建一份当前事实快照；旧假设仍持续污染时，创建有 lineage 记录的新 session。

## 模式 B：隔离并发

只把**相互独立、写集不重叠**的任务放进同一批：

~~~bash
python3 scripts/acp_pool.py --cwd /path/to/repo "任务A" "任务B" "任务C"

echo '[{"prompt":"新任务"},{"prompt":"追问","resume":"<sessionId>"}]' \
  | python3 scripts/acp_pool.py --cwd /path/to/repo --tasks -
~~~

输出：

~~~json
[{"index":0,"sessionId":"6c68be10-...","transcriptPath":"/path/to/session.jsonl",
  "stopReason":"end_turn","text":"..."}]
~~~

参数：

- --emit results.jsonl：完成一个就追加一行；
- --trace trace.jsonl：记录全部工具调用；
- --model、--timeout：模型和总超时；
- --no-guard、--guard-file：控制守则。

关键写任务默认开 --trace，并把 --emit、--trace 和判分器放在工作目录外。不要并发 resume
同一会话，也不要让不同会话并发修改同一 worktree。

## 无人值守守则

scripts/rx 与 scripts/acp_pool.py 默认注入 [scripts/guard.md](scripts/guard.md)。
无人值守执行不得关闭守则。

守则要求：

- 只执行调度者已裁决的合同；
- 遇到会改变外部行为、架构、范围、数据或验收标准的冲突时，在写入前返回 BLOCKED；
- 不向不存在的实时用户提问，不虚构“用户已确认”；
- 不越过允许路径与权限边界；
- 自测结果只标 SELF_TESTED，逐项给出命令、退出码、耗时和剩余风险。

局部命名、等价代码组织等不改变合同的实现细节可自行决定，无需把执行者降格为逐字符机器人。

## 测试与证据纪律

- 先证明反例有效：旧实现失败，新实现通过；最终不留下临时 mutant。
- 静态测试只证明结构，不能宣称运行时行为。
- 涉及 timeout、重试或轮询的 mock 注入 clock、sleep 和 timeout，设置明确秒级预算，禁止吃真实墙钟。
- 执行者编写的测试属于自测；关键判分器由调度者或验收者独立维护并放在工作区外。
- 长期验收报告在独立验收后生成。Reasonix 只交任务级工作记录，不写“全部闭合”式结论。

## 已知注意事项

- 工作目录里不要放日志、隐藏判分器或参照答案；执行者能读取它们。
- “改造前后行为一致”任务先把原件复制到工作目录外，保留对拍基准。
- --resume 需要完整会话路径；rx 可代为定位裸 session id。
- 不要根据 mtime 猜会话，也不要自行拼 reasonix 项目目录 slug。
- 只有 --output-format json 带 session_id。
- 一个 reasonix serve 进程只有一个活跃会话；多执行者使用模式 B。
- 工具层仍有 initialize 早期失败、超时 reader 竞态和存活挂起只能靠总超时兜底等已知问题。

更多资料：

- 调度拆包、任务包模板和返工协议：[references/task-packet.md](references/task-packet.md)
- serve / ACP 接口：[references/interfaces.md](references/interfaces.md)
- 能力基线、失效案例与已知问题：[references/verification.md](references/verification.md)
