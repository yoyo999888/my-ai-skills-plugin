---
name: unity-to-blender-export
description: 把 Unity 工程(fbx→prefab→scene)一比一导出为可编辑的 Blender 工程(prefab 库 collection + 场景 collection instance),含全套 Unity/Blender 脚本与坐标共轭、逐实例 override、性能坑的实证经验。当用户要把 Unity 场景/资产包迁到 Blender 编辑、或问 Unity 转 Blender 怎么做时使用。触发词:unity 转 blender、unity 导出 blender、unity-to-blender、prefab 转 collection。
---

# unity-to-blender-export

把 Unity 工程完整镜像成**可编辑**的 Blender 工程,三层语义一比一保留:

| Unity | Blender | 编辑语义 |
|---|---|---|
| fbx(几何源) | 全库共享 mesh data(内容去重) | 改一处全联动 |
| prefab | 库 .blend 里一个 collection(内部树保留) | 改 collection,所有实例联动 |
| scene | 场景 .blend 的 collection instance + 分组 empty 树 | 挪实例只动一份 |

核心原则:**Unity 的语义让 Unity 解算**(材质绑定/嵌套 prefab/override 全部由 Unity 导出确定结果),不要手写 .prefab/.unity YAML 父链数学(实证会把建筑摆散);**验证以数值为准,渲染只做定性**(基线 glb 也可能失真)。

## 何时使用

- 要把 Unity 资产包/场景迁到 Blender 做日常编辑(迁完与 Unity 无关)。
- 只想要单个 prefab/建筑的正确回导(几何+材质+层级)。

## 步骤

1. **Unity 侧四个导出**(`scripts/GltfExporter.cs` 放进工程 `Assets/Editor/`,batchmode 逐个调用,见 `scripts/run_manifests.sh`、`scripts/run_export_prefabs.sh`):
   - `ExportSceneManifests`:每场景一份实例清单 JSON(实例名/层级路径/prefab+guid/世界矩阵/激活态/**mods 精确 diff**);
   - `ExportPrefabs`:逐 prefab 导 glb(**根 TRS 归零**防双重变换;**全激活导出 + inactive sidecar**,因 glTFast 只导 active 节点);
   - `ExportLooseNodes`:不属于任何 prefab 的场景散件(天穹/云/山)一个 glb,世界坐标烘焙;
   - `ExportMaterialPalette`:全部 .mat 各挂一个 cube 导 glb——只被场景 override 引用的材质不在任何 prefab glb 里,必须补全集。
2. **Blender 侧构建**(顺序执行):
   - `gen_prefab_list.py` 汇总清单 → `build_prefab_library.py` 建库(mesh/材质/贴图三级去重,collection **不挂场景、fake_user 持久化**——挂场景会触发 depsgraph 平方级,实测 28 倍差距);
   - `add_palette_to_library.py` 并入材质全集(只补缺,**绝不重命名已有材质**——场景按名链接,改名断链);
   - `build_scene.py` 装配场景:纯净实例 = collection instance;带 mods 实例 = 按 (prefab, mods签名) 去重的**变体 collection**(实体拷贝但 mesh 仍链接库);
   - `patch_scene_materials.py` 按实例 custom props 里的 mods 补打材质 override(幂等,场景免重建)。
3. **数值验证**(必做,勿只看渲染):
   - `verify_manifest_vs_glb.py`:全体实例世界矩阵 vs 整场景基线 glb,同时实证坐标共轭——**Unity→glTF = flipX 共轭** `C=diag(-1,1,1)`,glTF→Blender = `(x,y,z)→(x,-z,y)` 共轭,合成 `K=CONV@C`,`E_blender = K M_unity K⁻¹`(局部矩阵同式);
   - `verify_prefab_subtree.py`:prefab 内部链 × 实例矩阵 vs 基线子树,逐节点比对;
   - `render_snapshot.py` 同机位定性对比(注意排除并隐藏 SkyDome/Cloud,否则相机怼穹面)。
4. **命名/身份双轨制**:显示名用 Unity 名(容忍 Blender `.001` 后缀/63 字节截断),机器身份挂 custom props(`unity_path`/`guid`/`u_path` 资产侧消歧路径)。

## 关键坑(详见 references/pitfalls.md,均为实证)

- override 的 tpath 必须用**资产侧消歧路径**(场景节点会被改名;同名兄弟按局部坐标 round 1e-3 排序加 `#k`);嵌套 prefab 的 corresponding 会解析到子资产,要用「纯净实例路径映射」查表(失败率 45%→0%);
- 实例里加塞的嵌套 prefab(如车内角色)用 `GetAddedGameObjects` 识别,整棵记一条 added,别逐骨骼 diff;
- glTFast 会把 png 重编码为 jpg 且内嵌图可能损坏:贴图按 **stem** 匹配磁盘源图,源图为真相,外链不打包;
- Unity 编译错误会静默用旧程序集跑完且 exit 0:跑完必须 grep `error CS`;同工程 Unity 单实例;
- 长任务输出别 `| tail`(缓冲),用 `grep --line-buffered > file`。
