# CLAUDE.md

面向 Claude Code 的仓库指南。

## 交流语言

默认用中文交流。提交信息用英文祈使句，简短明确。

## 项目定位

本仓库是一个**同时面向 Claude Code 和 Codex** 的 AI 技能插件。核心载荷是 `skills/`，command、agent、hook 为辅助。两端共用同一套 skills/commands/agents，只有 manifest 和 hooks 入口各自独立。

## 目录约定

- `.claude-plugin/`：Claude 插件 manifest 与 marketplace manifest。
- `.codex-plugin/`：Codex 插件 manifest（`skills` 指向 `./skills/`，`hooks` 指向 `./hooks/codex-hooks.json`）。
- `skills/`：技能，每个技能一个目录，含 `SKILL.md`，frontmatter 必须有 `name`（=目录名）和 `description`。
- `commands/`：斜杠命令，frontmatter 建议含 `description`。
- `agents/`：子 agent 定义，frontmatter 必须含 `name`、`description`、`tools`。
- `hooks/`：`hooks.json`（Claude）+ `codex-hooks.json`（Codex）+ 共用的 `*.sh` 脚本；hook 命令用 `${CLAUDE_PLUGIN_ROOT}` 定位脚本。
- `scripts/validate.sh`：结构校验。

## 开发与验证

结构或内容改动后至少运行：

```bash
bash scripts/validate.sh
```

改动涉及 manifest 时，先确认 JSON 可解析，并确认 `README.md` 的安装路径和组件列表仍准确。改动涉及 `hooks/*.sh` 时确认执行权限未丢失（`git diff --summary`）。

## 两端一致性

给两端都生效的组件（skills/commands/agents）改动无需区分 Claude/Codex。只有 hooks 需要在 `hooks.json` 和 `codex-hooks.json` 两处对应维护，脚本尽量共用。
