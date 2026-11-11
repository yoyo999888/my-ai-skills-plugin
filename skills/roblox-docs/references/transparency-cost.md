# 透明件的真实代价（真机）

> 实测环境：Android 手机 Redmi K30（Android 12），Roblox 客户端 2.746.1266，
> `SavedQualityLevel = 5`，竖屏视口 393×838（逻辑像素），2026-11-12。
> 场景：一张约 1.6 万图元的真实地图，固定机位，基线整帧 36.4 ms。同一台手机在同一张图的城区机位
> 读 `/sys/class/kgsl/kgsl-3d0/gpu_busy_percentage` 为 99%（显卡跑满），空场景能跑到 50～60 帧，没有 30 帧上限。
> 方法：客户端 LocalScript 在本地临时放一个测试件，放进前后各采 50 帧取中位数，
> 每种 3 轮再取中位数。读 `Stats.SceneDrawcallCount`、`Stats.SceneTriangleCount`、
> `Stats.RenderGPUFrameTime`。脚本见文末。

## 一句话

**手机上 `Transparency = 1` 不等于不画。** 只要在视野里，它就和半透明件一样画一遍，
代价按「朝向镜头的那一面盖住多少屏幕」算。

## 实测数据

测试件：503×111×961 的 Part（Plastic），或正对镜头、离镜头 30 格的薄板。

| 放进场景的东西 | 绘制调用 | 三角面 | 整帧时间 |
| --- | ---: | ---: | ---: |
| 大方块，镜头在**里面**，T=1 | +1 | +12 | **0**（3 轮 −0.2～0.2 ms） |
| 同上，`CastShadow = false` | +1 | +12 | 0 |
| 同上，T=0.99 / 0.5 / 0（不透明） | +1 | +12 | 0 |
| 同上 3 块叠放，T=1 | +3 | +36 | 0 |
| 大方块在镜头前 20 格，正面盖满屏幕，T=1 | +1 | +12 | **+6.1 ms** |
| 大方块在镜头**背后**（不在视野里），T=1 | 0 | 0 | 0 |
| 薄板盖满全屏，T=1 | +2 | +12 | **+6.5 ms** |
| 薄板盖半屏，T=1 | +2 | +12 | **+3.1 ms** |
| 薄板盖四分之一屏，T=1 | +2 | +12 | **+1.7 ms** |
| 薄板盖满全屏，T=0.5 | +2 | +12 | **+6.5 ms** |

每种 3 轮的离散都在 ±0.3 ms 以内。

## 读法

1. **T=1 没被剔除**：在视野里就 +1～2 次绘制调用，三角面照算。只有视锥剔除（出了视野）才归零。
2. **T=1 和 T=0.5 一样贵**：同样盖满全屏，都是 +6.5 ms。透明度数值、投影开关都不影响。
3. **代价和盖住的屏幕面积成正比**：全屏 6.5 → 半屏 3.1 → 四分之一 1.7 ms。
   这是像素填充（读回底色再混合）的特征，不是三角面或绘制调用的问题（它们只有 12 个面）。
4. **镜头在方块里面时是 0**：从里面看到的都是背面，被背面剔除掉了，透明不透明都一样。
   所以「巨型透明区域盒」贵不贵，取决于镜头是在盒外看着它的外表面，还是在盒子里面。

## 线上事故（这条结论的来源）

一张地图里留着 3 个编辑用的透明区域盒（最大 503×111×961，CanCollide / CanQuery / CanTouch 全关，
没有任何脚本读）。在检查站机位手机整帧 43.3 ms；把它们从 Workspace 挪进 ServerStorage 后
36.5 ms（−6.8 ms，−16%），帧率 23 → 27。和上表的「盖住屏幕面积」规律吻合。

## 设计推论

1. **编辑用的范围盒、定位块、触发区不要留在 Workspace。** 放 ServerStorage；
   需要编辑时可见、运行时不要，就在服务端开服时挪走。
   只有服务端用的判定盒，改成脚本里的中心 + 尺寸常量。
2. **要隐藏的东西改 `Parent`，不要只设 `Transparency = 1`。**
   这和 `rendering-batching.md`、`lod.md` 里 Studio 的结论相反，以真机为准。
3. 半透明的大面（玻璃幕墙、水面、雾片、树叶贴图）同理，**按占屏面积估成本**。
   同一台手机上，3 个透明盒约 6.8 ms，树叶 SurfaceAppearance 半透明约 4～6 ms。

## 适用边界

- 只测了一台中端 Android、一个画质档（5）。高端机、iOS、PC 未测；
  在显卡不吃满的设备上，帧时间差可能看不出来，但绘制调用 +1 仍然成立。
- 只测了 `Part`（Plastic）。MeshPart、带贴图或 SurfaceAppearance 的透明件未单独测。
- **Studio 0.747 和电脑版 Player 这次没复测。** 7 月的 Studio 数据是「T=1 Δ0 batches」；
  是引擎变了还是平台不同，没分清。
- 手机上 `RenderCPUFrameTime` 和 `RenderGPUFrameTime` 读数相同，都是整帧时间，
  拆不出 CPU 和 GPU 各占多少。

## 测试脚本（核心部分）

固定相机后，对每个变体执行：

```lua
local function sample(n)
	local d, tr, gpu = {}, {}, {}
	for _ = 1, n do
		RunService.RenderStepped:Wait()
		table.insert(d, Stats.SceneDrawcallCount)
		table.insert(tr, Stats.SceneTriangleCount)
		table.insert(gpu, Stats.RenderGPUFrameTime * 1000)
	end
	for _, t in { d, tr, gpu } do table.sort(t) end
	local m = #d // 2 + 1
	return { draws = d[m], tris = tr[m], gpu = gpu[m] }
end

-- 每个变体 3 轮，取差值的中位数
local b = sample(50)
local p = make() -- 新建测试件：Anchored，CanCollide/CanQuery/CanTouch = false
p.Parent = workspace
task.wait(0.5)
local w = sample(50)
p:Destroy()
task.wait(0.5)
-- 差值 = w - b
```

盖屏薄板的尺寸：竖直视场 70° 时，离镜头 d 格盖满全屏需要高 `2·d·tan(35°)`、
宽 = 高 × 视口宽高比；盖 f 比例的面积就把边长乘 `sqrt(f)`。

手机上跑的办法：测量脚本常驻在场景里，只在 `GetJoinData().LaunchData` 含约定关键字时运行，
用 `roblox://experiences/start?placeId=<id>&launchData=<关键字>` 进游戏；
结果 `print` 到客户端日志，Android 上在 `/data/data/com.roblox.client/files/appData/logs/`（需要 root）。
