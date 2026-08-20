---
name: use-glm
description: Run tightly scoped tasks through the local GLM-backed Claude Code headless runner. Use when the user explicitly asks to use GLM, glm-agent, GLM Claude Code, or use-glm for delegation, narrow research, document drafts, fact-table drafts, review checklists, or bounded execution where the main agent must review the result.
---

# Use GLM

Use this skill to delegate a concrete, bounded task to the GLM Anthropic-compatible Claude Code runner, then independently review its output. GLM is an execution agent, not the final architectural decision-maker or verifier.

## Workflow

1. Freeze the scope, inputs, files allowed to change, and objective acceptance checks before delegating.
2. Run the local `c2` alias (or the equivalent GLM headless runner) with model `glm-5.3`.
3. Wait for completion at low frequency; do not busy-poll or repeatedly inspect unchanged diffs.
4. Independently rerun the relevant tests, formatter, linter, build, and diff checks. Do not trust a self-reported “completed” or “passed” without evidence.

## GLM headless command

The local `c2` alias must set all GLM model aliases to `glm-5.3` and select `--model glm-5.3`:

```bash
c2 --permission-mode bypassPermissions --model glm-5.3 -p --output-format text <<'PROMPT'
你是 glm-agent，一个通过 GLM Anthropic-compatible endpoint 运行的 Claude Code 无头执行器。

任务：
[在这里写具体任务]
PROMPT
```

`c2` supplies authentication and runner defaults; do not put authentication tokens in this skill or in delegated prompts.

## Boundaries

- Keep delegated tasks narrow and do not ask GLM to make final architecture decisions.
- Do not allow unrelated refactors or edits outside the frozen file scope.
- Never publish authentication tokens in skill files, prompts, logs, or commits.
