# 原生代码生成（`--!native` / `@native`）

> ⚠️ **本条目是二手证据，不是本机实测。** 与本库其它条目不同 ——
> 来源为 Roblox 官方文档 + DevForum 社区自测，**没有一条经过本机验证**。
> 引用时必须带上这个前提。文末「待验证清单」列了该测什么。
> 整理日期：2026-09-05。官方文档快照：`create.roblox.com/docs/luau/native-code-gen`。

## 是什么

Luau 默认编译成字节码由 VM 解释执行。`--!native` 让脚本进一步编译成**宿主 CPU 机器码**
（AOT，加载时编译，不是运行时 JIT）。

**收益只来自一处**：省掉解释器的指令分发和装箱开销。
所以只对「在 Luau 里自己算」的代码有效 —— 调 Roblox API 的代码本来就已经是 C++ 了，
加了等于没加。

## 两种开启方式

脚本级，第一行（可与 `--!strict` 并存）：

```lua
--!strict
--!native
```

函数级（**更推荐**，理由见「代价」）：

```lua
@native
local function f(x: number): number
    return x + 1
end
```

- **只有函数体会被编译。** 顶层作用域只跑一次，加了基本无收益（官方明说）。
- **编译单元 = 脚本。** `--!native` 的 Script `require` 的 ModuleScript **不会**跟着被编译，
  模块要自己加。（机制推论，未实测）
- `--!native` 不是承诺。编译器挑「有利可图」的函数编，编不动的静默回落解释执行。

## 平台支持：一条会过期的时间线

| 日期 | 事件 | 来源 |
| --- | --- | --- |
| 2023-08-31 | Studio Beta 发布 | 官方公告 |
| 2023-11-20 | staff `rep_movsb`：**只支持 Studio + 服务端**，"we will not support native code generation on clients" | bug 报告 2710130，判为 intended |
| 2024-05 | 脱 beta，服务器 + Studio 默认可用 | 官方公告 2961746 |
| 2025-06 / 2025-09 | 开发者投诉输出刷屏 `Native code generation of script =SCRIPT failed: Native code generation is not supported on this device.` ← **该警告存在本身即证明客户端已在尝试编译**，只是设备被挡 | 3767914 / 3969429 |
| 2025-10-08 | staff `WheretIB` 修掉刷屏改为一次性初始化警告；**确认 Mac 是支持的**（提问者 M1 Mac 的误解） | 3969429 |
| 2026-08-11 | bug 报告标题直接写 "**supported devices** give no warning if it chose not to compile as NCG" → 客户端设备已分「支持/不支持」两类 | 4804395 |
| 2026-09-03 | 社区报告 "they actually did enable NCG for Android devices" | 3170510 p3，**单一来源、无官方公告** |

**结论**：客户端 NCG 在**按设备灰度铺，无官方公告**。
2023 年那句「客户端永不支持」已过时，别再引用。

⚠️ **最大的坑（2023~2025 长期成立，现在部分缓解）**：LocalScript 在 Studio 里会走 native，
线上真机可能不走 → **Studio 测出的客户端加速比不可信**。
有开发者报告线上比 Studio 慢 6 倍（`EmK530`，3170510）。

## 社区实测加速比

⚠️ 全部为 DevForum 用户自测，**测量环境未标注、无原始数据、未经本库验证**。
只用来判断「量级」，不要当设计依据。

| 场景 | 加速比 | 报告人 / 日期 |
| --- | ---: | --- |
| 矩阵求逆（locomotion stepLinking） | **6x** | AxisAngle 2023-09-01 |
| Sweep 碰撞 | **4x** | AxisAngle 2023-09-01 |
| AABB 相交测试 | **2.6x** | Ax3nx 2023-08-31 |
| 第 25000 个素数（9.25s → 4.86s） | **2x** | SyntaxMenace 2024-02-17 |
| Ray→OBB 相交测试 | 1.3x | Ax3nx 2023-08-31 |
| MessagePack utf8Encode | +34% | wynnrar 2023-09-01 |
| 挖矿方块生成（170,150 → 191,791 blocks/s） | +12.7% | Alkan 2023-09-01 |
| **IK 代码** | **≈0** | AxisAngle 2023-09-01 |

### 为什么差距这么大 —— staff 给了原因

- **`zeuxcg`（2023-09-01）**：IK 那条没收益，是因为 "your IK code is using **Vector3** heavily"，
  当时 Vector3 未做特化。
  → 这正是后来官方文档增加「类型标注」一节的由来，**补标注可吃回这部分**（未实测）。
- **`WheretIB`**：依赖 table、Lua C 函数、Roblox 引擎调用越多收益越小；
  `loadstring` 出来的代码**完全不编译**。

## 类型标注决定收益上限

编译器要推断类型才能生成特化代码，推不出就走保守通用路径。官方对照例子：

```lua
--!native

local function sumComponentsSlow(v)          -- 类型未知，通用路径
    return v.X + v.Y + v.Z
end

local function sumComponentsFast(v: Vector3) -- 生成 vector 特化代码
    return v.X + v.Y + v.Z
end
```

**实践口径：`--!native` 应与 `--!strict` + 完整参数类型标注一起用。**
只加 `--!native` 不补标注是浪费。`Vector3` 是官方点名的重点。

## 不会原生执行的代码（官方明列）

