# Server Authority（`Workspace.AuthorityMode = Server`）

> 平台：Roblox，Server Authority 于 **2026-07-09 Full Release**（LLM 知识截止之后，凭记忆必错）。
> 本机测量：Studio `0.731.0.7310942` / **Apple M4（4 性能核 + 6 能效核）**，2026-07-26~27。
> 云端测量：**真实 Roblox 服务器 `JobId=3e7b68c8`**，真人客户端加入，2026-07-27。
> 原始数据：`gta-roblox/gta-roblox-online/prototypes/p-vauth-01-server-authority-vehicles/RESULTS.md`（本机十轮）
> 与 `.../p-vauth-02-cloud-physics-baseline/RESULTS.md`（云端）。可重跑探针见两目录的 `studio/harness/`。

## 1. 它是什么：服务端跑**完整模拟**，不是"验证"

这不是 `SetNetworkOwner(nil)` 的同义词。服务端持有同步模拟真值，**客户端也跑同一份模拟作为
预测**，失配时由**引擎**回滚并重模拟。

实测证据（Studio，600 帧双端同步采样，角色落座后按住 W 6 秒再叠加 D 4 秒）：

| 量 | 客户端 | 服务端 |
| --- | ---: | ---: |
| `SteeringServo.TargetAngle` 均值 | 3.653 | **0.000** |
| 轮马达角速度 | — | **0.00** |
| 车速 | 2.80 | **0.04** |

**客户端写实例属性完全不产生权威效果**——服务端那辆车全程没动。配套：服务端
`IsResimulating()` 恒 `false`（它是真值，从不回滚），客户端大量 `true`。

**架构含义**：`Automatic` 下分散在 N 台客户端的载具物理，Server 模式下**全部压到服务端一台**。
这是 Server Authority 在载具域最大的成本转移项。

## 2. 六个必需开关，两个坑

`AuthorityMode=Server` 强制连带开启其余五项，不是可选：

| 属性 | 类型 | 值 |
| --- | --- | --- |
| `AuthorityMode` | `Enum.AuthorityMode` | `Server` |
| `NextGenerationReplication` | **`Enum.RolloutState`** | `Enabled` |
| `PlayerScriptsUseInputActionSystem` | **`Enum.RolloutState`** | `Enabled` |
| `UseFixedSimulation` | **`Enum.RolloutState`** | `Enabled` |
| `SignalBehavior` | `Enum.SignalBehavior` | `Deferred` |
| `StreamingEnabled` | `Bool` | `true` |

**坑 1 · 三项是 enum 不是 bool。** 赋 `true` 报
`error converting Lua boolean to userdata (expected EnumItem)`。
`RolloutState`：`Default=0 / Disabled=1 / Enabled=2`。

**坑 2 · 除 `StreamingEnabled` 外五项 `scriptability=None`，普通脚本读不到。**
`AuthorityMode` 报 `lacking capability RobloxScript`（属性存在、无权限），其余四项报
`is not a valid member of Workspace`（连名字都看不到）。

⇒ **不能靠读属性判断模式是否生效**，要靠行为证据：`BindToSimulation` / `IsResimulating` /
`GetPredictionStatus` / `SetPredictionMode` 四个 API 的存在性与返回值。

**怎么写进 place**：Rojo 的 `$properties` 不能指望认识这些 post-cutoff 属性；用 lune
`@lune/roblox` 反射库后处理（Rojo 出工程结构 → lune 盖开关 → 序列化往返自检）。
实现见 `p-vauth-02-cloud-physics-baseline/studio/stamp-flags.luau`。

## 3. `BindToSimulation` 模拟相里能做什么

**默认 30 Hz，不是 60**（`BindToSimulation(callback, frequency, priority)`，frequency 默认
`Hz30`，priority 默认 2000）。要 60 必须显式传 `Enum.StepFrequency.Hz60`。

能力表实测 30/32 项可用，**力与约束全部可读可写**（`VectorForce.Force`、`HingeConstraint`
的 `AngularVelocity`/`MotorMaxTorque`/`TargetAngle`/`CurrentAngle`、`PrismaticConstraint`、
`SpringConstraint`、`ApplyImpulse`、`CFrame`、`AssemblyLinearVelocity`、`SetAttribute`、
`Workspace:Raycast`、`Instance.new`+`Parent`（创建））。

**被拒的两项**：

- `Instance:Destroy()` → `Function Instance.Destroy is not allowed for simulation callbacks`
- 写 `Instance.Parent` → 同类拒绝

语义上说得通：回滚无法把已销毁的实例变回来。**创建是允许的**（官方 techniques 页的
predictive creation / instance stitching 由此得到实证）。⇒ 模拟相内的对象生命周期要用
对象池 / `Enabled=false`，不能 `Destroy`。

### 另外两条形态约束（会静默出错，务必遵守）

- **状态必须外置到 attribute**，不得留在 Luau 表 / 闭包 upvalue / 模块级变量。引擎回滚
  恢复的是实例状态，不是 Luau 变量；状态藏在闭包里会导致重模拟后客户端预测与服务端真值
  **静默发散**，没有报错、只表现为行为不一致。
