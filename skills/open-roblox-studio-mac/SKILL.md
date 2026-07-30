---
name: open-roblox-studio-mac
description: 在 macOS 命令行打开 Roblox Studio 场景的两种方式——本地 rbxl/rbxlx 文件、以及已发布到 Roblox 但没有本地文件的远程 place（按 placeId）。触发词：打开 studio、用 studio 打开、命令行打开 roblox 场景、open rbxl、打开已发布的 place、roblox-studio 协议。
---

# open-roblox-studio-mac

macOS 命令行打开 Roblox Studio 场景，按有没有本地文件分两种方式。

## 方式一：打开本地 `.rbxl` / `.rbxlx` 文件

```bash
open <file>.rbxl
```

- macOS 默认已把 `.rbxl` / `.rbxlx` 关联到 Roblox Studio，直接 `open` 即可。
- **不要加 `-a "RobloxStudio"`**：加了反而可能绕过默认关联触发异常，直接裸 `open` 最可靠。

## 方式二：打开已发布到 Roblox 的远程 place（没有本地文件，只有 placeId）

分两步：

1. **查 universeId**（公开 API，无需鉴权）：

   ```bash
   curl -s "https://apis.roblox.com/universes/v1/places/<PLACE_ID>/universe"
   # 返回 {"universeId": <UNIVERSE_ID>}
   ```

2. **拼 `roblox-studio:` 协议 URI 并 open**：

   ```bash
   open "roblox-studio:1+launchmode:edit+task:EditPlace+placeId:<PLACE_ID>+universeId:<UNIVERSE_ID>"
   ```

### 注意

- **必须带 `universeId`**。只带 `placeId` 会报错：
  ```
  We could not open the place [0]
  Error fetching latest place version
  ```
  （2026-07-30 实测：`placeId=88451300192871` 单独打开必现此错，补上 `universeId=10594886372` 后成功。）
- 打开后需要 Studio 已登录、且账号对该 place 有编辑权限，否则会走浏览器授权确认或直接失败。
