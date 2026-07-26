# LOD（RenderFidelity 与手工 LOD）

> 实测环境：Roblox Studio edit 会话（macOS），2026-07-27。
> 原始数据：`roblox-render-lab/results/bench_meshpart_raw.txt`、`bench_lod_threshold_raw.txt`。
> 被测 mesh：970 三角形的 4 层公寓，尺寸 16.2 × 16.9 × 13.5 stud。

## 阈值按**绝对距离**，不是屏幕占比

判别法：同一 mesh 放大 ×1 / ×3 / ×10，在同样距离重测。

| fidelity | scale | 首次降级距离 | 该处屏幕占比 |
| --- | --- | ---: | ---: |
| `Automatic` | ×1 / ×3 / ×10 | **900 / 900 / 900** | 0.013 / 0.040 / 0.134 |
| `Performance` | ×1 / ×3 / ×10 | **600 / 600 / 600** | 0.020 / 0.060 / 0.201 |

距离完全一致、屏幕占比差 10 倍 → **阈值按绝对距离**。

## 各档实测面数（原始 970 tris）

| RenderFidelity | 300 | 600 | 900 | 1500 | 3000 | 6000 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Precise` | 965 | 965 | 965 | 965 | 965 | 965 |
| `Automatic` | 965 | 965 | **480** | 480 | 480 | 480 |
| `Performance` | **448** | **191** | 93 | 93 | 21 | **12** |

- **`Automatic` 只有两档**：满面数 → 50%，到底了，再远也不降。
- **`Performance` 有五档**：965 → 448 → 191 → 93 → 21 → 12。
- 小物体在 ~6000 stud 外被**整个剔除**。
- 近距离时尺寸有影响（`Performance ×10` 在 300 stud 仍满面数），
  符合「按到**包围盒表面**的距离」而非到中心；600 stud 起三个尺寸完全一致。

## ⚠️ 官方文档与实测不符

官方文档说 `Automatic` 按 **250 / 500 stud** 切三档。
实测 `Automatic` 在 600 stud 仍是满面数，900 stud 才降，且只降一档。
`Performance` 首降在 300~600 之间。**不要照文档的数字做设计。**

## 手工 LOD 值不值得做

**值得，但价值点和直觉不同。**

- 手工做的 LOD1（80 tris）**不是「比引擎更低面」** ——
  `Performance` 最终能到 12 tris，比它更低。
- 真正的价值是**能在中距离就用上低模**：手工切换可以在 300 stud 就换到 80 tris，
  而 `Performance` 在 300 stud 还有 448 tris，要到 3000 stud 才降到 21。

**切换成本接近零**：用 `Transparency = 1` 隐藏，实测 Δ0 batches（见 `rendering-batching.md`）。
不需要改 `Parent`。

**注意 `MeshPart.MeshId` 运行时不可写**（官方限制）。替代方案是
`MeshPart:ApplyMesh()`，但它会连碰撞几何一起重建，代价明显。
所以手工 LOD 的正确做法是**预先摆两个 MeshPart，切 `Transparency`**，
代价是两份 mesh 同时驻留内存。

## 适用边界

- 全部取自 Studio **edit 会话**。真机行为未验证 —— 这条尤其重要，
  因为 Studio 可能对编辑体验做特殊处理。
- 只测了一个尺寸量级的 mesh（16~170 stud）。极大或极小物体未测。
- 排除了两个干扰因素：`Rendering.MeshPartDetailLevel`（全 11 档）和
  `Rendering.QualityLevel`（Level01~21）都**不影响** `Automatic` 的降级行为。
