# AGENTS.md

面向 Codex 及其他编码 agent 的仓库指南。

## 交流语言

默认用中文交流。提交信息用英文祈使句，简短明确。

## 项目定位

本仓库是一个**同时面向 Codex 和 Claude Code** 的 AI 技能插件。核心载荷是 `skills/`，command、agent、hook 为辅助。两端共用同一套 skills/commands/agents，只有 manifest 和 hooks 入口各自独立。

Codex 通过 `.codex-plugin/plugin.json` 识别本插件：`skills` 指向 `./skills/`，`hooks` 指向 `./hooks/codex-hooks.json`。

## 目录约定

- `.codex-plugin/`：Codex 插件 manifest。
- `.claude-plugin/`：Claude 插件与 marketplace manifest。
- `skills/`：技能，每个技能一个目录，含 `SKILL.md`，frontmatter 必须有 `name`（=目录名）和 `description`。
- `commands/`：斜杠命令。
- `agents/`：子 agent 定义，frontmatter 含 `name`、`description`、`tools`。
- `hooks/`：`codex-hooks.json`（Codex）+ `hooks.json`（Claude）+ 共用 `*.sh`；hook 命令用 `${CLAUDE_PLUGIN_ROOT}` 定位脚本。
- `scripts/validate.sh`：结构校验。

## 开发与验证

结构或内容改动后至少运行：

```bash
bash scripts/validate.sh
```

manifest 改动先确认 JSON 可解析；hook 脚本改动确认执行权限未丢。

## 提交纪律

用户要求提交时，按可审查的主题分批提交，不要把不相关改动塞进一个提交。提交前看 `git status --short` 和对应 diff，只 stage 当前主题的文件。

## 文档风格

文档面向未来的 AI 使用者和插件维护者，直接、可执行、少背景叙事。命令示例必须能复制运行。
