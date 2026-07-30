---
name: rojo-studio-live-sync
description: 用 rojo serve 做 Roblox Studio 热同步开发的完整规程——固定 34872 端口、Studio 自动重连（需先手工连一次建缓存 + placeId/gameId + roblox-studio 协议启动）、从 `rojo serve -v` 日志判断 Studio 是否连着及改动有没有真同步进去、以及连接异常的恢复（重启服务必须连带重启 Studio）。触发词：rojo 自动重连、rojo serve、rojo 热同步、studio 连不上 rojo、判断 studio 断开、文件同步成功没、rojo 日志、重启 rojo、rojo 端口占用、34872。
---

# rojo-studio-live-sync

`rojo serve` + Roblox Studio 热同步开发的操作规程：怎么起、怎么判断连没连上／同步没同步、坏了怎么恢复。

## 何时使用

- 要开一个 Studio 热同步开发环境，希望 Studio 一打开就自动连上 rojo。
- 改了文件后要确认「Studio 还连着吗」「这次改动到底同步进去了吗」。
- 用户报"Studio 里没变化"，要定位是 rojo 没看见文件、还是 Studio 断了、还是 Studio 收了没应用。
- 连接坏了要恢复：重启 rojo 服务、清端口占用、重开 Studio。

---

## 四条铁律

1. **端口固定 `34872`**。所有项目的 rojo 服务统一占用 34872，不给不同项目分配不同端口。好处是判定、curl、日志、Studio 插件配置全都不用记项目差异；代价是**同一时刻只能有一个 rojo 服务在跑**——换项目必须先停掉上一个。看到 `Address already in use` 就是上一个还活着，去清它，**不要换端口绕开**（换了端口 Studio 插件那边就连不上了）。

2. **自动连接的前提：这个 place 至少手工连过一次**。Rojo 插件的自动重连是靠上一次成功连接留下的缓存（place ↔ 服务地址）恢复的，**全新的 place 第一次必须由用户手动点一次 Connect**，之后才谈得上自动。所以新 place 首次开工不要期待自动连上，也不要因为没自动连就去重启服务排查——先确认用户手连过。

3. **重启 rojo 服务 ⇒ 必须连带关闭并重开 Studio**。服务重启后旧 WebSocket 已死，Studio 插件的自动重连不保证能跨服务重启恢复，而且 Studio 侧可能停在「显示 Connected 但实际不通」的假状态。只点插件的 Disconnect/Connect 常常不够——**整个 Studio 重开是唯一可靠路径**。

4. **`Sending batch` ≠ Studio 已应用**。日志只能证明 rojo 把 patch 发出去了。「Studio 里已经是新代码」这个结论必须去 Studio 内存态取证，见 §2.4。

---

## 1. 标准启动流程

### 1.1 一次性设置

两件事都得用户在 Studio 里做一次，AI 代不了：

- **打开自动重连开关**：Studio 的 Rojo 插件设置里的 **auto-connect / reconnect**。
- **手工连一次，建立缓存**：服务起好后，让用户在插件里点一次 **Connect** 并确认连上（日志出现 `established`）。这一次是自动重连的前提（铁律 2）——缓存建立后，之后每次打开这个 place 才会自动连。换了 place、换了端口、或用户清过插件设置，都要重新手连一次。
- 在 rojo 项目文件（`*.project.json`）顶层写死开发 place 与端口：

  ```jsonc
  {
    "name": "MyProject",
    "servePort": 34872,
    "placeId": <PLACE_ID>,
    "gameId": <UNIVERSE_ID>,
    "tree": { /* ... */ }
  }
  ```

  自动重连靠 place 身份匹配：Studio 打开的 place 必须与项目声明的 `placeId` 一致，否则插件不会自动连（或弹 place mismatch 警告）。`servePort` 写进项目文件后，`rojo serve` 不带 `--port` 也走 34872。

- **不知道 pid / uid 时**：先去项目文件里查 `placeId` / `gameId`；查不到再问用户，**不要猜、不要随便填一个测试 place**。`universeId` 就是 `gameId`，同一个值、两种叫法。只有 placeId 时可用公开 API 反查：

  ```bash
  curl -s "https://apis.roblox.com/universes/v1/places/<PLACE_ID>/universe"
  # {"universeId": <UNIVERSE_ID>}
  ```

### 1.2 每次启动（顺序不能反）

**① 确认 34872 是干净的。**

```bash
lsof -ti :34872          # 有输出说明端口被占
pgrep -fl 'rojo serve'   # 看是哪个项目的服务还活着
```

