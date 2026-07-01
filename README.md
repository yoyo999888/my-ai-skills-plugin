# my-ai-skills-plugin

一个 AI 技能插件，同时作为 **Claude Code 插件**和 **Codex 插件**分发。技能放在 `skills/`。

```
.claude-plugin/plugin.json       # Claude Code 插件 manifest
.claude-plugin/marketplace.json  # Claude Code marketplace manifest
.codex-plugin/plugin.json        # Codex 插件 manifest（skills 指向 ./skills/）
skills/                          # 技能，每个技能一个目录含 SKILL.md
```

## 安装（Claude Code）

```bash
claude plugin marketplace add https://github.com/yoyo999888/my-ai-skills-plugin
claude plugin install my-ai-skills-plugin@my-ai-skills-plugin
```

Codex 通过 `.codex-plugin/plugin.json` 识别本插件。

## 新增技能

在 `skills/<技能名>/SKILL.md` 里写，frontmatter 需含 `name`（=目录名）和 `description`（说明做什么、何时触发）。