- `getfenv()` / `setfenv()`（已弃用）
- Luau 内建函数收到错类型实参（例：`math.asin()` 收到非 number）
- 类型标注与实参不符的函数
- `loadstring` 产生的代码（staff 补充）

## 硬限制与报错对照

| 报错 | 含义 | 处理 |
| --- | --- | --- |
| `exceeded single code block instruction limit` | 单代码块 > **64K** 指令 | 拆函数 / 简化 |
| `exceeded function code block limit` | 单函数内部块 > **32K** | 简化控制流（大 if 链、展开循环） |
| `exceeded total module instruction limit` | 单脚本累计 > **100 万**指令 | 大函数挪到非 native 脚本，或改用 `@native` 精选 |
| `encountered an internal lowering failure` | 编译器啃不动该表达式 | 拆表达式；确属 bug 就报 |
| `Memory allocation limit reached for native code generation` | **全局**编译产物内存配额耗尽 | 见下节 |

## 三项代价（为什么不能全项目撒 `--!native`）

1. **启动时间变长** —— 机器码在加载时生成。
2. **额外常驻内存** —— 机器码远大于字节码。
3. **整个游戏有全局编译配额** —— 最要命。在 A 脚本乱加会挤掉 B 脚本真正需要的额度，
   触发上表最后一条。

→ **官方建议：默认用 `@native` 精确点热函数，而不是脚本级 `--!native` 满天飞。**

## 怎么验证真的生效

### 服务端（工具齐全）

- **Script Profiler**：原生执行的函数旁显示 `<native>`。没这标记就是回落了。
- **`debug.dumpcodesize()`**：Command Bar 的 **Server** 视图执行，输出已编译脚本/函数总数、
  占用内存、**每个函数的机器码大小**。查配额水位和定位内存大户靠它。
- **Luau Heap**：原生函数内存显示为 `[native]` 条目。

### 客户端（只有两个半）

- **F9 游戏内控制台**：设备不支持时打
  `Native code generation of script =SCRIPT failed: Native code generation is not supported on this device.`
- **LuauHeap** 的 `[native]` 条目
- **MicroProfiler**

⚠️ **`debug.dumpcodesize()` 是 Server 视图的，客户端用不了。**

⚠️ **「F9 没警告」≠「跑上了 native」。** 4804395 那条 bug 的核心投诉就是：
**支持的设备如果只是「编译器自己决定不编」，不发任何警告。**
没警告只能证明设备不是被平台挡掉的，要确认仍得看 LuauHeap。

⚠️ **从 Lua 侧没有检测 API。** 社区试过用 metamethod 行为差异探测，
在 iPhone 15 (iOS 17.5.1) 上假阳性（3080908）。别走这条路。

⚠️ **断点会关掉所在函数的原生执行**，且原生帧的 locals/upvalues 视图可能残缺。
带断点调试时看到的性能不是生产性能。

## 适用边界

- **本条目零本机实测。** 上面每个数字都是官方文档或社区自测，测量硬件、引擎版本、
  画质等级全部未知。按本库纪律，这些只能当「待验证假设」。
- **平台支持随时会变。** 客户端灰度在推进且无公告，时间线表格**每隔几个月要重查**。
- 加速比数据多为 2023-2024 年，那之后 Vector3 特化等优化已落地，**旧数字可能低估**。

## 待验证清单（本机该测什么）

1. **服务端基线**：纯数值循环 / `buffer` 操作 / `Vector3` 累加三组，
   `--!native` 开关对照，`os.clock()` 计时 + Script Profiler 确认 `<native>` 标记。
2. **类型标注增量**：同一函数有无 `v: Vector3` 标注的差异 —— 验证 zeuxcg 那条是否已修。
3. **客户端真机**：同一 LocalScript 发测试 place，在 Android / iOS / PC 各跑，
   与 Studio 数字对比，并查 F9 有无 not-supported 警告 + LuauHeap 有无 `[native]`。
   → 顺带验掉「Android 已开」那条单来源传闻。
4. **模块传递性**：`--!native` 的 Script require 未标注的 ModuleScript，
   模块函数是否被编译（验证上文那条机制推论）。
5. **配额水位**：真实项目下 `debug.dumpcodesize()` 的数字，摸清全局限额大概在什么量级。

## 来源

- 官方文档：<https://create.roblox.com/docs/luau/native-code-gen>
- 公告（Studio Beta，含 benchmark 讨论）：<https://devforum.roblox.com/t/luau-native-code-generation-preview-studio-beta/2572587>
- 公告（脱 beta 更新）：<https://devforum.roblox.com/t/luau-native-code-generation-preview-update/2961746>
- 客户端不支持（2023，已过时）：<https://devforum.roblox.com/t/native-codegen-works-in-localscripts-in-studio-but-not-in-the-client/2710130>
- 客户端开放诉求：<https://devforum.roblox.com/t/enable-native-for-clients/3170510>
- 警告不一致 bug（2026-08）：<https://devforum.roblox.com/t/native-code-generation-warning-message-inconsistency-and-confusion-supported-devices-give-no-warning-if-it-chose-not-to-compile-as-ncg/4804395>
- Mac 警告刷屏（含 WheretIB 回复）：<https://devforum.roblox.com/t/option-to-suppress-warnings-about-native-code-generation-on-mac-and-other-unsupported-devices/3969429>
- 运行时检测尝试（失败）：<https://devforum.roblox.com/t/is-there-any-possible-way-to-detect-native-code-generation/3080908>
