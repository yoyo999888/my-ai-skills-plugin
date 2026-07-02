# Unity→Blender 导出:踩坑全记录(现象 → 根因 → 修法)

来源:BlendPoly 城市包(3,238 prefab / 126k 实例 / 三场景)完整迁移,2026-07-02。全部实证。

## 1. Blender 批量导入平方级恶化
现象:3,238 个 glb,86 分钟才导 1,200 个且每批越来越慢。
根因:每次 `import_scene.gltf` 触发对场景内全部已积累对象的 depsgraph 更新。
修法:prefab collection **不挂场景**,`use_fake_user=True` 持久化(libraries.load 照常可 link)。同位置 28 倍提速,全量 117 分钟完成。

## 2. 内嵌贴图囤积爆内存
现象:导入途中 packed image 涨到近 4,000 张。
修法:**增量去重**——每个 glb 导完立刻按 stem 归一 + 周期 batch_remove 孤儿;canonical dict 在 purge 时同步剔除死指针(否则悬空引用崩溃)。全程贴图数恒定。

## 3. glTFast 只导 active 节点
现象:prefab 内默认禁用的堆叠备选件在 glb 里消失,实例级 active:true override 无对象可用。
修法:导出前整树 SetActive(true),原禁用清单写 sidecar json;Blender 侧按 sidecar 隐藏(hide 沿子树传递,对应 Unity activeSelf 语义)。

## 4. override 目标路径三连坑(失败率 45% → 0%)
1) 场景里节点会被改名(`墙 (3)`):tpath 必须用资产侧名字;
2) 资产内同名兄弟:路径段加 `#k` 消歧,k = 按 Unity 局部坐标 round(1e-3) 排序 + sibling index tiebreak,Blender 侧同一约定(每对象存 `u_path` custom prop,查表应用,不做名字猜测);
3) 嵌套 prefab 的 `GetCorrespondingObjectFromSource` 解析到子 prefab 资产,直接拼路径缺前缀。
终极修法:对每个 prefab 临时 InstantiatePrefab 建「`GetCorrespondingObjectFromOriginalSource(节点)` → 消歧路径」查找表(与 prefab glb 天然一致),diff 时查表。

## 5. 实例内加塞的嵌套 prefab(车内角色)
现象:载具实例里塞的角色刷出上千条骨骼级假 transform mods。
修法:`PrefabUtility.GetAddedGameObjects` 识别新增子树,整棵记一条 added(带 prefab 身份 + 局部矩阵);Blender 端在变体里挂子 collection instance。

## 6. prefab 根 TRS 双重变换
场景实例会整体替换根变换(manifest 矩阵就是它),prefab glb 若还带资产根自身 TRS 即双重变换。导出前根 TRS 归零。

## 7. 材质三坑
- glTFast 把 png 重编码 jpg、内嵌图可能坏:按 stem 匹配磁盘源图(png 优先),源图为真相,外链不打包;
- 只被场景 override 引用的材质不在任何 prefab glb:导材质调色板 glb(全部 .mat 各挂一个 cube)补全库;
- canonical 材质可能顶着 `.00N` 名:**不要重命名**(场景按名字链接,改名断链),查找用「精确名 → 基名」两级匹配。

## 8. 变体对象数预算
逐实例 override 全量实体拷贝会爆(估 36 万对象)。闸门:按 (prefab, mods签名) 去重(14k 实例→3.6k 变体)+ 资产内禁用子树不拷贝(除非 active:true 涉及)。mesh data 始终链接库,零几何复制。

## 9. 渲染验证的坑
- 场景可能自带巨型 SkyDome + 云海:自动取景会把相机怼在穹面上,穹外相机又被穹面全挡——渲染脚本按名排除取景 + hide_render;
- 渲染会骗人,基线也会骗人(整场景基线 glb 可能是「隐藏对象全激活」导出的失真参考):对错判定以数值比对为准(矩阵/顶点),真值裁判用引擎原生截图。

## 10. 工程习惯
- 长任务输出别 `| tail`(缓冲到结束才可见),用 `grep --line-buffered > file`;
- Unity 同工程单实例,上一个 batchmode 未退干净下一个直接 fatal;
- Unity 编译错误会静默用旧程序集跑完且 exit 0:跑完必须 grep `error CS`;
- 大批量删数据块用 `bpy.data.batch_remove`。

## 坐标系(实证,勿凭记忆)
- Unity→glTF:flipX 共轭 `M_gltf = diag(-1,1,1) @ M_u @ diag(-1,1,1)`(24,169 实例 vs 基线,误差 1e-7;flipZ/identity 全灭);
- glTF→Blender:`(x,y,z)→(x,-z,y)` 共轭;
- 合成 `K = CONV @ C`;实例摆放与局部矩阵都是 `K M K⁻¹`(共轭对链封闭);
- 位置向量换算:`p_unity = (-x_b, z_b, -y_b)`(反向同理)。

## 验证结果基准(供新迁移对照)
- 纯净实例子树:逐节点 0 超差;
- override 应用后重算世界矩阵:0 超差;
- mods 路径解析:0.00% 失败;
- 性能:manifests ~4min / 3,238 prefab glb ~15min / 库 117min / 场景 20-100min。
