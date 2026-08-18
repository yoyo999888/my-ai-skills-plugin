// rbx — 静默打开 Roblox Studio，不让它抢焦点。
//
// 背景：Roblox Studio 是 Qt 应用，打开一个 place 的过程中会多次强制激活自己
// （Qt 插件 libqcocoa 里的 activateIgnoringOtherApps: 一次，Roblox 自己代码里
// 的 activate / makeKeyAndOrderFront: 还有若干次）。macOS 没有任何官方接口能
// 禁止一个 app 自我激活，唯一能做的是事后反制。用 shell 轮询反制延迟约 200ms，
// 肉眼能看见闪烁；这里改用 NSWorkspace 的激活通知，反应在毫秒级。
//
// 两种模式：
//   --mode hide  (默认) 新开的 Studio 进程全程隐藏，加载完再 unhide。
//                unhide 不会激活，窗口直接以后台形式出现，全程零闪烁。
//   --mode focus 窗口正常可见，只是每次它抢焦点就立刻把焦点切回原应用。
//
// 安全性：只管本次新启动的 Studio 进程（按 PID 跟踪）。已经开着的 Studio
// 窗口（比如你正在编辑的其它 place）绝不会被隐藏。

import AppKit
import ApplicationServices

let studioBundleID = "com.Roblox.RobloxStudio"

// ---------- 参数解析 ----------
let usage = """
用法: rbx [选项] [文件或URI]

  --mode hide|focus   hide=加载期间隐藏(默认, 零闪烁)  focus=可见但保持焦点
  --duration <秒>     监控时长, 默认 90
  --foreground, -f    前台运行(调试用)。默认自我后台化, 命令立刻返回
  --verbose, -v       前台模式下打印事件日志
  --help              显示帮助

默认行为和 open 一致: 命令立刻返回, 守护进程在后台跑。
日志: ~/Library/Logs/rbx.log
随时中止: pkill -x rbx
你只要用鼠标点一下 Studio, 它会立刻让出控制权并自动退出。

示例:
  rbx ~/place.rbxl
  rbx --mode focus ~/place.rbxl
  rbx "roblox-studio:1+launchmode:edit+task:EditPlace+placeId:123+universeId:456"
  rbx                        # 只启动 Studio 本身
"""

var duration: TimeInterval = 90
var mode = "hide"
var verbose = false
var target: String? = nil
var runInForeground = false
var isDaemonChild = false

let logPath = NSHomeDirectory() + "/Library/Logs/rbx.log"

var argv = Array(CommandLine.arguments.dropFirst())
var i = 0
while i < argv.count {
    let a = argv[i]
    switch a {
    case "--help", "-h":
        print(usage); exit(0)
    case "--verbose", "-v":
        verbose = true
    case "--foreground", "-f":
        runInForeground = true
    case "--__daemon":          // 内部标记，用户不该直接用
        isDaemonChild = true
    case "--mode":
        i += 1
        if i < argv.count { mode = argv[i] } else { FileHandle.standardError.write("--mode 缺少参数\n".data(using: .utf8)!); exit(2) }
    case "--duration":
        i += 1
        if i < argv.count, let d = Double(argv[i]) { duration = d } else { FileHandle.standardError.write("--duration 缺少或非法参数\n".data(using: .utf8)!); exit(2) }
    default:
        target = a
    }
    i += 1
}

guard mode == "hide" || mode == "focus" else {
    FileHandle.standardError.write("--mode 只能是 hide 或 focus\n".data(using: .utf8)!)
    exit(2)
}

