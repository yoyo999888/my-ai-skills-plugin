---
name: rojo-studio-live-sync
description: 用 rojo serve 做 Roblox Studio 热同步开发的两个关键技巧——让 Studio 每次打开都自动重连服务器（placeId/gameId + roblox-studio 协议启动），以及 AI 如何从 `rojo serve -v` 日志判断 Studio 是否连着、改的文件有没有真同步进去。触发词：rojo 自动重连、rojo serve、rojo 热同步、studio 连不上 rojo、判断 studio 断开、文件同步成功没、rojo 日志。
---

# rojo-studio-live-sync

`rojo serve` + Studio 热同步开发的两件事：**自动重连**（少点手动 Connect）和**连接/同步状态判定**（AI 别瞎猜"已同步"）。

## 何时使用

- 要开一个 Studio 热同步开发环境，希望 Studio 一打开就自动连上 rojo。
- 改了文件后需要确认「Studio 还连着吗」「这次改动到底同步进去了吗」。
- 用户报"Studio 里没变化"，要定位是 rojo 没看见文件、还是 Studio 断了、还是 Studio 收了没应用。

---

## 技巧一：Studio 自动重连 rojo

目标：每次打开 Studio 自动连上本地 rojo 服务，不用手点 Rojo 插件的 Connect。

1. **一次性设置**：提醒用户在 Studio 的 Rojo 插件设置里打开 **自动重连（auto-connect / reconnect）** 开关。这一步是插件 UI，AI 做不了，必须让用户手动开。
2. **在 rojo 项目文件里写死开发 place**（`*.project.json` 顶层）：

   ```jsonc
   {
     "name": "MyProject",
     "placeId": <PLACE_ID>,
     "gameId": <UNIVERSE_ID>,
     "tree": { /* ... */ }
   }
   ```

   自动重连靠 place 身份匹配：Studio 打开的 place 必须与项目声明的一致，否则插件不会自动连（或弹"place mismatch"警告）。
3. **先起服务，再开 Studio**：

   ```bash
   rojo serve <project>.project.json --port 34872
   ```

   顺序反了，Studio 启动时没服务可连，自动重连要等下一次轮询或干脆需要手动点。
4. **用 `roblox-studio:` 协议打开对应的远程 place**：

   ```bash
   open "roblox-studio:1+launchmode:edit+task:EditPlace+placeId:<PLACE_ID>+universeId:<UNIVERSE_ID>"
   ```

   `universeId` 就是项目文件里的 `gameId`，两者同一个值、不同叫法。（打开 Studio 的完整方式、以及只带 placeId 会报错的坑，见 `open-roblox-studio-mac` 技能。）
5. **不知道 pid / uid 时**：先去项目文件里查 `placeId` / `gameId`；查不到再问用户，**不要猜、不要随便填一个测试 place**。若只有 placeId，可用公开 API 反查：

   ```bash
   curl -s "https://apis.roblox.com/universes/v1/places/<PLACE_ID>/universe"
   ```

6. Studio 启动、加载完 place 后即自动连上，此后改文件自动推送。

---

## 技巧二：判断 Studio 连接与同步状态

### 怎么启动才能看到状态

用 `-v` 起服务，并且**把日志落到文件**（不要只挂在终端里，AI 读不到滚动输出）：

```bash
rojo serve <project>.project.json --port 34872 -v > /tmp/rojo.log 2>&1 &
```

不要在管道里做 grep 过滤：判定需要「最后一条相关事件」的时序，过滤掉上下文反而更难判断。日志量很小（只在连接变化和推送时打点），全量留着即可，判定时再 `grep`。

### 日志里三种关键行

以本次实测的日志为例（改了两次文件，然后关掉 Studio）：

```
Visit http://localhost:34872/ in your browser for more information.
[DEBUG librojo::web::api] WebSocket subscription established for session <uuid>   ← Studio 连上了
[DEBUG librojo::web::api] Sending batch of messages over WebSocket subscription   ← 第 1 次改动已推给 Studio
[DEBUG librojo::web::api] Sending batch of messages over WebSocket subscription   ← 第 2 次改动已推给 Studio
[DEBUG librojo::web::api] WebSocket subscription closed by client                 ← Studio 断开
```

| 日志行 | 含义 |
|---|---|
| `WebSocket subscription established for session <uuid>` | 有 Studio 客户端连上（每次重连一个新 session id） |
| `Sending batch of messages over WebSocket subscription` | rojo 检测到文件变更**并已推送**给已连接客户端 |
| `WebSocket subscription closed by client` | 客户端主动断开（关 Studio、点 Disconnect、切 place） |

### AI 的判定规则

**连接状态**：取 `established` / `closed` 两类行中**时间上最后出现的那一条**——`established` 在后 = 当前连着；`closed` 在后 = 当前已断。两者都没有 = Studio 从未连过。

```bash
grep -E 'subscription (established|closed)' /tmp/rojo.log | tail -1
```

注意 session id：断开后重连会出现新的 `established`（新 uuid），说明是**新连接**而非旧连接恢复，Studio 侧状态可能已被重载覆盖。

**同步状态**：编辑文件后，日志**新增**一条 `Sending batch` 才说明推送发生了。判定方式是记录编辑前的行数，编辑后再数：

```bash
before=$(grep -c 'Sending batch' /tmp/rojo.log)
# ...编辑文件...
after=$(grep -c 'Sending batch' /tmp/rojo.log)   # 需 > before
```

给文件系统事件留一点时间（约 1s 量级）再数，别改完立刻判"没同步"。

**改了文件但没有新 `Sending batch`**，按这个顺序排查：

1. 没有活跃连接（最后一条是 `closed`）→ 改动只进了 rojo 的内存快照，Studio 侧毫无变化；重连后 Studio 才会拿到全量。
2. 该文件不在项目 `tree` 映射范围内，或被 `globIgnorePaths` 排除 → rojo 根本没在看它。
3. 改动内容对 rojo 不产生实例差异（例如只改了注释外的空白？不会——任何 Source 变化都算差异；但改的是 `.gitignore` 之类非映射文件就不算）。

### ⚠️ 最重要的一条：`Sending batch` ≠ Studio 已应用

`Sending batch` 只证明 **rojo 把 patch 发出去了**，不证明 Studio 收下并写进了 DataModel。Studio 侧可能因为插件报错、实例被锁、脚本正在运行（Play 态下 Rojo 不改运行中的实例）而没落地。

所以：

- **"rojo 侧已推送"**——可以只凭日志断言。
- **"Studio 里已经是新代码/新实例"**——**必须去 Studio 内存态取证**，不能凭日志断言。用 Studio MCP 实测：
  - `mcp__Roblox_Studio__script_read` / `inspect_instance` 读回目标实例，比对内容；
  - `get_console_output` 看 Rojo 插件有没有报错；
  - `get_studio_state` 确认不在 Play 态。

这条与本项目集的「三态取证」纪律一致：文件态、引擎内存态、代码态可能互不一致，落在引擎行为上的结论只有引擎内存态算证据。

### 快速自检脚本

```bash
LOG=/tmp/rojo.log
echo "连接: $(grep -E 'subscription (established|closed)' $LOG | tail -1)"
echo "推送次数: $(grep -c 'Sending batch' $LOG)"
```
