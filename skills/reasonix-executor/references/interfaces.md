# reasonix 接口速查（实测，v1.18.0）

## 会话文件布局

| 来源 | 落盘位置 |
|---|---|
| `reasonix run` / 交互 / `serve` | `~/.reasonix/projects/<slug>/sessions/<YYYYMMDD-HHMMSS.nnn-model>.jsonl` |
| ACP (`reasonix acp`) | `~/.reasonix/sessions/<uuid>.jsonl` |

每个会话除主 `.jsonl` 外还带一堆兄弟文件：`.events.jsonl`（脱敏事件流）、`.meta`、`.ckpt/`（checkpoint）、
`.recovery.json`、`.lease.json` + `.lease.lock`（进程占用租约）、`.event-index.json`。

- `--resume` 要给**主 `.jsonl`**，误给 `.events.jsonl` 会报 `refusing to snapshot session with content but no system message`。
- `.lease.lock` 意味着**同一会话同时只能被一个进程持有**；被占时用 `run --copy` 复制一份继续。
- `<slug>` 是路径把 `/` 换成 `-`，但会受符号链接影响，**不要自己推导**，用 `find` 定位。

## CLI 关键 flag

```
reasonix run [--dir PATH] [--model NAME] [--resume PATH|--continue] [--copy]
             [--output-format text|json|stream-json] [--events-jsonl]
             [--permission-mode manual|ask|auto|acceptEdits|dontAsk|plan|bypassPermissions]
             [--effort LEVEL] [--profile economy|balanced|delivery]
             [--max-steps N] [--metrics PATH] [--add-dir PATH] [--allowed-tools RULES] <task>
```

`--output-format json` 的返回：

```json
{"type":"result","subtype":"success","is_error":false,"duration_ms":1512,"num_turns":1,
 "result":"回答正文","session_id":"20260731-090147.725832000-deepseek-v4-flash",
 "total_cost_usd":0.00089,
 "usage":{"input_tokens":24497,"output_tokens":28,"cache_read_input_tokens":18560,"cache_creation_input_tokens":5937}}
```

其它子命令：`reasonix subagent list|create|edit|delete|try|run <name>`（预置 profile 的隔离子智能体）、
`reasonix session list|show --json`、`reasonix review --base BRANCH`、`reasonix doctor --json`。

## ACP（stdio JSON-RPC）

`reasonix acp [--model NAME]`。`initialize` 返回的能力：

```json
{"protocolVersion":1,
 "agentCapabilities":{"loadSession":true,
   "sessionCapabilities":{"list":{},"resume":{},"close":{},"delete":{}},
   "promptCapabilities":{"image":false,"audio":false,"embeddedContext":true},
   "mcpCapabilities":{"http":true,"sse":false},
   "_meta":{"reasonix.io":{"sessionSteer":{"method":"_reasonix.io/session/steer"}}}},
 "agentInfo":{"name":"reasonix","version":"v1.18.0"}}
```

要点：

- **一个进程可并发跑多个会话**，`session/prompt` 靠 `sessionId` 路由，互不阻塞（实测 3 个任务 3.1s 全完）。
- `session/new {cwd, mcpServers}` → `{sessionId}`；`session/prompt` 的结果里带 `{stopReason, transcriptPath}`。
- `session/load {sessionId, cwd, mcpServers}` 接管旧会话，但**响应里不回 `sessionId`**，要自己记；且会**重放历史 update**，收集正文前要先过滤。
- `_reasonix.io/session/steer` 是私有扩展，跑到一半插话改方向。
- 客户端没声明的能力（`fs/*`、`terminal/*`）要显式回 error，否则代理可能等死。

在编辑器里接（Zed）：

```json
"agent_servers": { "Reasonix": { "command": "reasonix", "args": ["acp"] } }
```

## serve（HTTP + SSE + 网页 UI）

```
reasonix serve [--addr HOST:PORT] [--auth none|token|password] [--token STR|--token-file PATH]
               [--password STR] [--hash-password] [--behind-proxy]
               [--resume PATH] [--model NAME] [--profile P] [--max-steps N]
               [--pid-file PATH] [--port-file PATH]
```

**没有 `--dir`**——项目目录取启动时的 cwd，所以每个执行者必须先 `cd` 到目标仓库再起。
**单会话**：`/status` 只有一份 history，`/new` 把当前会话换掉，`running` 时禁止切换。

| 端点 | 方法 | 说明 |
|---|---|---|
| `/submit` | POST `{"input":"..."}` | 提问，**202 立即返回**（异步）。字段是 `input`，写成 `text` 会返回 200 + `missing input` |
| `/events` | SSE | `turn_started` / `reasoning` / `tool_dispatch` / `approval_request` / `message` / `usage` |
| `/status` | GET | `running`、`goalStatus`、`cwd`、cacheHit/Miss、余额 |
| `/history` | GET | 完整消息数组（含 system prompt） |
| `/sessions` | GET | 存档列表：`name` / `path` / `title` / `turns` / `current` |
| `/approve` | POST `{"id":"1","decision":"approve"}` | 放行单次工具调用 |
| `/tool-approval-mode` | POST `{"mode":"auto"}` | 免审批，无人值守必设 |
| `/new` `/resume` `/delete-session` | POST | 新建 / `{"path":...}` 切换 / `{"name":...}` 删除 |
| `/cancel` | POST | 打断当前 turn |
| `/fork` | POST `{"turn":N,"name":""}` | 从某轮分叉 |
| `/checkpoints` `/rewind` | GET / POST `{"turn":N,"scope":...}` | 回滚 |
| `/compact` `/summarize` | POST | 压缩上下文（`summarize` 收 `{"turn":N,"mode":"from"\|"upto"}`） |
| `/goal` `/todos` `/plan` `/models` `/branches` `/tree` `/memory` `/mcp` `/hooks` `/skill` `/help` `/answer` `/verbose` | — | 其余面板功能 |

## 配置

`reasonix.toml` 优先级：flag > `./reasonix.toml` > `~/.reasonix/config.toml` > 内置默认。
密钥通过 `api_key_env` 从环境变量注入。`reasonix setup` 交互生成配置。
