---
name: open-roblox-studio-mac
description: 在 macOS 命令行打开 Roblox Studio 场景（本地 rbxl/rbxlx 文件、或已发布的远程 place），并用自带的 rbx 工具静默打开——不让 Studio 抢占焦点。含 rbx 源码、编译安装、使用与踩坑。触发词：打开 studio、用 studio 打开、命令行打开 roblox 场景、open rbxl、打开已发布的 place、roblox-studio 协议、studio 抢焦点、静默打开 studio、rbx。
---

# open-roblox-studio-mac

macOS 命令行打开 Roblox Studio 场景。**默认用 `rbx` 静默打开**——裸 `open` 会被 Studio 抢走焦点（打开一个 place 过程中会抢 2~4 次，每次几秒且需手动点回来）。

## 快速用法

```bash
rbx <file>.rbxl                      # 本地文件，静默打开
rbx "roblox-studio:1+launchmode:edit+task:EditPlace+placeId:<PID>+universeId:<UID>"
rbx                                  # 只启动 Studio 本身
```

命令 0.01 秒返回（行为对齐 `open`），守护进程在后台跑 90 秒。

| 选项 | 说明 |
|---|---|
| `--mode hide` | 默认。加载期间隐藏窗口，加载完 unhide（unhide 不激活），全程零闪烁 |
| `--mode focus` | 窗口可见，只在被抢焦点时切回来 |
| `--duration <秒>` | 监控时长，默认 90。大文件加载超时就调大 |
| `--foreground` / `-f` | 前台运行，调试用 |
| `--verbose` / `-v` | 前台模式打印事件日志 |

- 日志：`~/Library/Logs/rbx.log`
- 中止：`pkill -x rbx` —— **必须带 `-x`**。不带的话 `pkill rbx` 会模糊匹配到 `rojo serve xxx.rbxl` 等命令行里含 `rbx` 的进程，误杀。
- 想切过去时**直接点 Studio 窗口或 Dock 图标**，它会立刻让出控制权并自动退出。在别的 app 里点鼠标不受影响。

## 安装（编译 Swift 源码）

源码在本技能的 `scripts/rbx.swift`。需要 Xcode Command Line Tools（`xcode-select --install`）。

```bash
mkdir -p ~/workspace/scripts
cp <本技能目录>/scripts/rbx.swift ~/workspace/scripts/
swiftc -O -o ~/workspace/scripts/rbx ~/workspace/scripts/rbx.swift
ln -sf ~/workspace/scripts/rbx /opt/homebrew/bin/rbx     # 装进 PATH
rbx --help                                                # 验证
```

编译只有 Swift 6 并发相关的 warning，无害。symlink 指向文件路径，之后重新编译即时生效，不用重装。

### ⚠️ 辅助功能授权——决定这工具能不能用

隐藏走的是 Accessibility API。TCC 把权限算在**责任进程**（调用它的终端）头上：

- 从**已授权的终端**（如 WezTerm/iTerm）调用 → 正常工作。
- 从 **Raycast、Finder、rojo 钩子、launchd** 或未授权终端调用 → `AXIsProcessTrusted()` 为 false，隐藏快路径全灭，**无声失效**（不报错，只是又开始抢焦点）。

彻底解法：把编译出的 `rbx` 二进制单独拖进「系统设置 → 隐私与安全性 → 辅助功能」授权一次。**注意：每次重新编译该授权都会失效**（二进制内容变了），需重新授权。

排查：`rbx -f -v <file>` 看日志里 `Accessibility 授权: true/false`。

## 底层打开方式（rbx 内部用的，也可单独手工用）

### 本地 `.rbxl` / `.rbxlx`

```bash
open <file>.rbxl
```

macOS 默认已把 `.rbxl` / `.rbxlx` 关联到 Roblox Studio。**不要加 `-a "RobloxStudio"`**——绕过默认关联可能触发异常，裸 `open` 最可靠。

### 已发布的远程 place（只有 placeId，无本地文件）

```bash
# 1. 查 universeId（公开 API，无需鉴权）
curl -s "https://apis.roblox.com/universes/v1/places/<PLACE_ID>/universe"
# → {"universeId": <UNIVERSE_ID>}

# 2. 拼协议 URI
open "roblox-studio:1+launchmode:edit+task:EditPlace+placeId:<PLACE_ID>+universeId:<UNIVERSE_ID>"
```

- **必须带 `universeId`**。只带 `placeId` 必报：
  ```
  We could not open the place [0]
  Error fetching latest place version
  ```
  （实测 `placeId=88451300192871` 单独打开必现，补 `universeId=10594886372` 后成功。）
- 需要 Studio 已登录且账号对该 place 有编辑权限，否则走浏览器授权或直接失败。

## 抢焦点问题的背景与踩坑

`rbx` 为什么这么写、试过哪些死路、macOS 上有哪些反直觉的行为，见 `references/focus-stealing.md`。**改这个工具前务必先读**，那里记录了多个必然踩中的坑（AX 调用卡死主线程、unhide 触发自身监听器、锚点冻结等），以及两条已验证的负结论（Qt 环境变量无效、macOS 无官方接口可阻止自我激活）。
