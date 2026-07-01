# my-ai-skills-plugin

一套可复用的 AI 技能插件，**同时作为 Claude Code 插件和 Codex 插件**分发。核心载荷是 `skills/`，另外附带示例 command、agent 和 hook。

## 目录结构

```
my-ai-skills-plugin/
├── .claude-plugin/
│   ├── plugin.json          # Claude Code 插件 manifest
│   └── marketplace.json     # Claude Code marketplace manifest
├── .codex-plugin/
│   └── plugin.json          # Codex 插件 manifest（引用 skills/ 与 codex-hooks.json）
├── skills/                  # 技能（主载荷）
│   └── hello-skill/SKILL.md
├── commands/                # 斜杠命令
│   └── hello.md
├── agents/                  # 子 agent 定义
│   └── skill-scaffolder.md
├── hooks/
│   ├── hooks.json           # Claude Code hooks
│   ├── codex-hooks.json     # Codex hooks
│   └── session-tip.sh       # 两端共用的示例 hook 脚本
├── scripts/
│   └── validate.sh          # 结构校验
├── AGENTS.md                # 面向 Codex / 编码 agent 的仓库指南
└── CLAUDE.md                # 面向 Claude Code 的仓库指南
```

Claude Code 与 Codex 共用同一套 `skills/`、`commands/`、`agents/` 内容，各自只有独立的 manifest（`.claude-plugin/` vs `.codex-plugin/`）和 hooks 入口。

## 安装

### Claude Code

作为本地 marketplace 安装：

```bash
claude plugin marketplace add ~/workspace/my-ai-skills-plugin
claude plugin install my-ai-skills-plugin@my-ai-skills-plugin
```

或从 GitHub：

```bash
claude plugin marketplace add https://github.com/yoyo999888/my-ai-skills-plugin
claude plugin install my-ai-skills-plugin@my-ai-skills-plugin
```

验证：

```bash
claude plugin list | grep my-ai-skills-plugin
```

### Codex

Codex 通过 `.codex-plugin/plugin.json` 识别本插件，其中 `skills` 指向 `./skills/`、`hooks` 指向 `./hooks/codex-hooks.json`。把仓库放到 Codex 能加载插件的位置后即可使用其中的技能。

## 组件

| 类型 | 位置 | 示例 |
|------|------|------|
| 技能 Skill | `skills/<name>/SKILL.md` | `hello-skill` |
| 命令 Command | `commands/<name>.md` | `/hello` |
| Agent | `agents/<name>.md` | `skill-scaffolder` |
| Hook | `hooks/*.json` + `hooks/*.sh` | `session-tip.sh`（SessionStart） |

## 新增技能

1. 复制 `skills/hello-skill/` 为 `skills/<你的技能名>/`。
2. 改写 `SKILL.md` frontmatter 的 `name`（与目录名一致）和 `description`（写清「做什么 + 何时触发」，末尾附触发词）。
3. 重写正文；大段参考资料放进子目录 `references/` / `examples/` / `scripts/`。
4. 运行校验：

   ```bash
   bash scripts/validate.sh
   ```

也可以让 `skill-scaffolder` agent 直接生成骨架。

## 校验

任何结构或内容改动后：

```bash
bash scripts/validate.sh
```

## License

MIT
