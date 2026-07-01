---
description: 根据提示内容整理成一个技能，写入 skills/<name>/SKILL.md
argument-hint: <技能的描述/提示内容>
---

把下面的提示内容整理成本插件的一个技能：

$ARGUMENTS

步骤：

1. 从提示内容提炼一个 kebab-case 技能名 `<name>`。若已存在 `skills/<name>/`，改用更精确的名字，不要覆盖已有技能。
2. 创建 `skills/<name>/SKILL.md`，frontmatter 必须包含：
   - `name`：与目录名一致。
   - `description`：一句话写清「这个技能做什么 + 何时触发」，末尾附触发词，便于被正确调用。
3. 正文把提示内容整理成可执行的技能说明（建议含「何时使用」「步骤」小节）；把提示里零散、口语化的内容归纳成清晰、可复制运行的指令。
4. 大段参考资料、示例或脚本放进子目录（`references/`、`examples/`、`scripts/`），正文按需引用，保持 `SKILL.md` 精简。
5. 完成后向用户报告新建技能的相对路径和 `description`。