// ---------- 自我后台化：行为对齐 open，命令立刻返回 ----------
// 父进程 spawn 一个带 --__daemon 标记的自己，然后立刻退出；
// 子进程 setsid() 脱离终端会话，终端关掉也不会被 SIGHUP 带走。
if !runInForeground && !isDaemonChild {
    let exePath = Bundle.main.executablePath ?? CommandLine.arguments[0]
    let p = Process()
    p.executableURL = URL(fileURLWithPath: exePath)
    p.arguments = Array(CommandLine.arguments.dropFirst()) + ["--__daemon"]

    if !FileManager.default.fileExists(atPath: logPath) {
        FileManager.default.createFile(atPath: logPath, contents: nil)
    }
    let fh = try? FileHandle(forWritingTo: URL(fileURLWithPath: logPath))
    fh?.seekToEndOfFile()
    p.standardOutput = fh ?? FileHandle.nullDevice
    p.standardError = fh ?? FileHandle.nullDevice
    p.standardInput = FileHandle.nullDevice

    do {
        try p.run()
        exit(0)                    // 立刻返回，不等子进程
    } catch {
        // 派生失败就退化成前台跑，至少功能不丢
        FileHandle.standardError.write("后台派生失败，改为前台运行: \(error)\n".data(using: .utf8)!)
    }
}

if isDaemonChild {
    setsid()                       // 脱离终端会话
    verbose = true                 // 后台模式一律留日志，便于事后排查
}

func log(_ s: String) {
    if verbose {
        let t = String(format: "%.3f", Date().timeIntervalSince(startTime))
        let stamp = isDaemonChild ? " \(Date())" : ""
        print("[\(t)s]\(stamp) \(s)")
        fflush(stdout)
    }
}

let startTime = Date()
let ws = NSWorkspace.shared

// ---------- 本进程设为不可激活，免得它自己干扰焦点 ----------
let nsapp = NSApplication.shared
nsapp.setActivationPolicy(.prohibited)

// ---------- 记录锚点应用（调用瞬间的前台应用）----------
guard let anchor = ws.frontmostApplication else {
    FileHandle.standardError.write("读不到当前前台应用，放弃。\n".data(using: .utf8)!)
    exit(1)
}
let anchorPID = anchor.processIdentifier

// 锚点不能是 Studio 自己。否则工具会一边判定"Studio 抢了焦点"、一边又
// "把焦点还给 Studio"，自己跟自己打架，重试全部空转（实测踩过）。
if anchor.bundleIdentifier == studioBundleID {
    FileHandle.standardError.write(
        "Roblox Studio 当前就是前台应用，没有需要保护的焦点，直接放行。\n".data(using: .utf8)!)
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
    p.arguments = target.map { [$0] } ?? ["-b", studioBundleID]
    try? p.run()
    p.waitUntilExit()
    exit(0)
}
log("初始锚点: \(anchor.localizedName ?? "?") (pid \(anchorPID))")

// ⚠️ 锚点必须跟随焦点，不能冻结在启动那一刻。
// 用户敲完命令往往会切到别的 app 干活；若把焦点还给启动时那个窗口，
// 等于把用户从当前工作的 app 里硬拽走 —— 比被 Studio 抢还烦（实测踩过）。
// 所以每当有非 Studio 的 app 被激活，就把它记成新的锚点。
var currentAnchorPID = anchorPID

// ---------- 记录启动前已存在的 Studio 进程，之后绝不动它们 ----------
var preExistingStudioPIDs = Set<pid_t>()
for a in NSRunningApplication.runningApplications(withBundleIdentifier: studioBundleID) {
    preExistingStudioPIDs.insert(a.processIdentifier)
}
log("已存在的 Studio 进程(将被保护, 不隐藏): \(preExistingStudioPIDs.sorted())")
log("Accessibility 授权(决定隐藏走快路还是慢路): \(AXIsProcessTrusted())")

// 本次新出现的 Studio 进程
var managedPIDs = Set<pid_t>()
var grabCount = 0

// 收尾标志。收尾时会 unhide，而 unhide 又会触发 didUnhide 监听器 ——
// 不设这个标志的话，监听器会把刚放出来的窗口立刻重新隐藏回去，窗口永远出不来。
var windingDown = false
let guardPeriod: TimeInterval = 8   // unhide 之后再守一会儿焦点，但不再隐藏

// ---------- 隐藏/取消隐藏：三级回退 ----------
// 1) Accessibility API —— 同步、亚毫秒，最快
// 2) NSRunningApplication.hide() —— 实测常被系统拒绝(返回 false)，仅作备选
// 3) System Events —— 实测可用，但要 spawn osascript，约 50-100ms
let axQueue = DispatchQueue(label: "rbx.ax")

