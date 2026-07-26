# 怎么测（Roblox 渲染指标的自动化测量）

> 环境：macOS + Roblox Studio + `run-in-roblox` 0.3.0 + `rojo` 7.7.0，2026-07-27。
> 参考实现：`roblox-render-lab/scripts/*.lua`。

## 核心发现：渲染统计能从 Lua 读

Shift+F3 那个渲染统计面板背后的数据在 **`Stats.FrameRateManager`** 下，可以直接读：

| StatsItem | 含义 |
| --- | --- |
| `Batches` | **draw call 数** —— 合批类实验的主指标 |
| `Indices` | 索引数。⚠️ **是 2 个 pass 的合计**，真实三角形 = `(Indices - 基线) / 6` |
| `MaterialChanges` | 材质切换次数 |
| `VideoMemoryInMB` | 显卡总显存 |
| `FramebufferWidth/Height` | 视口分辨率 |
| `AverageFPS` `RenderAverage` `PerformAverage` `AverageGPU` | 帧时间分解 |

内存分项走 `Stats:GetMemoryUsageMbForTag(Enum.DeveloperMemoryTag.X)`，
需要 `Stats.MemoryTrackingEnabled == true`。渲染相关 tag：
`GraphicsTexture` / `GraphicsMeshParts` / `GraphicsParts` / `GraphicsSolidModels` /
`GraphicsTerrain` / `GraphicsParticles` / `GraphicsSpatialHash` / `GraphicsSlimModels`。

## 跑法

```bash
# 生成一个空测试场景
rojo build default.project.json -o places/lab.rbxlx

# 把 Lua 塞进 Studio 跑，stdout 回传终端
run-in-roblox --place places/lab.rbxlx --script scripts/bench.lua | tee results/raw.txt
```

- `--place` **不能省**（0.3.0 省略会 panic：`not implemented: run-in-roblox with no place argument`）。
- 脚本以 **plugin 权限**在 Studio 的 **edit 会话**里运行（不是 Play 模式）。
- 单次跑约 2~4 分钟，大头是 Studio 启动。

## 实验设计纪律

1. **帧时间类指标一律不采信。** Studio 视口在后台时 `AverageFPS` 只有个位数、
   `RenderAverage` 几百毫秒，这些数没有意义。
   `Batches` / `Indices` 是**结构性计数**，不受帧率影响，可信。
2. **每组等够帧再采样**（实测 40 帧足够），采 5 次取众数，防某一帧没画完。
3. **必测空场景基线**，所有结论用 Δ 表示。
4. **必设复测组**：把第一组的配置在最后再跑一遍，验证没有累积污染。
   实测两次读数可精确复现。
5. **相机要能看全**：物体被视锥剔除会得到假的低读数。
6. **首次渲染 mesh 有加载延迟**，正式测量前先热身跑一遍并
   `ContentProvider:PreloadAsync`，否则第一组会读到 0。

## plugin 权限的坑

| 想做的事 | 结果 |
| --- | --- |
| 读 `Lighting.Technology` | ❌ 需要 RobloxScript 权限 |
| 读写 `Lighting.GlobalShadows` | ❌ 读回 `nil`，写入无效（属性大概率已废弃） |
| 读写 `settings():GetService("RenderSettings")` 各属性 | ✅ 可用 |
| `InsertService:LoadAsset()` | ✅ 可用 —— **这是运行时换 mesh 的正路** |
| 写 `MeshPart.MeshId` | ❌ 运行时不可写 |
| 写 `MeshPart.TextureID` | ✅ 可写 |
| `SurfaceAppearance.ColorMap = "rbxasset://..."` | ❌ 不接受本地资产，必须是上传的 assetId |

所以：**要在脚本里造 MeshPart，走 `InsertService:LoadAsset(modelAssetId)` 拿到 Model
再 `Clone()` 里面的 MeshPart**，不要试图设 `MeshId`。

## 不用进引擎也能测的东西

有些"看起来需要肉眼判断"的问题其实能算。例如 mip 串色 ——
mip 生成是确定的 2×2 盒式滤波，用 numpy 直接算比截图比对更准，
还能把混在一起的多个机制拆开（见 `atlas-and-mip.md`）。
**先想想能不能算，再考虑截图。**
