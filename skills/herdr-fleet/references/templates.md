# herdr-fleet 模板集

## 1. 任务书模板（/tmp/<任务>-task.md，按任务定制 EXTRA 段）

```
任务：执行 <计划名> 的 <子任务 ID>（长任务，独立完成，计划范围内的问题自行决策，不要中途提问等待）。

## 准备
1. 通读 <计划文件路径>：重点执行结构节（case ID / 输出 schema / 超时 / 完成标记 / provenance 要求 / 互斥与错峰规则）+ 你负责的 <子任务> 全部 case + blocked 台账（别越界采别人的）。
2. 切 worktree（基于 origin/main，不要基于本地当前分支）：
   cd <仓库路径> && git fetch origin && git worktree add .claude/worktrees/<worktree 名> -b <分支名> origin/main
   之后所有工作都在 worktree 目录里做。
3. 输出目录（先建）：worktree 内 <输出路径>

## 外部资源（按任务定制：MCP bridge / CLI / daemon）
- 资源地址、鉴权方式、调用示例命令
- 已知坑（参数名拼写、id 易变要按稳定名重解析、工具面怎么发现）

## 执行约束
<EXTRA：互斥标记文件 / 错峰规则 / 顺序要求（某项必须最后做）等>
- 每项按计划要求带阳性对照与超时；时序敏感项重复 3-5 次取中位。
- 计划内确实不可完成的项：在汇总 MD 里开「本地 blocked」小节记录原因与解除条件，不要静默丢弃，也不要为凑数编造数据。
- 不要动 main、不要合并、只在自己的 worktree/分支工作；不要碰其他资源实例。

## 完成动作
1. 在 worktree 里 git add -A && git commit（信息写清子任务号与完成统计）&& git push origin <分支名>
2. 报告：完成/失败/blocked 数、输出文件清单、commit hash、分支名。然后停下待命，不要自行开始其它任务。
```

生成技巧：本地用 python 脚本以「模板 + 每任务参数表」批量生成 N 份，再 scp 分发，比手写 N 份不易漏。生成后校验：每份任务书里的项数注释与实际表行数一致（错了 worker 会停下来求证）；跨任务挪动的行两侧任务书都要标注。

## 2. 反思任务书模板（worker 报告完成时发，轮 R，共 2 轮）

```
反思轮 <R>（共 2 轮）：你的完成报告不作数。重新打开 <计划文件>，把 <子任务> 的每个 case 逐条过一遍：
a) 每个 case 是否有对应产出？逐 case 给出：产出文件路径 / blocked 理由 / 或承认缺失。
b) 产出是否满足计划要求：schema、provenance（版本/脚本 hash/时间戳/环境）、阳性对照、超时、时序项重复次数。
c) blocked 理由是否真实成立（不是绕过偷懒）？解除条件写了吗？
d) 有无静默降级（如要求逐帧只采了单点、要求矩阵只采对角）？
发现问题：补采修正 → 在 worktree 写 <输出路径>/REFLECT-<R>.md（逐 case 一行 PASS/补采/blocked + 本轮发现与修补说明）→ git commit（写明反思轮修补）→ push。
没有问题：同样写 REFLECT-<R>.md（逐 case 全 PASS）→ commit + push。
报告本轮：新发现问题数、修补数、结论。不要开始其它任务。
```

判定：两轮均零实质新发现 = PASS；第 2 轮仍有实质发现 → 追加轮，直到连续一轮干净。R2+ 的反思书要**点名上一轮的具体发现**逐条复核（如「R2 抓出的 X 补采数据本轮重跑 1 rep 确认稳定」），并区分问题型发现（阻塞 PASS）与成果型发现（交办产出/表述精确化，当场闭环不阻塞）。

## 3. 巡检 cron prompt 骨架（CronCreate，recurring，错峰分钟如 7-59/20 * * * *）

```
【<任务名> 保活巡检 + 反思 + 阶段触发】核心纪律：worker 的完成报告一律不采信，必须过两轮反思才算 PASS。
1) 扫描：本机 herdr agent list + ssh <各远程机> '/opt/homebrew/bin/herdr agent list'，看 <worker 名单>。working 不打扰。
2) blocked：herdr agent read 看问题，按 <计划文件> 精神自主代答（用户已授权）；重大偏离才停下报告用户。
3) unknown/agent 消失：读 pane 诊断；挂了 pane run <alias> 重启 + agent rename 恢复，按其 worktree git log 续传，重发 <任务书路径>（已完成部分不重做）。
4) 互斥信号检查：<标记文件> 是否出现；出现而后继 worker 临界段未推进就提醒。
5) 反思流程：worker 报完成 → 立即发反思 1/2 → 完成后发 2/2 → 两轮零实质新发现才 PASS；第 2 轮仍有发现则追加。用 /tmp/reflect-<子任务>.md 跟踪各任务进度（working/done待反思/R1/R2/PASS）。
6) 阶段触发：全部子任务 PASS → 简报用户后自动部署下一阶段（清场/验杀/派收尾任务书），下一阶段同样走两轮反思。
7) 每次扫描一行简报：各任务状态 + 进度计数。
```