// ⚠️ AX 调用默认消息超时是 6 秒。目标 app 刚启动、AX 服务还没就绪时，
// AXUIElementSetAttributeValue 会把调用线程整个卡住等超时 —— 实测卡了 3 秒，
// 期间主队列上的 didActivate 通知完全处理不了，焦点就一直被 Studio 占着。
// 所以必须显式压到 150ms，而且只在后台队列上调。
func axSetHidden(_ pid: pid_t, _ hidden: Bool) -> Bool {
    let axApp = AXUIElementCreateApplication(pid)
    AXUIElementSetMessagingTimeout(axApp, 0.15)
    return AXUIElementSetAttributeValue(axApp, kAXHiddenAttribute as CFString,
                                        hidden ? kCFBooleanTrue : kCFBooleanFalse) == .success
}

func sysEventsSetHidden(_ pid: pid_t, _ hidden: Bool) {
    let src = "tell application \"System Events\" to set visible of "
            + "(first application process whose unix id is \(pid)) to \(hidden ? "false" : "true")"
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
    p.arguments = ["-e", src]
    p.standardOutput = FileHandle.nullDevice
    p.standardError = FileHandle.nullDevice
    try? p.run()
}

// 在后台队列上反复试 AX 直到成功或超时，超时才回退 System Events。
// 全程不碰主线程，保证 didActivate 通知能被毫秒级处理。
func setHiddenAsync(pid: pid_t, _ hidden: Bool, timeout: TimeInterval = 3.0, tag: String = "") {
    axQueue.async {
        let deadline = Date().addingTimeInterval(timeout)
        var tries = 0
        while Date() < deadline {
            if hidden && windingDown { return }
            tries += 1
            if axSetHidden(pid, hidden) {
                log("\(tag)pid \(pid) \(hidden ? "hide" : "unhide") via ax (第\(tries)次尝试)")
                return
            }
            Thread.sleep(forTimeInterval: 0.05)
        }
        sysEventsSetHidden(pid, hidden)
        log("\(tag)pid \(pid) \(hidden ? "hide" : "unhide") AX 超时，回退 System Events")
    }
}

// ---------- 区分「Studio 自我激活」和「用户主动点过去」----------
// 两者在系统看来是同一个 didActivate 通知，无法直接区分。但用户主动切换必然
// 伴随一次真实鼠标点击，而 Studio 自我激活不会。所以看激活前后有没有点击。
// 一旦判定是用户意图，就立刻让出控制权 —— 否则用户会发现窗口点不动（踩过）。
func secondsSinceUserClick() -> Double {
    let l = CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: .leftMouseDown)
    let r = CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: .rightMouseDown)
    return min(l, r)
}

let dockPID = NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.dock")
    .first?.processIdentifier

