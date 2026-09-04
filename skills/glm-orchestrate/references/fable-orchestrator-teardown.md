# 原型拆解：codejunkie99/fable-orchestrator

本技能的原型。2026-09-04 通读全部源码（6 个文件 / 184K / 单 commit）后的记录，重点是**哪些设计值得抄、哪个设计不能抄**。

## 它是什么

不是编排引擎，是一个 **prompt 包**：装进 Codex 的 skill 目录（`~/.codex/skills/fable`），全部实质内容就三个文件。

```
skill/fable/SKILL.md              ← 给 Codex 的自然语言规矩
skill/fable/scripts/ask_fable.sh  ← 唯一的可执行代码，77 行
skill/fable/agents/openai.yaml    ← 4 行界面元数据
```

## 三层结构

**① 角色分工**（纯自然语言约定，写在 SKILL.md）

- Claude Fable 5.1 = 只编排和裁决，不写代码不碰文件，且明确排除在 worker 图之外
- Codex = 运行时，spawn worker、持有文件、跑工具、验证、报告
- 实现只准派给 `opencode-go-responses/gpt-5.6-luna`（常规）与 `opencode-go/deepseek-v4-flash`（循环 / 高吞吐机械活），这两个 agent 由 Codex Router 提供，仓库自己不带 provider / key / 模型目录

**② 把模型当纯规划函数调**（值得抄的核心）

```bash
claude --print --model X --effort low --permission-mode dontAsk \
       --tools "" --no-session-persistence --output-format text \
       --system-prompt "$system_prompt" "$packet"
```

`--tools ""` 剥光工具、`--no-session-persistence` 不落会话、`--print` 一次性问答。**复用本机 Claude Code 登录态，因此不需要任何 API key** —— 这是它最实用的一点。

（这些 flag 在 claude CLI 里全部真实存在且取值合法：`--effort` 取 low/medium/high/xhigh/max，`--permission-mode` 取 acceptEdits/auto/bypassPermissions/manual/dontAsk/plan。）

**③ 执行回路**（SKILL.md 的 8 步）

收集 workspace 事实 → 打包 packet → 问 Fable 拿图 → **Codex 校验这张图**（安全与范围的最终责任在 Codex，不执行编造的模型）→ 并行 spawn 就绪节点 → 收结果验证 → 需要时把结果 packet 回炉裁决，**最多 3 轮** → 返回内容逐字挂在 `Fable 5.1 speaks:` 标题下。

## ⚠️ 不要抄的地方：模型发现

它没有内置模型目录（作者注释说「Claude Code 没有可移植的列模型命令」），改成用 jq 从 `~/.claude/settings.json` 和 `~/.claude/stats-cache.json` 里**刮 model 字段**当候选，按顺序试，第一个不报错就 break。

本机跑同样的 jq 实测：

```
settings.json     → opus[1m]                        ← 永远命中，循环立刻 break
stats-cache.json  → claude-fable-5, claude-opus-5,
                    deepseek-v4-flash, glm-5.2 …    ← 用量统计，混着非 Anthropic 模型名
```

两个后果：

1. **它根本不保证用 Fable 模型**。本机上这个「Fable orchestrator」实际调的是 `opus[1m]`，而 system prompt 里在骗它「你是 Fable 5.1」。
2. 一旦第一个候选失败，它会拿 `--model glm-5.2` 去喂 claude CLI —— 从**用量统计**里刮模型名，本质上是把统计当成配置读。

**所以本技能坚持 `PLANNER_MODEL` 显式指定，空值就老老实实用默认模型，不做任何猜测式发现。**

## 另一个局限

所有「编排纪律」都只是 prompt：没有调度器、没有状态机、没有并发控制、没有图的结构化校验、没有持久化。「并行度上限」「文件独占归属」「最多 3 次调用」「拒绝非法模型节点」全靠执行方读了 SKILL.md 之后自觉遵守。能不能成立取决于指令遵循能力，而不是代码 —— 本技能同理，所以把**主 session 独立验证**写成硬要求。

## 它真正解决的问题

一个具体的成本 / 能力错配：**用最强的模型做规划（贵、调用次数少），用便宜快的模型做实现（多、量大）**，且规划这一跳走本机订阅登录态、零 API key 配置。这个判断是对的，值得复刻。
