---
name: list-my-skills
description: 列出 my-ai-skills-plugin 仓库 skills/ 目录下当前所有技能名称及其 description 一句话说明；触发词：list-my-skills、列出我的技能、查看 my-ai-skills-plugin 技能列表。
---

# list-my-skills

列出 `my-ai-skills-plugin` 仓库 `skills/` 目录下当前所有技能的名称，以及每个技能 frontmatter `description` 里的一句话说明。

## 何时使用

- 用户想查看 `my-ai-skills-plugin` 里已经发布了哪些技能。
- 用户要求列出、盘点、汇总或检查个人技能库中的技能名称和说明。

## 步骤

1. clone 仓库到临时目录，不依赖当前 cwd 或本机已有副本：

   ```bash
   TMP=$(mktemp -d)
   git clone https://github.com/yoyo999888/my-ai-skills-plugin.git "$TMP"
   ```

2. 遍历 `$TMP/skills/*/SKILL.md`，读取每个文件开头 YAML frontmatter 中的 `name` 和 `description`。

3. 输出精简列表，格式建议为：

   ```text
   - <name>: <description>
   ```

4. 如果某个技能缺少 `name`，用目录名兜底；如果缺少 `description`，标记为 `无 description`。

5. 完成后删除临时目录：

   ```bash
   rm -rf "$TMP"
   ```

## 建议实现

可用 Python 标准库解析简单 frontmatter，避免依赖额外包：

```bash
TMP_DIR="$TMP" python3 - <<'PY'
import os, pathlib, re

root = pathlib.Path(os.environ["TMP_DIR"]) / "skills"
for skill in sorted(root.glob("*/SKILL.md")):
    text = skill.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    data = {}
    if match:
        for line in match.group(1).splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip().strip('"').strip("'")
    name = data.get("name") or skill.parent.name
    desc = data.get("description") or "无 description"
    print(f"- {name}: {desc}")
PY
```