被占且是**同一个项目**的服务、工作正常 → 直接复用，跳到 ③。是**别的项目**或状态可疑 → 先杀掉（见 §3.2 ①）。

**② 起服务，日志落文件。**

```bash
rojo serve <project>.project.json --port 34872 -v > /tmp/rojo.log 2>&1 &
sleep 1 && curl -sf "http://localhost:34872/api/rojo" > /dev/null && echo "服务已就绪"
```

- **必须 `-v`**：没有 `-v` 就没有连接／推送日志，§2 的判定全部失效。
- **必须落文件**：挂在前台终端里的滚动输出 AI 读不到。
- **不要在管道里 grep 过滤**：判定依赖「最后一条相关事件」的时序，过滤掉上下文更难判断；日志量极小（只在连接变化和推送时打点），全量留着，判定时再 grep。
- 每次重启服务**换新日志文件或先清空**，别复用旧日志——否则行数计数和「最后一条」判定会串。
- `/api/rojo` 通了只说明 HTTP 服务活着，**跟 Studio 有没有连上无关**，别拿它当连接判据。

**③ 打开 place 前，先清掉已有 Studio 实例。** 见 §1.3。

**④ 用 `roblox-studio:` 协议打开 place。**

```bash
open "roblox-studio:1+launchmode:edit+task:EditPlace+placeId:<PLACE_ID>+universeId:<UNIVERSE_ID>"
```

（打开 Studio 的完整方式、以及只带 placeId 会报错的坑，见 `open-roblox-studio-mac` 技能。）

**⑤ 确认连上。** 日志出现 `established`（见 §2.2）。此后改文件自动推送。若一直没有 `established`，先想「这个 place 手工连过没有」（铁律 2），没连过就让用户点一次 Connect，别去重启服务瞎折腾。

### 1.3 打开 place 前必做：清掉已有实例

**每次 `open "roblox-studio:..."` 之前，先确认本机没有已经开着的 Studio 实例。** 重复打开的后果不只是多一个窗口：

- 多个实例可能同时连同一个 rojo 服务，日志里多个 session 并存，`established`/`closed` 的「最后一条」判定失去意义，AI 会对着错误的实例下结论。
- Studio MCP 面对多实例需要 `set_active_studio` 选靶，选错就是在另一个窗口里取证。
- 同一个 place 被两个实例打开，各自保存会互相覆盖。

```bash
pgrep -fl 'RobloxStudio' | grep -v pgrep     # 有输出 = 已有实例在跑
```

Studio MCP 的 `list_roblox_studios` 只能看到**连着 MCP 的**实例；没装／没连插件的实例不会出现，`pgrep` 才是进程层的真相。

- 已有实例打开的就是目标 place 且连接正常 → **不要重开**，直接用它。
- 已有实例是别的 place / 状态异常 → 先关掉再开新的：

  ```bash
  osascript -e 'quit app "RobloxStudio"'
  pgrep -f 'RobloxStudio' || echo "已全部退出"
  ```

  ⚠️ **关之前必须确认没有 Studio 内未保存的手动改动**——Studio 里手改的东西不在 rojo 管辖范围，关掉即丢。有疑问就问用户，不要擅自 `quit`。
  ⚠️ **`quit` 是异步的**，有未保存改动还会弹保存对话框（需人工处理）。务必等到 `pgrep` 查不到进程再 `open`，否则新 place 可能被并进旧进程或直接被忽略。

---

## 2. 判定连接状态与同步状态

### 2.1 日志里的三种关键行

以实测日志为例（改了两次文件，然后关掉 Studio）：

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

### 2.2 连接状态

取 `established` / `closed` 两类行中**时间上最后出现的那一条**：`established` 在后 = 当前连着；`closed` 在后 = 当前已断；两者都没有 = 从未连过。

```bash
grep -E 'subscription (established|closed)' /tmp/rojo.log | tail -1
```

留意 session uuid：断开后重连会出现**新 uuid**，说明是新连接而非旧连接恢复，Studio 侧状态可能已被全量覆盖。

### 2.3 同步状态

编辑文件后，日志**新增**一条 `Sending batch` 才说明推送发生了。判定方式是记录编辑前的行数，编辑后再数：

```bash
before=$(grep -c 'Sending batch' /tmp/rojo.log)
# ...编辑文件...
sleep 1
after=$(grep -c 'Sending batch' /tmp/rojo.log)   # 需 > before
```

给文件系统事件留约 1s，别改完立刻判「没同步」。

**改了文件但没有新 `Sending batch`**，按顺序排查：