// 光标底下那个窗口属于谁。只看"最近有没有点击"是不够的 —— 用户在别的 app 里
// 点鼠标时，恰好撞上 Studio 自我激活，就会被误判成"用户要切过去"而提前放弃保护
// （实测踩过：用户在 ChatGPT/终端之间切换，保护在 23 秒就失效了）。
// 注意：bounds 和 ownerPID 不需要屏幕录制权限，只有窗口标题才需要。
func pidUnderCursor() -> pid_t? {
    let loc = NSEvent.mouseLocation                       // 原点在左下
    guard let screenH = NSScreen.screens.first?.frame.height else { return nil }
    let pt = CGPoint(x: loc.x, y: screenH - loc.y)        // CGWindowList 原点在左上
    guard let infos = CGWindowListCopyWindowInfo(
            [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]
    else { return nil }
    // onScreenOnly 返回的顺序是从前到后，第一个命中的就是最上层窗口
    for info in infos {
        guard let b = info[kCGWindowBounds as String] as? [String: CGFloat],
              let pid = info[kCGWindowOwnerPID as String] as? pid_t else { continue }
        let r = CGRect(x: b["X"] ?? 0, y: b["Y"] ?? 0,
                       width: b["Width"] ?? 0, height: b["Height"] ?? 0)
        if r.contains(pt) { return pid }
    }
    return nil
}

// 判定这次激活是不是用户主动要的：最近有点击 **且** 点在 Studio 窗口或 Dock 上。
// 拿不到光标下的窗口时退回"有点击就算"，宁可提前放手也不要把用户锁在外面。
func isUserIntent() -> (Bool, String) {
    let since = secondsSinceUserClick()
    guard since < 1.0 else { return (false, "") }
    guard let p = pidUnderCursor() else {
        return (true, String(format: "%.2fs 前有点击（光标位置未知，保守让路）", since))
    }
    if p == dockPID {
        return (true, String(format: "%.2fs 前点了 Dock", since))
    }
    if NSRunningApplication(processIdentifier: p)?.bundleIdentifier == studioBundleID {
        return (true, String(format: "%.2fs 前点在 Studio 窗口上", since))
    }
    return (false, "")
}

func yieldAndExit(_ why: String) {
    windingDown = true
    let toUnhide = managedPIDs
    managedPIDs.removeAll()
    for pid in toUnhide where NSRunningApplication(processIdentifier: pid) != nil {
        if !axSetHidden(pid, false) {
            sysEventsSetHidden(pid, false)
        }
    }
    log("让出控制权（\(why)），窗口已恢复显示，退出。")
    if verbose { print("YIELDED=\(why)") }
    exit(0)
}

// ---------- 反制动作 ----------
func suppress(_ app: NSRunningApplication, reason: String) {
    let pid = app.processIdentifier
    let isNew = !preExistingStudioPIDs.contains(pid)

    let (userWants, why) = isUserIntent()
    if userWants {
        yieldAndExit(why)
        return
    }
    if grabCount > 10 {
        yieldAndExit("拦截已达 10 次，避免和你拉锯")
        return
    }

    // 先还焦点，再隐藏。activate 是毫秒级，hide 可能慢 1s 以上；
    // 顺序反了的话，hide 慢半拍期间焦点就一直被 Studio 占着（实测丢过 3 秒）。
    enforceAnchor()

    if mode == "hide" && isNew && !windingDown {
        managedPIDs.insert(pid)
        log("\(reason): 已还焦点，隐藏已排队 (pid \(pid))")
        setHiddenAsync(pid: pid, true, tag: "  ")
    } else {
        log("\(reason): 已还焦点 (pid \(pid), isNew=\(isNew), windingDown=\(windingDown))")
    }
}

// 只调一次 activate 不够：它可能和 Studio 正在进行的激活撞车而抢输，
// 而 Studio 此时已是前台就不会再发 didActivate 通知，等于没有第二次机会。
// 所以激活后要验证是否真的抢回来了，没抢回来就继续试（上限约 1.2 秒）。
func enforceAnchor(_ attempt: Int = 0) {
    guard attempt < 12 else {
        log("  ⚠️ 焦点争夺失败，已重试 \(attempt) 次仍停在 Studio")
        return
    }
    activateAnchor()
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
        if let f = NSWorkspace.shared.frontmostApplication,
           f.bundleIdentifier == studioBundleID {
            enforceAnchor(attempt + 1)
        } else if attempt > 0 {
            log("  焦点已夺回 (第\(attempt + 1)次尝试)")
        }
    }
}

func activateAnchor() {
    guard let a = NSRunningApplication(processIdentifier: currentAnchorPID) else { return }
    // macOS 14+ 协同激活可能拒绝后台进程的激活请求，成功与否要验证
    let ok = a.activate()
    if !ok {
        log("NSRunningApplication.activate() 被拒，回退 System Events")
        activateAnchorViaAppleScript()
    }
}

func activateAnchorViaAppleScript() {
    guard let name = NSRunningApplication(processIdentifier: currentAnchorPID)?.localizedName else { return }
    let src = "tell application \"System Events\" to set frontmost of first application process whose unix id is \(currentAnchorPID) to true"
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
    p.arguments = ["-e", src]
    p.standardOutput = FileHandle.nullDevice
    p.standardError = FileHandle.nullDevice
    try? p.run()
    log("AppleScript 回退已执行 (\(name))")
}

