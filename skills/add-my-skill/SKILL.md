---
name: add-my-skill
description: 把用户给出的提示内容整理成一个新技能，加入 my-ai-skills-plugin 仓库并发布（clone 到临时目录→写技能→bump 版本→push→清理）。当用户想把一段说明/流程/经验沉淀成可复用技能并发布时使用。触发词：整理成技能、加个技能、发布技能、add-my-skill、把这段做成 skill。
---

# add-my-skill

把用户给出的提示内容整理成一个新技能，**加入 `my-ai-skills-plugin` 仓库并发布**。

本技能全局安装，触发时当前工作目录不一定是插件仓库，因此**不依赖 cwd、也不依赖任何本机固定副本**：每次把仓库 clone 到临时目录里操作，push 后删除。

- 仓库：`https://github.com/yoyo999888/my-ai-skills-plugin.git`
- 需要对该仓库有 push 权限（本机 git 凭据即可）。

## 何时使用

- 用户想把一段说明、流程或经验沉淀成可复用技能，并发布到本插件仓库。
- 用户提供了要转成技能的原始内容（口语化、零散也可以）。

## 步骤

1. **提炼技能名与内容**：从提示内容提炼一个 kebab-case 技能名 `<name>`，并把零散、口语化的内容归纳成清晰、可执行的技能说明。

2. **clone 到临时目录**：

   ```bash
   TMP=$(mktemp -d)
   git clone https://github.com/yoyo999888/my-ai-skills-plugin.git "$TMP"
   ```

   若 `$TMP/skills/<name>/` 已存在，改用更精确的名字，不要覆盖已有技能。

3. **写技能文件** `$TMP/skills/<name>/SKILL.md`，frontmatter 必须包含：
   - `name`：与目录名一致。
   - `description`：一句话写清「这个技能做什么 + 何时触发」，末尾附触发词。

   正文建议含「何时使用」「步骤」小节；大段参考资料、示例、脚本放进子目录（`references/`、`examples/`、`scripts/`），正文按需引用，保持 `SKILL.md` 精简。

4. **bump 版本号（发布必需）**：把三个 manifest 的 `version` 同步 patch +1（例如 0.1.0 → 0.1.1）。`marketplace.json` 里有 `metadata.version` 和 `plugins[0].version` 两处：

   ```bash
   cd "$TMP"
   python3 - <<'PY'
   import json, pathlib
   def bump(v): a,b,c = v.split("."); return f"{a}.{b}.{int(c)+1}"
   # .claude-plugin/plugin.json
   p = pathlib.Path(".claude-plugin/plugin.json"); d = json.loads(p.read_text())
   nv = bump(d["version"]); d["version"] = nv; p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
   # .codex-plugin/plugin.json
   p = pathlib.Path(".codex-plugin/plugin.json"); d = json.loads(p.read_text())
   d["version"] = nv; p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
   # .claude-plugin/marketplace.json（两处）
   p = pathlib.Path(".claude-plugin/marketplace.json"); d = json.loads(p.read_text())
   d["metadata"]["version"] = nv; d["plugins"][0]["version"] = nv
   p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
   print(nv)
   PY
   ```

5. **commit 并 push（发布）**，push 被拒则 rebase 重试：

   ```bash
   cd "$TMP"
   git add -A
   git commit -m "Add skill: <name>"
   git push origin HEAD:main || { git pull --rebase origin main && git push origin HEAD:main; }
   ```

6. **清理**：`rm -rf "$TMP"`。

7. **报告**：告诉用户新技能的相对路径、新版本号、commit。并提示：**发布已到 GitHub，但本机已装的插件要 `claude plugin update` / `codex plugin marketplace upgrade` 才拿到新技能。**

## 注意

- 直接 push `main` 是无 review 发布，适合个人技能库。若仓库改为受保护分支，改走 PR。
- 全程在临时目录操作，不碰用户当前项目，也不碰本机其它 clone。
