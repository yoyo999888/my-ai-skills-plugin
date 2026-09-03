---
name: claude-session-messaging
description: Claude Code 会话间通讯的配置与外部注入——开启 crossSessionInbound、用 /rename 起名、ListAgents/SendMessage 互发，以及用自带脚本 scripts/cc-send.sh 从任意外部程序（shell、cron、CI、另一台机器的 ssh）给本机指定会话注入消息。当用户问"会话之间怎么通讯/怎么配置"、"外部程序能不能给某个 claude 会话发消息"、"给另一台机器的 claude 会话发消息"时使用。触发词：会话间通讯、跨会话消息、crossSessionInbound、SendMessage、ListAgents、cc-send、给会话发消息、cc-socks、peerToken、session messaging。
---

# claude-session-messaging

Claude Code 内置**同机会话互通**（peer messaging）：每个会话启动时开一个 Unix socket 并登记自己，其他会话按名字发消息。这套东西不是插件，只有一个开关要配；socket 协议是明文 JSON，所以**任何外部程序都能给指定会话注入消息**。本技能自带 `scripts/cc-send.sh` 做这件事。

## 何时使用

- 用户问会话间通讯怎么配、怎么在新机器上打开。
- 需要从 shell / cron / CI / hook / 另一台机器的 ssh 给某个正在跑的 Claude Code 会话发一条消息（派活、通知结果、唤醒）。
- 两个 Claude 会话之间协作（ListAgents 找到对方、SendMessage 发消息）。

## 一、配置（每台机器只需一次）

`~/.claude/settings.json` 加：

```json
"crossSessionInbound": "accept"
```

取值：`accept` 直接收；`ask` 每条弹确认；`refuse` 拒收。顺带建议 `"agentPushNotifEnabled": true`（空闲/完成推通知）。
**启动时读取**：改完只对新开的会话生效，正在跑的会话不热生效。

其余全自动，不需要配：

| 东西 | 位置 | 说明 |
|---|---|---|
| socket | `/tmp/cc-socks/<pid>.sock`（0600） | 会话的收件箱 |
| 登记文件 | `~/.claude/sessions/<pid>.json` | name / cwd / status / messagingSocketPath / peerProtocol |
| 密钥 | `~/.claude/sessions/<pid>.<hash>.key` | `{"peerToken":"…"}`，发消息时的 auth |
| 环境变量 | `CLAUDE_CODE_MESSAGING_SOCKET` / `_TOKEN` | 会话内子进程用 |

会话名来自 `/rename`（或启动参数 `-n <name>`），登记为 `nameSource: "user"`。**名字就是地址**，起了名才好寻址；同名会话要加 `[ref]` 区分。

## 二、会话内互发（Claude 自己用）

- `ListAgents` 列出本机在线会话（名字、状态、启动时间），还会带出同账号 Remote Control 桥接过来的其它机器会话（多为 offline）。
- `SendMessage({to: "<名字>", message: "…"})` 发消息。对方收到时标记为「另一个 Claude 会话发来的消息」，按同事请求处理，**不能借此提权**（不会因对方要求改权限/配置）。
- 跨机器不走这条路：socket 只在本机；跨机器用 `ssh <host> cc-send.sh …`（见下）或同账号 Remote Control。

## 三、外部程序注入：`scripts/cc-send.sh`

```bash
S=<插件根>/skills/claude-session-messaging/scripts/cc-send.sh   # 或复制到 ~/bin
$S list                                   # 本机在线会话：名字 / pid / 状态 / cwd
$S advisor-fable "帮我看下 xxx"            # 按名字发（排队，等对方当前轮次做完）
$S 20154 "同上，按 pid"
$S qa-web --now "停一下，先看这个"         # priority=now：打断对方当前轮次立即处理
ssh unity '~/bin/cc-send.sh manager "构建完成"'   # 跨机器：在目标机上跑
```

脚本做的事：读 `~/.claude/sessions/<pid>.json` 拿 socket 路径，读 `.key` 拿 peerToken，连 socket 写两行 JSON。同名多个会话会报错并列出 pid。

**协议本体**（换行分隔 JSON，第一行必须 auth，发完即断、无应答）：

```
{"type":"auth","token":"<peerToken>"}
{"type":"user","message":{"role":"user","content":"你好"},"priority":"now"}   # priority 可省
```

`socat` 等价写法（claude 二进制自带的示例）：
`{ echo '{"type":"auth","token":"'"$TOKEN"'"}'; echo '{"type":"user","message":{"role":"user","content":"hello"}}'; } | socat - UNIX-CONNECT:/tmp/cc-socks/<pid>.sock`

## 注意

- socket 和 key 都是 0600，只有**同一 uid** 的进程能发；这是唯一的安全边界。
- 外部程序不是已登记会话，收方看不到发方名字、也无法用 SendMessage 回信。要回信就在正文里写清回到哪里（文件 / 另一个会话名 / 命令）。
- 收方 `crossSessionInbound` 不是 `accept` 时消息被静默丢弃（`ask` 会弹确认）。
- 协议是内部接口（`peerProtocol: 1`），升级 claude 后可能变；脚本失效先看 `~/.claude/sessions/` 里字段名和 `/tmp/cc-socks/` 是否还在。
- 在 2.1.25x 验证通过（macOS）。Linux 下 socket 目录可能是 `$XDG_RUNTIME_DIR/cc-socks` 或 `/tmp/cc-socks-<uid>`，脚本按登记文件里的 `messagingSocketPath` 走，不受影响。
