---
name: roblox-docs
description: Roblox 引擎经验知识库，按条目索引已经实测验证过的结论（渲染合批、LOD、资产上传等）。回答任何 Roblox 性能/渲染/资产问题前先查这里，避免凭直觉或从别的引擎类比。触发词：roblox 性能、draw call、合批、batching、LOD、RenderFidelity、图集、atlas、mip、SurfaceAppearance、上传 asset、roblox-docs。
---

# roblox-docs

Roblox 引擎的经验知识库。**只收实测验证过的结论**，按条目索引。

## 为什么需要它

Roblox 引擎闭源、不让写 shader，官方文档在细节上多处与实测不符。凭直觉推断或从别的引擎（Unity、Cities: Skylines 等）类比，**错误率极高** —— 建立本库的那次调研里，看起来很有道理的推断被实测推翻了 5 次（见 `references/lessons.md`）。

所以规矩是：**回答 Roblox 性能/渲染问题前先查本库；本库没有的，先测再答，不要猜。**

## 条目索引

| 条目 | 一句话 | 文件 |
| --- | --- | --- |
| 渲染合批 | 「东西多」不花 draw call，「种类多」才花；合批键是 `(mesh, 贴图/材质/SurfaceAppearance)`，每多一种组合 +3 批 | `references/rendering-batching.md` |
| LOD | 阈值按**绝对距离**（非屏幕占比），`Automatic` 只降一档到 50%，`Performance` 五档最低 12 tris | `references/lod.md` |
| 贴图图集与 mip | 格子边界对齐 2 的幂则 mip 生成零串色；UV 内缩只防 mip 0~2 的采样 | `references/atlas-and-mip.md` |
| 测量方法 | `Stats.FrameRateManager.Batches` 可从 Lua 读；配 `run-in-roblox` 可全自动跑实验 | `references/measurement.md` |
| 资产上传 | Open Cloud + `rbxcloud` 上传 mesh/贴图的可用流程与两个坑 | `references/asset-upload.md` |
| 踩过的坑 | 被实测推翻过的 5 条「合理推断」，以及它们为什么听起来对 | `references/lessons.md` |

## 何时使用

- 被问到 Roblox 的 draw call、合批、LOD、贴图内存、图集、SurfaceAppearance、RenderFidelity 等问题。
- 要给 Roblox 项目做性能相关的设计决策（美术规格、材质数量、LOD 策略、图集排布）。
- 想把一个新的 Roblox 实测结论沉淀下来。

## 怎么用

1. 先读本文件的条目索引，定位相关条目。
2. 打开对应的 `references/*.md` 拿具体数字。
3. **引用结论时连数据来源一起给**（每条结论都标了测量环境和原始数据位置），
   让对方能判断这条结论在他的环境下还成不成立。
4. 本库没覆盖的问题：按 `references/measurement.md` 的方法测出来再答，
   顺手把结果按下面的格式加成新条目。

## 怎么加新条目

1. 在 `references/` 下新建一个 kebab-case 的 `.md`，或往已有条目里追加。
2. 每条结论必须写清四件事，缺一不可：

   - **数字**：实测值，不是「大概」「差不多」
   - **测量环境**：引擎版本、Studio 还是真机、画质等级、日期
   - **原始数据在哪**：能复现的脚本 / 输出文件路径
   - **适用边界**：哪些情况下这条结论不成立

3. 明确区分「**实测**」和「**推断**」。推断必须显式标注为推断，
   并写清怎么验证它。本库最大的价值就是这条界限清楚。
4. 回到本文件的条目索引表里登记一行。

## 纪律

- **不收未验证的结论。** 官方文档的说法也算未验证 —— 本库里已有多处实测与官方文档不符。
- **结论会过期。** 每条都带日期和引擎版本；引擎更新后要重测，不要无限期沿用。
- **不收从别的引擎类比来的推断。** 那正是本库要防的错误来源。
