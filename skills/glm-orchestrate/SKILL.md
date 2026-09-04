---
name: glm-orchestrate
description: 在 Claude Code 里做「规划/实现分离」的两级编排——先把一个模型当无工具、无会话的纯规划函数问出一张任务图，再把实现节点并行派给多个 GLM 账号执行，主 session 只做校验与验收。当用户要拆解并并行推进一个多步骤任务、要省钱（强模型只规划、GLM 干活）、或要复刻 fable-orchestrator 那套编排时使用。触发词：glm 编排、规划实现分离、任务图、并行派活、多账号并行、plan-execute、fable-orchestrator、ask_planner。
---

# GLM 编排（规划 / 实现分离）

把一次任务拆成两种角色：

- **规划端**：一次性问答，拿回一张**任务图**。不给工具、不留会话、不碰文件。
- **执行端**：GLM 无头 Claude Code，按图的单个节点干活，只写自己那份文件。
- **主 session（你）**：校验图、派活、收证据、独立验证、最终验收。**安全与范围的最终责任在你**，不执行图里编造出来的东西。

## 何时使用 / 何时不用

用：任务能拆成 3 个以上可并行或有明确依赖的子任务；想让贵模型只出 20 行计划、让 GLM 干几千 token 的实现；需要多账号同时推进。

不用：单个明确的活 —— 直接走 `use-glm` 派一次就够，不要为一件事画图。规划本身就是目标（选型、架构裁决）时，也不要套这个壳。

## 一、规划端：把模型当纯函数调

核心就一条命令，`scripts/ask_planner.sh` 是它的封装：

```bash
claude --print --tools "" --no-session-persistence \
       --output-format text --system-prompt "<编排器人设>" "<packet>"
```

- `--tools ""` 剥光所有工具 → 它**只能**输出计划，不可能偷偷改文件；
- `--no-session-persistence` 不落会话 → 无状态、可重复调用；
- `--print` 一次性问答 → 没有多轮漂移。

用法（packet 走 stdin）：

```bash
printf '%s' "$PACKET" | scripts/ask_planner.sh
```

环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `PLANNER_CMD` | `claude` | 规划端命令。裸 `claude` = 本机订阅（Opus/Fable，免 key）；填 `c2` 等 GLM alias = 全程 GLM |
| `PLANNER_MODEL` | 空 | **必须显式指定**，空=用当前默认模型。绝不去猜 |
| `PLANNER_EFFORT` | `medium` | 规划值得给高一点 |

**packet 里只放决策所需事实**：目标、验收标准、workspace 现状、约束、受保护文件、已有证据、可用执行端清单、并发上限。**不放任何密钥。**

## 二、任务图契约（收到图先按这个验）

每个节点必须齐全，缺一项就打回重问：

`id` · `依赖` · `独占的文件或职责` · `预期产出` · `验证方式` · `停止条件`

再检查三条硬约束：

1. **文件独占**：两个并行节点不得写同一个文件。冲突就串行化或重新划分。
2. **图末必须有集成 + 终验节点**。
3. 规划端**不出现在执行图里**——它不实现任何东西。

图不合理时你直接改，别盲从。规划端没看过你的 workspace，你看过。

## 三、执行端：并行派 GLM

本机 `~/.zshrc` 里有多个 GLM alias（`c0`/`c1`/`c2`/`c3`/`cc4`-`cc6`/`glm`），**分属不同账号 token**，因此可以真正并行而不互相挤额度。alias 自带鉴权与 `--permission-mode bypassPermissions --model glm-5.3`。

单节点派活：

```bash
zsh -ic 'c2 -p --output-format text' <<'PROMPT'
你是执行器，负责任务图的节点 n2。
只准修改：<文件列表>。其他 agent 正在并行改别的文件，不要动、不要重排、不要格式化它们。
目标：<预期产出>
完成后自检：<验证方式>
PROMPT
```

并行派 N 个节点：给每个节点分配**不同的 alias**（`c0` `c1` `c2` `c3`），用 Bash 工具的 `run_in_background: true` 同时起，收到完成通知再汇总。

## 四、必须知道的坑

1. **alias 只在交互式 zsh 里存在**。非交互 shell 直接敲 `c2` 会 `command not found`，必须 `zsh -ic '...'`。
2. **当前会话的 `CLAUDE_*` env 会被子进程继承**，新起的 claude 会被当成子会话（不登记、transcript 关闭、`--session-id` 失效）。派活前把 `CLAUDE_*` / `ANTHROPIC_*` 全部 unset（`ask_planner.sh` 已内置这步）。
3. **`[claude-code:unrecognized_model] {"model":"glm-5.3"}` 是无害告警**，GLM 端点正常返回，别当故障排查。同理还有一条 connectors disabled 的告警。
4. **`run_in_background` 的任务随宿主会话退出而死**（不受 `timeout` 参数限制、权限与前台一致）。要「会话关了也继续跑」必须 `nohup` 出去。
5. **绝不把 token 写进技能文件、prompt、日志或 commit**。鉴权只经由 alias 传递。
6. **回炉次数设上限**：复杂任务最多再问规划端 2 次（共 3 次），否则退化成无限左右横跳。

## 五、验收

只有主 session 独立跑过测试 / lint / build / 看过 diff 才算完成。**不接受执行端自报的「已完成」「测试通过」**——要证据。报告时说明：选了哪些模型、改了什么、验证证据是什么。

## 参考

`references/fable-orchestrator-teardown.md` —— 本技能的原型 `codejunkie99/fable-orchestrator` 的完整源码拆解，含它那个「模型发现」设计缺陷的实证（说明为什么这里坚持 `PLANNER_MODEL` 显式指定）。
