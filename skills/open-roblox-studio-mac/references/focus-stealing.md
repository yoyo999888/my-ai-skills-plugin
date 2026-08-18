# Roblox Studio 抢焦点：原理、死路、踩坑

`rbx` 的设计依据。改这个工具前先读，能省掉大量重复调试。

## 现象

裸 `open xx.rbxl` 打开场景，Studio 会在加载过程中**多次强制把自己提到前台**。实测一个**空场景**（rojo build 的空 place）就抢了 3~4 次，时间点分散在 t=0s / 11s / 35s / 43s，每次都要手动点回来。真实大工程只会更晚更多。

抢焦点分两个来源，都会各跑一遍：

- **父进程（hub）启动完成**
- **place 编辑子进程启动完成** —— Studio 是「父进程 + 每个 place 一个独立子进程」架构（`ps` 里能看到子进程带 `-parentPid <父pid>`）

## 根因

Studio 是 **Qt 应用**。`activateIgnoringOtherApps:` 出现在 `RobloxStudio.app/Contents/Plugins/Qt5/platforms/libqcocoa.dylib`，即 Qt 的 macOS 平台插件。主二进制里另有 `activate` 和 `makeKeyAndOrderFront:`，是 Roblox 自己的代码。

`activateIgnoringOtherApps:` 是 `NSApplication` 的方法，参数为 `true` 时**不管用户当前在干什么，直接抢到最前面**。Apple 文档明确劝退，但系统会无条件照办。

关键：`open -g` 只是告诉 **LaunchServices**「启动时别激活它」，管的是*启动那一刻*；app 进程起来后在自己代码里调 activate 是完全独立的另一件事，`-g` 管不着。

> macOS 14 (Sonoma) 引入协同激活(cooperative activation)后对跨 app 强抢有所限制，但**刚被用户操作启动的 app 有正当理由激活自己**——用 `open` 拉起 Studio 恰好落在这个豁免里。

## 两条已验证的负结论（别再重查）

### 1. Qt 环境变量无效

`libqcocoa.dylib` 里确实有 `QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM`，Qt 源码中它 gate 住 `applicationDidFinishLaunching` 里的 activate 调用：

```objc
if (qEnvironmentVariableIsEmpty("QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM")) {
    [[NSApplication sharedApplication] activateIgnoringOtherApps:YES];
}
```

**实测无效**：设了之后抢焦点次数 3 → 2，在噪声范围内。因为它只关掉 Qt 启动时那一次，Roblox 自己代码里的 activate 照抢。

（`open --env VAR=VALUE` 可注入环境变量，但仅在真正冷启动 app 时生效；Studio 已在运行时 `open` 只是把文件交给现有进程，`--env` 完全无效，子进程继承的是旧环境。`launchctl setenv` 可全局设但同样解决不了问题。）

### 2. macOS 没有任何官方接口能阻止 app 自我激活

没有 API、没有用户可关的开关。**一切方案本质都是事后反制**，区别只在反应多快、反制的是「焦点」还是「可见性」。

## rbx 的设计

1. **记录锚点**（当前前台 app），`open -g -j` 启动目标（`-j` = 隐藏启动）
2. 监听 `NSWorkspace.didActivateApplicationNotification`（毫秒级，远快于轮询的 200ms）
3. Studio 抢到前台时：**先还焦点，再隐藏**
4. 加载完成后 unhide —— **unhide 不会激活**，窗口以后台形式出现，焦点纹丝不动，这是全程零闪烁的关键
5. 检测到用户主动意图就让出控制权并退出

## 必然踩中的坑

### AX 调用默认超时 6 秒，会卡死调用线程

`AXUIElementSetAttributeValue` 对刚启动、AX 服务未就绪的 app 会**阻塞到超时**（返回 `-25204 cannot complete`）。在主线程上调 → 主队列被堵 3 秒 → 期间 `didActivate` 通知完全处理不了 → 焦点一直被占着。

**必须** `AXUIElementSetMessagingTimeout(axApp, 0.15)` 压低超时，**且只在后台队列上调**。

### 收尾 unhide 会触发自己的 didUnhide 监听器

收尾时 unhide → 系统发 `didUnhideApplicationNotification` → 自己的监听器看到该 pid 仍在管辖列表 → **立刻重新隐藏**，窗口永远出不来。必须先置 `windingDown` 标志并清空管辖列表再 unhide。

（早期版本没炸，只是因为 `exit(0)` 抢在通知投递之前跑了；一加守护期就必现。）

### 锚点不能是 Studio 自己

若调用瞬间 Studio 就是前台，工具会一边判定「Studio 抢了焦点」、一边「把焦点还给 Studio」，自己跟自己打架，重试全部空转。要显式守卫：Studio 已在前台时直接放行。

### 锚点必须跟随焦点，不能冻结在启动那一刻

用户敲完命令往往会切到别的 app 干活。若把焦点还给启动时那个窗口，等于**把用户从当前工作的 app 里硬拽走**——比被 Studio 抢还烦。每当有非 Studio 的 app 被激活就更新锚点。

### 判断「用户主动切过去」不能只看有没有点击

只判「最近 1 秒内有鼠标点击」会误伤：用户在别的 app 里点鼠标，恰好撞上 Studio 自我激活，就被误判成要切过去，保护提前失效。必须**加上光标位置判断**——点击落在 Studio 窗口或 Dock 图标上才算用户意图。

用 `CGWindowListCopyWindowInfo` 取光标下的窗口所有者 pid。`kCGWindowBounds` / `kCGWindowOwnerPID` 不需要屏幕录制权限（只有窗口标题才需要）。

### NSRunningApplication.hide() 会被系统拒绝

实测恒返回 `false`。隐藏要走 Accessibility API（`kAXHiddenAttribute`）或 System Events（`set visible of process ... to false`），做多级回退。

### 只调一次 activate 不够

`activate()` 可能和 Studio 正在进行的激活撞车而抢输，而 Studio 此时已是前台就不会再发 `didActivate`，等于没有第二次机会。**激活后要验证是否真的抢回来了**，没有就继续试。

### 只隐藏新进程，别碰用户已开着的 Studio

按 pid 记录启动前已存在的 Studio 进程并全程保护。Studio 每个 place 一个独立进程，可以精确区分——隐藏用户正在编辑的另一个 place 是灾难。

## 测试方法论（血泪）

自动化测试反复出假结果，根因：

1. **测试脚本跑在终端里，终端输出会把终端 app 顶到前台**，污染焦点采样。→ 全程输出重定向到文件，测试期间终端不产生任何输出。
2. **锚点捕获卫生**：测试开始时若前台恰好是 Studio（上轮残留进程抢的），整个测试无效。→ 测前显式设定锚点并断言它不是 Studio。
3. **Studio 残留进程**让 `open` 走「交给已有进程」而非新建的路径，行为完全不同。→ 测前确认无残留（注意 hub 进程没有 `-localPlaceFile` 参数，按文件名 pkill 抓不到）。
4. **初始锚点和切换目标必须是两个不同的第三方 app**，否则「冻结锚点」和「跟随锚点」两种行为在结果上无法区分。

**验收指标**：内部拦截计数（`TOTAL_GRABS`）永远不会是 0——收到通知正是工具的工作原理。真正的指标是**外部独立采样器在保护期内看到 0 次 Studio 处于前台**。
