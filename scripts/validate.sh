#!/usr/bin/env bash
# validate.sh — 插件结构验证脚本
# 检查 Claude / Codex 双插件的 manifest、hooks、skills 结构是否完整合法。

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ERRORS=0
WARNINGS=0

pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; ERRORS=$((ERRORS + 1)); }
warn() { echo "  ⚠ $1"; WARNINGS=$((WARNINGS + 1)); }

json_ok() { python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$1" 2>/dev/null; }
json_has_name() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert 'name' in d" "$1" 2>/dev/null; }

echo "=== my-ai-skills-plugin 结构验证 ==="
echo ""

# --- 1. Claude plugin.json ---
echo "[1] .claude-plugin/plugin.json"
CJSON="$ROOT/.claude-plugin/plugin.json"
if [ -f "$CJSON" ]; then
  if json_ok "$CJSON"; then
    pass "合法 JSON"
    json_has_name "$CJSON" && pass "包含 name 字段" || fail "缺少 name 字段"
  else
    fail "JSON 解析失败"
  fi
else
  fail "文件不存在"
fi

# --- 2. Claude marketplace.json ---
echo "[2] .claude-plugin/marketplace.json"
MJSON="$ROOT/.claude-plugin/marketplace.json"
if [ -f "$MJSON" ]; then
  json_ok "$MJSON" && pass "合法 JSON" || fail "JSON 解析失败"
else
  warn "文件不存在（作为 marketplace 分发时需要）"
fi

# --- 3. Codex plugin.json + hooks 引用 ---
echo "[3] .codex-plugin/plugin.json"
if [ -f "$ROOT/.codex-plugin/plugin.json" ]; then
  if python3 - "$ROOT" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
manifest = json.loads((root / ".codex-plugin" / "plugin.json").read_text())
assert "name" in manifest, "missing name"
hooks = manifest.get("hooks")
if hooks is not None:
    if not isinstance(hooks, str) or not hooks.startswith("./"):
        raise SystemExit("hooks 必须是以 ./ 开头的插件相对路径")
    hooks_path = (root / hooks[2:]).resolve()
    if not hooks_path.is_file() or root.resolve() not in hooks_path.parents:
        raise SystemExit("hooks 路径缺失或越出插件根目录")
    data = json.loads(hooks_path.read_text())
    cmds = [
        h.get("command", "")
        for ev in data.get("hooks", {}).values()
        for entry in ev
        for h in entry.get("hooks", [])
        if h.get("type") == "command"
    ]
    if cmds and any("${CLAUDE_PLUGIN_ROOT}" not in c for c in cmds):
        raise SystemExit("command hooks 必须使用 ${CLAUDE_PLUGIN_ROOT}")
PY
  then
    pass "合法 JSON 且 hooks 引用有效"
  else
    fail "Codex manifest 或 hooks 引用无效"
  fi
else
  fail "文件不存在"
fi

# --- 4. hooks JSON ---
echo "[4] hooks/"
for j in hooks.json codex-hooks.json; do
  if [ -f "$ROOT/hooks/$j" ]; then
    json_ok "$ROOT/hooks/$j" && pass "$j 合法 JSON" || fail "$j JSON 解析失败"
  else
    warn "hooks/$j 不存在"
  fi
done
for s in "$ROOT"/hooks/*.sh; do
  [ -e "$s" ] || continue
  [ -x "$s" ] && pass "$(basename "$s") 可执行" || warn "$(basename "$s") 缺少可执行权限（chmod +x）"
done

# --- 5. skills ---
echo "[5] skills/"
SKILL_COUNT=0
for d in "$ROOT"/skills/*/; do
  [ -d "$d" ] || continue
  SKILL_COUNT=$((SKILL_COUNT + 1))
  name="$(basename "$d")"
  if [ -f "$d/SKILL.md" ]; then
    if head -1 "$d/SKILL.md" | grep -q '^---$'; then
      pass "$name/SKILL.md 含 frontmatter"
    else
      fail "$name/SKILL.md 缺少 frontmatter（首行应为 ---）"
    fi
  else
    fail "$name/ 缺少 SKILL.md"
  fi
done
[ "$SKILL_COUNT" -eq 0 ] && warn "skills/ 下暂无技能"

# --- 6. agents / commands frontmatter ---
echo "[6] agents/ 与 commands/"
for f in "$ROOT"/agents/*.md "$ROOT"/commands/*.md; do
  [ -e "$f" ] || continue
  rel="${f#$ROOT/}"
  head -1 "$f" | grep -q '^---$' && pass "$rel 含 frontmatter" || warn "$rel 缺少 frontmatter"
done

echo ""
echo "=== 结果：$ERRORS 个错误，$WARNINGS 个警告 ==="
[ "$ERRORS" -eq 0 ]
