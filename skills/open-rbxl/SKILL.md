---
name: open-rbxl
description: macOS 命令行打开 Roblox Studio 场景：本地 .rbxl/.rbxlx 直接裸 `open`，不要 `-a`；远程 place 用 roblox-studio: 协议 URI 且必须带 universeId。触发词：打开 rbxl、打开 Studio 场景、open place、多开 Studio。
---

# open-rbxl

macOS 上打开 Roblox Studio 场景，不需要任何额外工具。

## 本地文件

```bash
open <file>.rbxl        # 或 .rbxlx
```

- macOS 默认已把 `.rbxl` / `.rbxlx` 关联到 Roblox Studio，裸 `open` 最可靠。
- **不要加 `-a "RobloxStudio"`**——绕过默认关联可能触发异常。
- 依次 open 多个文件即可多开 Studio 实例（每个文件一个进程）。

## 远程 place（只有 placeId、无本地文件）

```bash
# 1. 查 universeId（公开 API，无需鉴权）
curl -s "https://apis.roblox.com/universes/v1/places/<PLACE_ID>/universe"
# → {"universeId": <UNIVERSE_ID>}

# 2. 拼协议 URI 打开
open "roblox-studio:1+launchmode:edit+task:EditPlace+placeId:<PLACE_ID>+universeId:<UNIVERSE_ID>"
```

**必须带 `universeId`**，只带 placeId 会报
`We could not open the place [0] / Error fetching latest place version`。
需要 Studio 已登录且账号对该 place 有编辑权限。
