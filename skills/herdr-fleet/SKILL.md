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
- **复用上轮舰队先清点**：worker pane/会话会在战役间隔中丢失（agent list 缺员时 `pane split --cwd <目录>` → `send-text "<alias>\n"` → 等 ~10s → `agent rename` 重建），缺谁补谁，不必整套重建

## 二、派活：任务书文件，绝不在命令行内联长文本

1. 本地写 `/tmp/<任务>-task.md`（完整模板见 `references/templates.md`），scp 分发到各机
2. `herdr agent prompt <worker 名> "$(cat /tmp/<任务>-task.md)"`——长任务**不加 `--wait`**（那是等整轮完成的）；发完 1 分钟内 `agent list` 确认转 `working`
3. 任务书必须自含：worktree 切法（**基于 origin/main**，防远程机本地分支污染）、输出目录、外部资源（MCP/bridge/CLI）调用要点与已知坑、执行约束（互斥/错峰/标记文件）、完成动作（commit + push + 报告格式 + 「停下待命，不要自行开始其它任务」）
4. **计数与挪动注释必须和表的实际行数一致**（「本窗共 N 项」写错数字，worker 会停下来向你求证，浪费一轮）
5. 源计划文档可能有生成器截断/歧义行：任务书注明「以 <全量参考文档> 交叉核对，仍不明确就列出待裁定」——worker 请求裁定是好行为，不是低效
6. 计划行与文字「建议归属」不一致时，**manager 派发前统一挪行**并在两侧任务书都标注（挪出方「-1 行」、挪入方「+1 行，自 X 挪入」），杜绝两窗重复干同一行

## 三、保活巡检（manager 的 cron）

`CronCreate` 用错峰分钟（如 `7-59/20 * * * *` = 每小时 7/27/47），prompt 固化全部巡检逻辑（骨架见 references/templates.md）：

- **扫状态**：本机 `herdr agent list`，远程 `ssh <host> '/opt/homebrew/bin/herdr agent list'`。working 不打扰
- **停滞检测靠日志增长，不靠追问**（`scripts/fleet-stall.sh`）：每轮先跑它——抓每台 worker pane 全文算 md5 与上次快照比，`changed` = 在干活别打扰，`STILL Nm` = 静止 N 分钟；附尾部空等模式（`sleep N` / `not yet` / `MERGED`）、租约/429 标志、推送日志里的最近推送时间。`STILL` 超过两轮巡检间隔才去读 pane 尾部：空等 → prompt 告知真实状态并令切下一 AC；死亡 → 重启续传。`agent_status=working` 不等于有进展（worker 用 sleep 轮询等一个不存在的 PR 也是 working）——曾因只看状态位漏掉 1h+ 空等。用法：`FLEET_HOSTS="unity:d7 hufan:d1" FLEET_PUSH_LOG=/tmp/dmf-hub-sync.log scripts/fleet-stall.sh`
- **blocked**：`agent read` 看问题 → 按任务计划精神**自主代答**（需用户预先授权，每次代答记录在案），重大偏离计划才停下上报
- **死亡/unknown**：读 pane 输出诊断 → `pane run <pane> <alias>` 重启 → `agent rename` 恢复名 → 按 worktree `git log` 判断进度，重发任务书并注明「已完成部分不重做」
- **资源互斥**：需要排队的资源（前台/锁/独占设备）用标记文件信号——先占者完成临界段后 `touch /tmp/<信号>`，后继 worker 轮询该文件再进入；巡检检查信号与后继者是否推进。**标记文件只在同机可见**（互斥的本质是同机独占资源，跨机本无冲突），任务书里别写别机的信号路径；**新一轮战役开跑前清掉上轮的残留信号文件**（旧信号会让新 worker 误判放行）
- 每轮一行简报：各 worker 状态机位 + 进度计数（已推送分支数等）
- **跨窗协调**（多子任务共享发现时）：某窗偶得发现指向另一窗的域 → 记移交台账（原始证据留在源窗产物、目标窗引用记录号不重采）；发现两窗要撞同一件事 → 防重复更正随时可发（prompt 排队不打断 working 中的 worker）
- **工具链风险广播**：某窗发现共享通道有风险（如某工具自报数据失真）→ 让用同通道的其它窗在下一反思轮自查对账；已 PASS 的窗按风险敞口抽查

