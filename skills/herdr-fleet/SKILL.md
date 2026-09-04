---
name: herdr-fleet
description: 一个 manager（本会话）通过 herdr 指挥多台机器上的多个常驻 worker（herdr pane 里的交互 claude/glm）并行干长任务：部署 worker、任务书派活、cron 保活巡检、强制两轮反思验收、集成分支合并。当用户要"你管理这几台机器""开 N 个 worker 并行采集/构建/干活""跑一批小时级长任务并盯进度"时使用。触发词：manager worker、多机 worker、worker 舰队、herdr 编排、批量长任务、保活巡检、并行采集。
---

# herdr-fleet：manager 指挥多 worker

**角色**：manager（你，当前会话，唯一决策点）× N 台机 × 每机 M 个 worker（herdr workspace 里的常驻交互 claude/glm 会话）。适用：小时级长任务、跨机并行、需要断点续传与统一验收的批量工作。

与 `glm-orchestrate` 的分工：那是无头一次性执行（c2 -p / ask_planner 出任务图）；本技能是常驻交互 worker 的舰队管理。可组合：先出任务图，再用本技能跑。

## 生命周期

```
部署 worker → 派任务书 → cron 保活巡检 ⇄（blocked 代答 / 死亡重启续传 / 互斥协调）
→ worker 报完成 ≠ 通过 → 强制反思 ×2（REFLECT 留痕）→ PASS
→ 全部 PASS → 集成分支合并 → 停在验收（不进 main）
```

worker 状态机：`working → done待反思 → R1 → R2 → PASS`（R2 仍有实质发现则追加轮，直到连续一轮干净）。

## 一、部署 worker（每台机）

```bash
# 本机（你已在 herdr 内，HERDR_ENV=1；不在 herdr 里就别控制别人的 herdr）
herdr workspace create --cwd <任务目录> --no-focus --label <workspace 名>
herdr pane run <root_pane> glm     # glm 是 shell alias，只在 pane 的交互 shell 展开
herdr agent rename <pane> <worker 名>   # 名字即地址，规则 [a-z][a-z0-9_-]{0,31}

# 远程机：ssh 绝对路径遥控（非交互 ssh 的 PATH 不含 homebrew）
ssh <host> '/opt/homebrew/bin/herdr workspace create --cwd <目录> --no-focus --label <名>'
```

- 多 worker：对 root pane 连续 `pane split --direction right`（ratio 递减得等宽列）+ `pane run` + `rename`
- worker 名全局统一（如 `<前缀>-<机>-<序号>`），跨机不重名；herdr pane/agent id 都易变，按 worker 名寻址
- `agent start --kind claude` 不会带 alias 里的自定义 env（网关/token），走网关的 worker 一律 `pane run <alias>`

## 二、派活：任务书文件，绝不在命令行内联长文本

1. 本地写 `/tmp/<任务>-task.md`（完整模板见 `references/templates.md`），scp 分发到各机
2. `herdr agent prompt <worker 名> "$(cat /tmp/<任务>-task.md)"`——长任务**不加 `--wait`**（那是等整轮完成的）；发完 1 分钟内 `agent list` 确认转 `working`
3. 任务书必须自含：worktree 切法（**基于 origin/main**，防远程机本地分支污染）、输出目录、外部资源（MCP/bridge/CLI）调用要点与已知坑、执行约束（互斥/错峰/标记文件）、完成动作（commit + push + 报告格式 + 「停下待命，不要自行开始其它任务」）

## 三、保活巡检（manager 的 cron）

`CronCreate` 用错峰分钟（如 `7-59/20 * * * *` = 每小时 7/27/47），prompt 固化全部巡检逻辑（骨架见 references/templates.md）：

- **扫状态**：本机 `herdr agent list`，远程 `ssh <host> '/opt/homebrew/bin/herdr agent list'`。working 不打扰
- **blocked**：`agent read` 看问题 → 按任务计划精神**自主代答**（需用户预先授权，每次代答记录在案），重大偏离计划才停下上报
- **死亡/unknown**：读 pane 输出诊断 → `pane run <pane> <alias>` 重启 → `agent rename` 恢复名 → 按 worktree `git log` 判断进度，重发任务书并注明「已完成部分不重做」
- **资源互斥**：需要排队的资源（前台/锁/独占设备）用标记文件信号——先占者完成临界段后 `touch /tmp/<信号>`，后继 worker 轮询该文件再进入；巡检检查信号与后继者是否推进
- 每轮一行简报：各 worker 状态机位 + 进度计数（已推送分支数等）

## 四、完成 ≠ 通过：强制两轮反思

worker 报告任务完成时，**不采信**，立即发反思任务书（模板见 references/templates.md）：

- 逐条 case 核对：产出文件路径 / blocked 理由 / 承认缺失——三选一，不许含糊
- 核查 schema、provenance、阳性对照、超时、重复次数；blocked 理由真实性（防绕过偷懒）；静默降级（要求逐帧只采单点、要求矩阵只采对角这类）
- 每轮产出 `REFLECT-<轮>.md` 放进输出目录，commit + push——manager 合并时逐任务可查自查清单
- **两轮均零实质新发现 = PASS**；第 2 轮仍有实质发现则追加反思轮，直到连续一轮干净
- 阶段推进（下一批任务/收尾单窗）以「全部 PASS」为门槛，不是「全部完成」

## 五、集成

全部分支推齐 → manager 在本机仓库逐个 `git merge` 进**集成分支** → push → **停在验收**，用户点头才进 main。产物目录互不重叠时冲突风险低，仍逐分支看 diff（REFLECT 文件是核对清单）。

## 坑（泛化）

- 远程非交互 ssh PATH 不含 `/opt/homebrew/bin` → herdr 一律绝对路径
- shell alias 只在交互 shell 展开：`pane run` 可用，`ssh <host> 'glm'` 不可用
- `agent prompt "$(cat 文件)"` 的 cat 展开发生在目标机 shell——本地写文件 + scp + 目标机 cat，绕开三层引号转义地狱
- worker 重启后 agent 名要重建（名跟 pane 走）；先 `agent list` 防重名
- session-only cron 随 manager 会话死：长任务期间 manager 会话不能关；durable cron 只在用户明确要求跨会话时用
- 巡检发现的外部依赖断了（如常驻 bridge/daemon）要先修依赖再重启 worker：daemon 类进程裸 nohup 常因 stdin EOF 自杀，用 `nohup zsh -c "exec tail -f /dev/null | <daemon>" &` 保活
