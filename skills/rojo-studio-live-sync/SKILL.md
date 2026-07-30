---
name: rojo-studio-live-sync
description: 用 rojo serve 做 Roblox Studio 热同步开发的三件事——让 Studio 每次打开都自动重连服务器（placeId/gameId + roblox-studio 协议启动）、AI 如何从 `rojo serve -v` 日志判断 Studio 是否连着及改动有没有真同步进去、以及连接异常时的恢复流程（清残留进程重启服务 + 重开 Studio）。触发词：rojo 自动重连、rojo serve、rojo 热同步、studio 连不上 rojo、判断 studio 断开、文件同步成功没、rojo 日志、重启 rojo、rojo 端口占用。
---

# rojo-studio-live-sync

`rojo serve` + Studio 热同步开发的两件事：**自动重连**（少点手动 Connect）和**连接/同步状态判定**（AI 别瞎猜"已同步"）。

## 何时使用

- 要开一个 Studio 热同步开发环境，希望 Studio 一打开就自动连上 rojo。
- 改了文件后需要确认「Studio 还连着吗」「这次改动到底同步进去了吗」。
- 用户报"Studio 里没变化"，要定位是 rojo 没看见文件、还是 Studio 断了、还是 Studio 收了没应用。
- 连接坏了要恢复：重启 rojo 服务、清端口占用、重开 Studio。
- 要打开一个开发 place，需要先避免重复打开 Studio 实例。

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
4. **打开前先确认本地没有已开着的 Studio 实例**（见下方「打开 place 前必做：清掉已有实例」）。
5. **用 `roblox-studio:` 协议打开对应的远程 place**：

   ```bash
   open "roblox-studio:1+launchmode:edit+task:EditPlace+placeId:<PLACE_ID>+universeId:<UNIVERSE_ID>"
   ```

   `universeId` 就是项目文件里的 `gameId`，两者同一个值、不同叫法。（打开 Studio 的完整方式、以及只带 placeId 会报错的坑，见 `open-roblox-studio-mac` 技能。）
6. **不知道 pid / uid 时**：先去项目文件里查 `placeId` / `gameId`；查不到再问用户，**不要猜、不要随便填一个测试 place**。若只有 placeId，可用公开 API 反查：

   ```bash
   curl -s "https://apis.roblox.com/universes/v1/places/<PLACE_ID>/universe"
   ```

7. Studio 启动、加载完 place 后即自动连上，此后改文件自动推送。

### 打开 place 前必做：清掉已有实例

**每次 `open "roblox-studio:..."` 之前，先确认本机没有已经开着的 Studio 实例。** 重复打开的后果不是"多一个窗口"这么轻：

- 多个实例可能同时连同一个 rojo 服务，日志里出现多个并存的 session，`established`/`closed` 的「最后一条」判定失去意义，AI 会对着错误的实例下结论。
- Studio MCP 面对多实例需要 `set_active_studio` 选靶，选错就是在另一个窗口里取证。
- 同一个 place 被两个实例打开，各自保存会互相覆盖。

检查与处理：

```bash
pgrep -fl 'RobloxStudio' | grep -v pgrep     # 有输出 = 已有实例在跑
```

也可以用 Studio MCP 的 `list_roblox_studios` 看**连着 MCP 的**实例列表（注意：没装/没连 MCP 插件的实例不会出现在这里，`pgrep` 才是进程层的真相）。

- 已有实例打开的就是目标 place 且连接正常 → **不要重开**，直接用它。
- 已有实例是别的 place / 状态异常 → 先关掉再开新的。**关之前必须确认没有 Studio 内未保存的手动改动**（那部分不在 rojo 管辖，关掉即丢）；有疑问就问用户，不要擅自 `quit`。授权后：

  ```bash
  osascript -e 'quit app "RobloxStudio"'      # 有未保存改动会弹保存对话框，需人工处理
  pgrep -f 'RobloxStudio' || echo "已全部退出"   # 确认真的退干净了再开新的
  ```

  `quit` 是异步的，务必等到 `pgrep` 查不到进程再执行 `open`，否则新 place 可能被并进旧进程或直接被忽略。

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

---

## 技巧三：连接异常的恢复（本地开发可直接做）

本地开发环境里 rojo 服务和 Studio 都是本机进程，**AI 可以自行重启服务**，不必等用户；只有「关掉 Studio」这一步需要交代给用户或用 Studio MCP 触发。

### 判定为「连接异常」的信号

- 日志最后一条是 `closed`，但用户认为 Studio 还开着 / 插件还显示 Connected（两侧状态不一致）。
- 改文件后反复没有新 `Sending batch`，且文件确实在 `tree` 映射内。
- 日志里短时间内大量 `established` / `closed` 交替（重连风暴）。
- 端口占用报错（`Address already in use`）或 Studio 插件报连不上。
- MCP 读回的实例内容与磁盘长期不一致（推送到了，Studio 没落地）。

### 恢复步骤（按顺序，不要跳）

1. **杀掉旧 rojo 服务**——重连风暴和端口占用最常见的根因就是**残留的旧 serve 进程还占着端口**，新起的那个其实没在服务：

   ```bash
   pgrep -fl 'rojo serve'                 # 先看有几个，别盲杀
   pkill -f 'rojo serve'                  # 或按 PID: kill <PID>
   lsof -ti :34872 | xargs -r kill        # 端口还被占就按端口清
   ```

2. **重启服务并确认起来了**（日志要重新落文件，别复用旧日志——否则行数计数和"最后一条"判定会串）：

   ```bash
   rojo serve <project>.project.json --port 34872 -v > /tmp/rojo.log 2>&1 &
   sleep 1 && curl -sf "http://localhost:34872/api/rojo" > /dev/null && echo "服务已就绪"
   ```

   `/api/rojo` 通得说明 HTTP 服务活着——但**它跟 Studio 有没有连上无关**，别拿它当连接状态判据，连接状态只看日志里的 `established`/`closed`。

3. **关闭 Studio 再重新打开**。重启服务后旧的 WebSocket 已死，Studio 插件的自动重连不一定能跨服务重启恢复，**整个 Studio 重开最干净**（只点插件的 Disconnect/Connect 常常不够）。

   ```bash
   open "roblox-studio:1+launchmode:edit+task:EditPlace+placeId:<PLACE_ID>+universeId:<UNIVERSE_ID>"
   ```

   ⚠️ **关 Studio 前先确认没有未保存的手动改动**——Studio 里手改的东西不在 rojo 管辖范围，重开即丢。有疑问就先问用户，别擅自关。

   ⚠️ **确认旧实例真的退干净了再 `open`**（`pgrep -f 'RobloxStudio'` 无输出），否则会变成重复打开，日志里多 session 并存、MCP 取证选错靶。完整规则见技巧一的「打开 place 前必做：清掉已有实例」。

4. **确认恢复**：日志出现**新的** `established`（新 session uuid），然后随便改一个映射内的文件，看是否新增 `Sending batch`：

   ```bash
   grep -E 'subscription (established|closed)' /tmp/rojo.log | tail -1   # 应为 established
   ```

5. 仍然不通，才往「非连接问题」查：`tree` 映射是否覆盖该文件、Studio 打开的 place 是否与 `placeId`/`gameId` 匹配（不匹配则自动重连不生效）、Rojo 插件版本与 rojo CLI 是否同代（7.x 对 7.x）、是否处在 Play 态。