## 四、完成 ≠ 通过：强制两轮反思

worker 报告任务完成时，**不采信**，立即发反思任务书（模板见 references/templates.md）：

- 逐条 case 核对：产出文件路径 / blocked 理由 / 承认缺失——三选一，不许含糊
- 核查 schema、provenance、阳性对照、超时、重复次数；blocked 理由真实性（防绕过偷懒）；静默降级（要求逐帧只采单点、要求矩阵只采对角这类）
- 每轮产出 `REFLECT-<轮>.md` 放进输出目录，commit + push——manager 合并时逐任务可查自查清单
- **反思书要点名前一轮的具体发现逐条复核**（「R2 抓出的 X 本轮复验」），不是泛泛「再查一遍」；发现分级：数据级/结论级（实质）与保全级（格式/provenance）
- **「实质新发现」的裁量**：问题型（推翻结论/暴露缺口/违规——阻塞 PASS）vs 成果型（交办补采的产出/表述精确化/适用域细化——当场闭环不阻塞）。不区分会把「每轮都有新数据」误判为「不收敛」，反思永远收不了口
- **worker 请求裁定时快速、明确**：三选一口径——以计划原文为准 / 按上下文推断执行予以认可 / 归属记实际执行窗。别让 worker 悬等裁定
- **两轮均零实质新发现 = PASS**；第 2 轮仍有实质发现则追加反思轮，直到连续一轮干净
- 阶段推进（下一批任务/收尾单窗）以「全部 PASS」为门槛，不是「全部完成」

## 五、集成

全部分支推齐 → manager 在本机仓库逐个 `git merge` 进**集成分支** → push → **停在验收**，用户点头才进 main。产物目录互不重叠时冲突风险低，仍逐分支看 diff（REFLECT 文件是核对清单）。

## 坑（泛化）

- 远程非交互 ssh PATH 不含 `/opt/homebrew/bin` → herdr 一律绝对路径
- shell alias 只在交互 shell 展开：`pane run` 可用，`ssh <host> 'glm'` 不可用
- `agent prompt "$(cat 文件)"` 的 cat 展开发生在目标机 shell——本地写文件 + scp + 目标机 cat，绕开三层引号转义地狱
- **长任务书走 base64 时**（内容含引号/`$` 等）：macOS BSD `base64 -d` **不吃位置参数**，要 `base64 -d -i <文件>`；且 b64 文件必须先 scp 到目标机再解码——本地生成、远程读必失败。herdr 对空 prompt 拒收（`empty_agent_prompt`），派发命令的 bug 会显性失败零污染，这是安全网不是故障
- worker 重启后 agent 名要重建（名跟 pane 走）；先 `agent list` 防重名
- session-only cron 随 manager 会话死：长任务期间 manager 会话不能关；durable cron 只在用户明确要求跨会话时用
- 巡检发现的外部依赖断了（如常驻 bridge/daemon）要先修依赖再重启 worker：daemon 类进程裸 nohup 常因 stdin EOF 自杀，用 `nohup zsh -c "exec tail -f /dev/null | <daemon>" &` 保活
- **`git worktree add <目录> origin/<分支>` 建出来是 detached HEAD**（不是本地分支）：在里面做合并前先 `git branch --show-current` 检查；`git push` 报 "Everything up-to-date" 而远端明明是旧 commit，先怀疑本地分支根本不存在（detached HEAD 上推了个寂寞）——`git branch -f <分支> <HEAD>` 再推
- worker 上下文打满（100%）仍能继续干活（runner 自动 compact），小时级战役不必中途换会话；轮次安排按内容多少，不按上下文余量
- **`workspace create` 返回的 workspace_id 在 `result.workspace.workspace_id`**（嵌在 workspace 对象里，不是 `result.workspace_id` 顶层键）——解析取错键得到空串，后续 pane 命令全报 `pane :p1 not found`；幂等复用已有 workspace 走 `workspace list` 按 label 匹配（2026-09-12 六机部署实犯）
