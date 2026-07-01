#!/usr/bin/env bash
# session-tip.sh — 会话开始时提示插件已加载（示例 hook）
# 被 Claude Code 的 hooks/hooks.json 和 Codex 的 hooks/codex-hooks.json 共用。
# SessionStart hook 的 stdout 会作为附加上下文注入会话。

set -euo pipefail

cat <<'TIP'
[my-ai-skills-plugin] 已加载。可用 /hello 查看组件，或用 hello-skill 作为新技能模板。
TIP