- **副作用（音频、VFX、UI、遥测、网络发包）必须移出模拟相**。重模拟会重放同一帧逻辑，
  副作用被重复触发；实测最密窗口达**每真实帧重放 2.7 次**。快照编码 + `FireAllClients`
  放进模拟相 = 带宽 ×2.7 且客户端收到时序错乱的重复包。

## 4. 成本：**只认云端数字**

⚠️ **本机 M4 数字不可作生产值。** 差距不是常数，不能用单一倍率换算。

云端实测（`JobId=3e7b68c8`，扣各自空场基线后为"净值"）：

| 负载 | 云端均值 ms | 云端净 | 本机 M4 净 | 云/M4 |
| --- | ---: | ---: | ---: | ---: |
| 自由行驶 3 车 @172.5 km/h | 0.788 | 0.566 | 0.952 | 0.59 |
| 自由行驶 10 车 | 1.288 | 1.066 | 1.515 | 0.70 |
| 自由行驶 20 车 | 2.015 | 1.793 | 1.851 | 0.97 |
| **自由行驶 30 车** | **2.669** | 2.447 | 2.512 | **0.97** |
| 密集碰撞 10 车 | 1.668 | 1.446 | 1.446 | 1.00 |
| 密集碰撞 30 车 | 3.309 | 3.087 | 2.872 | 1.08 |
| **密集碰撞 50 车** | 6.583 | 6.361 | 3.022 | **2.11** |
| **密集碰撞 80 车** | 9.060 | 8.838 | 3.963 | **2.23** |
| **密集碰撞 120 车** | **23.741** | 23.519 | 9.437 | **2.49** |
| 270 NPC 种群 @ `Workspace` | 4.789 | 4.567 | 2.329 | 1.96 |
| 270 NPC 种群 @ `Camera` | 4.531 | 4.309 | 3.052 | 1.41 |
| **种群 + 30 辆全速车（真实会话形态）** | **7.163** | 6.941 | 3.088 | **2.25** |

**关键形态：低负载下云端 ≈ 本机甚至更快；分歧只在接触密集的超线性区出现。**

真实会话形态（270 移动对象 + 30 辆玩家车全速）= **7.16 ms = 16.67 ms 帧预算的 43%**，
`RealPhysicsFPS` 59.82。本机同负载 3.81 ms / 22.8% —— **引用本机数字会低估一倍**。

## 5. 超线性拐点：存在，且云端明显前移

固定 60×60 场地、车数递增 = 密度递增 = 单一大接触岛：

| N | 云端均值 / 峰值 / 物理FPS | 本机均值 / 峰值 / 物理FPS | 邻接接触/车 |
| ---: | --- | --- | ---: |
| 50 | 6.583 / 7.244 / 59.85 | 3.634 / 3.813 / 59.88 | 5.4~5.5 |
| 80 | 9.060 / 9.501 / 59.72 | 4.575 / 4.687 / 59.88 | 6.4 |
| **120** | **23.741 / 41.702 / 28.45** | 10.049 / 20.049 / 55.83 | 7.8~8.3 |

- 云端 **120 车彻底崩**：峰值 41.7 ms 是帧预算的 2.5 倍，物理帧率掉到 28。本机同场景仍能跑。
- 云端 **80 车已占 54% 预算**。
- **自由行驶（接触≈0）时缩放是次线性的**，每车边际仅 0.03~0.08 ms，0→3 车的固定"物理激活"
  开销就占 ~0.95 ms。**拐点只在接触密集时出现。**

⇒ **可用车辆/对象密度上限由云端决定，不由开发机决定。** 只测本机会把上限高估一倍以上。

## 6. Camera 免复制：成立，且不额外收费

把实例挂到服务端 `Camera` 下 → **客户端完全收不到，但服务端保留完整物理与碰撞**。

| | 服务端 raycast | 服务端碰撞 | 客户端可见实例 |
| --- | --- | --- | ---: |
| `Workspace` 下 270 对象 | ✅ | ✅ | **1220（全收）** |
| `Camera` 下 270 对象 | ✅ | ✅ | **0** |

- **在 `AuthorityMode=Server` + `NextGenerationReplication=Enabled` 下依然成立**（新复制层
  没破坏这个技巧），本机 Studio 与真实云端服务器双重确认。
- `Camera` 下的实例**可以在 `BindToSimulation` 模拟相内读写**，与 `Workspace` 内实例行为
  一致（同一回调内两者同样位移 0.0098）⇒ 不会出现"两套模拟纪律"。
- **物理成本不额外收费**：云端 Camera 净 4.309 vs Workspace 净 4.567，**Camera 便宜 5.6%**。

> ⚠️ 本机 Studio 曾测出"Camera 贵 31%"，**那是单进程假象，已被云端数据推翻**。见下节坑 1。

## 7. `StreamingEnabled` 不会流送运行时创建的实例

同一客户端、角色锚定在 8600 studs 外：