// ---------- 事件监听 ----------
let nc = ws.notificationCenter

nc.addObserver(forName: NSWorkspace.didLaunchApplicationNotification, object: nil, queue: .main) { note in
    guard let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
          app.bundleIdentifier == studioBundleID else { return }
    log("Studio 进程启动: pid \(app.processIdentifier)")
    if mode == "hide" && !windingDown {
        managedPIDs.insert(app.processIdentifier)
        setHiddenAsync(pid: app.processIdentifier, true, tag: "  启动即隐藏 ")
    }
}

nc.addObserver(forName: NSWorkspace.didActivateApplicationNotification, object: nil, queue: .main) { note in
    guard let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication else { return }

    guard app.bundleIdentifier == studioBundleID else {
        // 用户切到了别的 app：焦点以后要还到这里，而不是启动时那个窗口
        if app.processIdentifier != currentAnchorPID {
            currentAnchorPID = app.processIdentifier
            log("锚点跟随 -> \(app.localizedName ?? "?") (pid \(app.processIdentifier))")
        }
        return
    }

    grabCount += 1
    suppress(app, reason: "抢焦点 #\(grabCount)")
}

// hide 模式下，Studio 被系统 unhide（激活会连带 unhide）时立刻再 hide 回去
nc.addObserver(forName: NSWorkspace.didUnhideApplicationNotification, object: nil, queue: .main) { note in
    guard mode == "hide", !windingDown,
          let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
          app.bundleIdentifier == studioBundleID,
          managedPIDs.contains(app.processIdentifier) else { return }
    // 用户点 Dock 图标也会让 app unhide —— 同样要让路，否则窗口永远调不出来
    let (userWants2, why2) = isUserIntent()
    if userWants2 {
        yieldAndExit(why2)
        return
    }
    log("Studio 自行 unhide (pid \(app.processIdentifier))，重新隐藏")
    enforceAnchor()
    setHiddenAsync(pid: app.processIdentifier, true, timeout: 1.5, tag: "  ")
}

// ---------- 启动目标 ----------
func launchTarget() {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
    var args = ["-g"]
    if mode == "hide" { args.append("-j") }   // -j = 隐藏启动
    if let t = target {
        args.append(t)
    } else {
        args.append(contentsOf: ["-b", studioBundleID])
    }
    p.arguments = args
    p.standardOutput = FileHandle.nullDevice
    p.standardError = FileHandle.nullDevice
    log("执行: open \(args.joined(separator: " "))")
    try? p.run()
}
launchTarget()

// ---------- 收尾 ----------
Timer.scheduledTimer(withTimeInterval: duration, repeats: false) { _ in
    // 必须先置标志并清空 managedPIDs：下面的 unhide 会触发 didUnhide 通知，
    // 监听器若还认得这些 pid，就会把刚放出来的窗口立刻按回隐藏。
    windingDown = true
    let toUnhide = managedPIDs
    managedPIDs.removeAll()

    if mode == "hide" {
        // unhide 不会激活，窗口以后台形式出现，焦点留在锚点应用
        for pid in toUnhide where NSRunningApplication(processIdentifier: pid) != nil {
            setHiddenAsync(pid: pid, false, timeout: 2.0, tag: "收尾 ")
        }
    }

    // 窗口刚出现时 Studio 往往还会再抢一次焦点，再守 guardPeriod 秒。
    // 此期间只还焦点、不再隐藏（窗口这时候本来就该是可见的）。
    log("进入守护期 \(Int(guardPeriod))s：只还焦点，不再隐藏")
    Timer.scheduledTimer(withTimeInterval: guardPeriod, repeats: false) { _ in
        log("监控结束，共拦截 \(grabCount) 次抢焦点")
        if verbose { print("TOTAL_GRABS=\(grabCount)") }
        exit(0)
    }
}

nsapp.run()
