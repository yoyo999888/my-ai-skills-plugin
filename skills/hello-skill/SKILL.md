---
name: hello-skill
description: 一个最小的示例技能，演示 SKILL.md 的结构。当用户想验证插件是否装好、或需要一个新技能的起始模板时使用。触发词：hello-skill、示例技能、skill 模板、demo skill。
---

# hello-skill

这是 `my-ai-skills-plugin` 附带的示例技能，用来演示技能文件的最小结构，同时充当新技能的起始模板。

## 何时使用

- 用户想确认插件在 Claude Code 或 Codex 里已正确加载。
- 需要一个可复制的 `SKILL.md` 骨架来编写新技能。

## 步骤

1. 向用户确认这是演示，说明技能已成功加载。
2. 复述当前触发上下文（用户说了什么触发了本技能）。
3. 若用户要新建技能，把本目录复制为 `skills/<新技能名>/`，改写 frontmatter 的 `name` 与 `description`，再重写正文。

## frontmatter 约定

- `name`：kebab-case，与目录名一致。
- `description`：一句话说明「做什么 + 何时触发」，越具体越容易被正确调用；末尾附触发词有帮助。

## 扩展资料

把大段参考、示例代码、脚本放到本目录的子文件夹里（例如 `references/`、`examples/`、`scripts/`），在正文里按需引用，保持 `SKILL.md` 精简。