| 内容来源 | 服务端实例 | 客户端实例 |
| --- | ---: | ---: |
| place 文件里的美术 | 2532 | 810（流走了） |
| **运行时 spawn 的 270 个 NPC** | 4053 | **4053（一个没流走）** |

更准的口径（后续实验补充）：「**已经流入的运行时实例不会再流出**」——建在客户端从未加载过
的区域的实例不会被发送。两种表述对结论一致：**不能靠 streaming 削运行时对象的复制量**。

用户读 Studio 网络面板佐证：角色在种群中间 ~500 KB/s，拉到 8600 studs 外 **~600 KB/s，
不降反升**。⇒ 大规模 NPC/交通必须自建兴趣管理，这一条**与 `AuthorityMode` 正交**，两种
模式下都成立。

## 8. 测量陷阱（八条，全部踩过）

1. **`Stats.DataReceiveKbps` 不可用。** Studio 单进程恒 `0`；**真实云端会话恒 `1`**——
   即便客户端确实收到了 1220 个实例仍读 1。**与实际复制量无关，不要用它出带宽数字。**
   目前只能用「客户端可见实例数」当代理指标。
2. **Open Cloud Luau Execution 测不了物理。** 它跑在**非运行态 DataModel**：
   `RunService:IsRunning()=false`、自由落体球 1 秒下落 **0 studs**、`PhysicsStepTimeMs=0`
   （心跳是真的，60 次 `Heartbeat` 耗时 0.996s）。**云端物理只能靠真人发布 place + 加入。**
3. **`Part.Size` 上限 2048 studs，超出被静默截断。** 写 8000 的跑道实际只有 2048，
   测试车在采样窗口冲出边缘自由落体，速度读数变成落体速度。必须加"是否掉出场地"的校验。
4. **轮子空转**：直接把 `HingeConstraint.AngularVelocity` 设成目标转速 → 车**完全不动**，
   但物理成本反而更高（持续滑移接触）。必须斜坡加速，并用"实际在动的车数"校验。
5. **铰链轴向**：轮子的 `Attachment` 主轴（X 轴）就是底盘横向，**不要**再绕 Z 转 90°——
   那会把滚动轴转成转向轴，车永远不动。
6. **单位换算**：`STUD_METERS = 0.28`，km/h = studs/s × 0.28 × 3.6 ≈ **studs/s × 1.008**
   （数值上 studs/s ≈ km/h）。**把 studs/s 当 m/s 乘 3.6 会高估 3.6 倍。**
7. **`PhysicsStepTimeMs` 是并行求解器的墙钟时间，不是可加的 CPU 时间。** 分离的物理岛会被
   并行求解：实测 30 辆车单独测净 2.512 ms，叠加到 270 对象种群上时边际只有 0.231 ms
   （两者分处 y=8 与 y=400 的独立岛）。**真实地图空间交织后并行度下降，叠加数是下界。**
8. **别把逐车串行的 harness 读成单车成本。** 一个"每辆车依次跑油门/转向/刹车"的 benchmark
   给出的 0.38 ms 是"**1 车在驾驶 + 2 车静置**"的全场数，不是每车边际，`30 × 0.38` 那个
   乘法没有依据。要测 N 车同时驾驶必须真的让 N 辆一起跑。

## 9. 明确标注为**推断**（未验证）

- **云端在超线性区慢 2.1~2.5× 的原因**：推测是本机 M4 的多核在接触岛并行求解上占便宜、
  云端共享实例没有同等并行度。**验证方法**：在多种云端实例上重跑碰撞扫描，看比值是否随
  可用核数变化。
- **云端 Camera 反而便宜的原因**：推测 Studio Play 单进程没有真实复制开销，Camera 那点额外
  物理开销显得突出；真实服务器上避开 1220 个实例的复制工作反而净赚。**验证方法**：在云端
  分别量复制线程与物理线程的耗时。
- **`Camera` 下的实例不参与客户端预测**：基本由构造决定（客户端根本没有该实例，无从预测），
  但**未做双客户端验证**。对 NPC 可接受——位置由自建同步 + 客户端插值承担；但意味着
  "打 NPC"的命中判定拿不到预测，只能靠服务端位置历史回溯。

## 10. 适用边界（换硬件也不消失）

1. 上述车辆成本的测试车 = 底盘 + 4 球轮 + 4 `HingeConstraint`（5 部件 / 4 约束）。真实
   GTA 级载具约 **29 个力/约束元素**（15 `VectorForce` + 6 `Hinge` + 4 `Prismatic` +
   4 `Spring`），约 7 倍。**这些数字确立的是缩放形态与硬件比值，不是生产车的绝对成本。**
2. 自由行驶组车间无碰撞、无转向。
3. 全部测量为**单玩家**、ping 0.1~0.2 ms（本机）或单人云端会话。**真实延迟下的预测/
   重模拟行为、多客户端带宽行为均未测。**
4. 云端服务器为共享实例，邻居负载不可控、不可复现；单次测量有系统性噪声。
5. 云端 place 是裸场景（仅 baseplate），无美术、无实际流送压力。