1. 没有活跃连接（最后一条是 `closed`）→ 改动只进了 rojo 的内存快照，Studio 侧毫无变化；重连后才会拿到全量。
2. 该文件不在项目 `tree` 映射范围内，或被 `globIgnorePaths` 排除 → rojo 根本没在看它。
3. 改的根本不是被映射的文件（如 `.gitignore`、文档）→ 不产生实例差异，本来就不该有推送。

### 2.4 ⚠️ 边界：`Sending batch` 只到 rojo 出口

`Sending batch` 不证明 Studio 收下并写进了 DataModel。Studio 侧可能因为插件报错、实例被锁、或处于 Play 态（Rojo 不改运行中的实例）而没落地。所以：

- **「rojo 侧已推送」**——可以只凭日志断言。
- **「Studio 里已经是新代码/新实例」**——**必须去 Studio 内存态取证**：
  - `mcp__Roblox_Studio__script_read` / `inspect_instance` 读回目标实例，比对内容；
  - `get_console_output` 看 Rojo 插件有没有报错；
  - `get_studio_state` 确认不在 Play 态。

这与本项目集的「三态取证」纪律一致：文件态、引擎内存态、代码态可能互不一致，落在引擎行为上的结论只有引擎内存态算证据。日志属于「进程态」，跟引擎内存态是两回事。

---

## 3. 连接异常的恢复

本地开发环境里 rojo 服务和 Studio 都是本机进程，**AI 可以自行重启服务**，不必等用户；只有「关 Studio」这一步涉及未保存内容，需要先确认。

### 3.1 判定为「连接异常」的信号

- 日志最后一条是 `closed`，但用户认为 Studio 还开着 / 插件还显示 Connected（两侧状态不一致）。
- 改文件后反复没有新 `Sending batch`，且文件确实在 `tree` 映射内。
- 短时间内大量 `established` / `closed` 交替（重连风暴）。
- 端口 34872 报 `Address already in use`，或 Studio 插件报连不上。
- MCP 读回的实例内容与磁盘长期不一致（推送到了，Studio 没落地）。

### 3.2 恢复步骤（按顺序，不要跳）

**① 杀掉旧 rojo 服务。** 重连风暴和端口冲突最常见的根因就是**残留的旧 serve 进程还占着 34872**，新起的那个其实没在服务：

```bash
pgrep -fl 'rojo serve'                 # 先看有几个，别盲杀
pkill -f 'rojo serve'                  # 或按 PID: kill <PID>
lsof -ti :34872 | xargs -r kill        # 端口还被占就按端口清
lsof -ti :34872 || echo "34872 已释放"  # 确认干净
```

固定端口的代价在这里体现：换项目前必须清掉上一个项目的服务。**不要因为端口被占就换端口**（铁律 1）。

**② 重启服务**（同 §1.2 ②，记得用新日志文件）。

**③ 关闭 Studio 再重新打开**——这是铁律 2，服务重启后必做，不是可选项。

```bash
osascript -e 'quit app "RobloxStudio"'
pgrep -f 'RobloxStudio' || echo "已全部退出"
open "roblox-studio:1+launchmode:edit+task:EditPlace+placeId:<PLACE_ID>+universeId:<UNIVERSE_ID>"
```

关之前确认没有未保存的手动改动；确认旧实例真的退干净了再 `open`（否则变成重复打开）。完整规则见 §1.3。

**④ 确认恢复。** 日志出现**新的** `established`（新 session uuid），然后改一个映射内的文件，看是否新增 `Sending batch`：

```bash
grep -E 'subscription (established|closed)' /tmp/rojo.log | tail -1   # 应为 established
```

**⑤ 仍然不通**，按这个顺序往「非连接问题」查：

- 这个 place 有没有手工连过？没有则自动重连本来就不成立（铁律 2），让用户点一次 Connect。
- Studio 打开的 place 是否与 `placeId`/`gameId` 匹配？不匹配则自动重连不生效。
- `tree` 映射是否覆盖该文件。
- Rojo 插件版本与 rojo CLI 是否同代（7.x 对 7.x）。
- 是否处在 Play 态。

---

## 4. 快速自检脚本

```bash
LOG=/tmp/rojo.log
echo "服务进程: $(pgrep -fl 'rojo serve' | tr '\n' ' ')"
echo "端口 34872: $(lsof -ti :34872 | tr '\n' ' ')"
echo "Studio 实例: $(pgrep -f 'RobloxStudio' | wc -l | tr -d ' ') 个"
echo "连接: $(grep -E 'subscription (established|closed)' $LOG | tail -1)"
echo "推送次数: $(grep -c 'Sending batch' $LOG)"
```
