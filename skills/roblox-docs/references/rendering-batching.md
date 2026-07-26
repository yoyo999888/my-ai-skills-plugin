# 渲染合批（instancing）

> 实测环境：Roblox Studio edit 会话（macOS）、`QualityLevel = Level21`、`EnableFRM = false`、
> 视口 1134×784，2026-07-27。原始数据：`roblox-render-lab/results/bench_batching*_raw.txt`、
> `bench_meshpart_raw.txt`、`bench_lod_and_sa_raw.txt`。指标取 `Stats.FrameRateManager.Batches`。

## 一句话

**「东西多」几乎不花 draw call，「种类多」才花。**

## 核心公式

Roblox 用 **instancing** 把相同外观的物体合成一次 draw call（不是 Cities: Skylines 那种合并 mesh）。

```
Δbatches ≈ 3 × k        （k = 场景里不同的「外观组合」数）
```

「外观组合」= `(mesh, 贴图 / 材质 / SurfaceAppearance)`。**与物体数量无关。**

k=1 是唯一例外，只要 2 批（不是 3）。那个 2 是**两个 pass**（颜色 + 深度/阴影）——
佐证是 `Stats.FrameRateManager.Indices` 读到的值恰好是真实三角形数的 2 倍。

## 实测数据

### 不拆批的（可以放心用）

| 变量 | 100 个物体的 Δbatches | 结论 |
| --- | ---: | --- |
| 全同 | +2 | 基准 |
| 各自不同 `Color` | +2 | **颜色不拆批** |
| 各自不同 `Size` | +2 | **尺寸不拆批** |
| `Anchored` true/false | +2 | 锚定与否无关 |
| 物体数 100 / 500 / **2000** | +2 / +2 / **+2** | **与数量完全无关** |
| 各挂内容相同的 `SurfaceAppearance` | +2 | **内容相同即合批** |

2000 个全同物体仍然只有 2 个 draw call，`Indices` 线性涨到 144,883。

### 拆批的（要控制种类数）

| 变量 | Δbatches | 每多一种 |
| --- | ---: | ---: |
| `Material` 1/2/3/4/8/16 种 | 2/6/9/12/24/48 | **+3** |
| MeshPart 用 2 种 mesh | +6 | +3~4 |
| MeshPart 轮换 4 张 `TextureID` | +12 | ~+3.3 |
| `SurfaceAppearance` 用 2 种 `ColorMap` | +6 | +3~4 |
| Decal 轮换 10 张贴图 | +22 | ~+2 |

材质数曲线在 k≥2 时精确符合 **Δ = 3k**。

### 特殊情况

- **`Transparency = 1`：Δ0 batches**，`Indices` 从 7965 掉到 765 —— 基本被完整剔除。
  **这是最便宜的隐藏方式**，比改 `Parent` 好，可用来做手工 LOD 切换。
- **`Transparency = 0.5`：Δ1**，比不透明还**少**一批，`Indices` 也少一半
  （半透明只画部分面、且没有阴影 pass）。「半透明贵」在 draw call 维度不成立，
  贵在 overdraw 和排序，那是像素侧的事。
- **「挂 SurfaceAppearance」和「不挂」算两种不同组合**：一半挂一半不挂 → Δ6。
  一批物体要么都挂要么都不挂。
- **Decal 按贴图分批**：100 个同贴图 decal 只 +1 批；换成 10 张不同贴图 → +19 批。
  官方文档说 "decals don't batch well"，准确说法是「不同贴图的 decal 不合批」。

## MeshPart vs Part

上面的规则**两边都成立**。曾担心 Part（引擎内置程序化几何）的结论不能外推到 MeshPart，
实测用真 MeshPart 复现，数字一致。

## 设计推论

1. **疯狂复用 mesh 和贴图，靠 `Color` / `Size` / `CFrame` 制造视觉变化。**
   2000 栋楼 × 10 种 mesh × 1 张图集 ≈ 30 个 draw call；
   同样 2000 栋楼但每栋一张贴图 ≈ 6000 个。三角形数一模一样，差 200 倍。
2. **图集是划算的**，每合并掉一张贴图就省 3 批。见 `atlas-and-mip.md`。
3. **材质种类是 3 倍放大器**，比"多摆几千个物体"贵得多。

## 适用边界

- 数据取自 Studio **edit 会话**，不是真实客户端。真机画质等级、后处理都可能不同。
- 只验证到 2000 个物体；更大规模未测。
- `SurfaceAppearance` 的 "identical" 只测了 `ColorMap` 维度，其余贴图通道未单独验证。
