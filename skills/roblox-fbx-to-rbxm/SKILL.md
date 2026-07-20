---
name: roblox-fbx-to-rbxm
description: 将任意路径的本地 FBX 通过 Roblox Open Cloud 上传为 Model，再用云端 LoadAsset 取回并生成保留原始层级与 pivot 的 .rbxm；当用户要上传 FBX、批量上传模型、取得 Roblox Model/Mesh 资产或把 FBX 转成 RBXM 时使用。触发词：上传 fbx、fbx 转 rbxm、fbx-to-rbxm、Roblox mesh upload、生成 rbxm。
---

# roblox-fbx-to-rbxm

把任意来源、任意目录的单个 `.fbx` 走完以下链路：

```text
local FBX
  -> rbxcloud assets create --asset-type model-fbx
     -> Roblox Model AssetId
        -> Open Cloud Luau Execution
           -> InsertService:LoadAsset(Model AssetId)
              -> SerializationService:SerializeInstancesAsync
                 -> local .rbxm
```

使用 `scripts/fbx_to_rbxm.py`，不要复制某个项目的 upload queue、Unity manifest 或建筑命名规则。脚本直接序列化云端 `LoadAsset` 返回的 Model，不把模型拍平为一组重新推算位置的 MeshPart，因此会保留 Roblox 导入后的层级、Model pivot、子件 CFrame、MeshId 和 Roblox 实际生成的其他子实例。

## 何时使用

- 用户给出一个任意路径的 FBX，要求上传 Roblox 并得到 `.rbxm`。
- 已有上传结果中断在 LoadAsset/RBXM 阶段，需要复用 checkpoint 继续。
- 要为一批互不相关的 FBX 分别生成可插入 Studio 的 Model 文件。

这不是材质制作或场景装配技能。外部贴图、SurfaceAppearance、动画发布、世界尺度换算和 prefab/scene transform 应按所属项目另行处理；本技能保存的是 Roblox importer 实际返回的 Model。

## 前置条件

1. 安装 `rbxcloud`，并可从 `PATH` 调用。
2. 准备一个 Open Cloud API key，至少能：
   - 以目标 user/group 创建 Asset；
   - 在指定 universe/place 创建并读取 Luau Execution task。
3. 测试 Place 必须能 `LoadAsset` 目标 Creator 的私有 Model。
4. 推荐通过 `ROBLOX_UPLOADER_CONFIG` 指向配置文件，不要把 API key 写在命令行、技能或仓库中。

配置兼容现有 uploader 格式：

```json
{
  "robloxApiKey": "<secret>",
  "owner": { "type": "user", "id": "123456" },
  "luauExecution": {
    "universeId": "123456789",
    "placeId": "987654321"
  }
}
```

也支持环境变量：

```text
RBXCLOUD_API_KEY
RBXCLOUD_CREATOR_ID
RBXCLOUD_CREATOR_TYPE=user|group
ROBLOX_LUAU_UNIVERSE_ID
ROBLOX_LUAU_PLACE_ID
```

## 标准流程

先定位本技能目录；不要假设当前工作目录就是插件仓库：

```bash
SKILL_DIR="<本 SKILL.md 所在目录>"
```

### 1. 必须先 dry-run

```bash
python3 "$SKILL_DIR/scripts/fbx_to_rbxm.py" /absolute/path/model.fbx \
  --output /absolute/path/model.rbxm
```

不带 `--execute` 时只输出计划，不上传、不创建 Luau task、不写 RBXM。检查：

- 输入确实是 `.fbx` 且文件存在；
- Creator 类型/ID 正确；
- Luau Execution universe/place 正确；
- 输出不会覆盖不应覆盖的文件；
- `wouldUpload` 是否符合预期。

### 2. 用户明确要求上传后才执行

上传是外部持久变更。得到用户授权后执行：

```bash
python3 "$SKILL_DIR/scripts/fbx_to_rbxm.py" /absolute/path/model.fbx \
  --output /absolute/path/model.rbxm \
  --execute
```

默认同时生成：

```text
model.rbxm                 # 云端 LoadAsset Model 的 Roblox 二进制模型
model.rbxm.upload.json     # FBX SHA-256 -> Model AssetId checkpoint
model.rbxm.report.json     # task、Model、子件数量和输出校验报告
```

脚本在上传成功后立即写 checkpoint。若 Luau Execution、LoadAsset 或下载临时失败，重跑同一命令会按 FBX SHA-256、Creator 和上传 recipe 复用原 AssetId，不重复创建资产。

只有明确需要创建替代资产时才加：

```bash
--force-upload
```

### 3. 验证交付

成功条件必须同时满足：

- 报告中 `status` 为 `complete`；
- `modelAssetId` 为数字；
- `summary.status` 为 `loaded`；
- `.rbxm` 非空且包含 Roblox 二进制模型头；
- `meshPartCount` 与预期相符；若 FBX 本来应有 mesh 而结果为 0，视为失败。

可直接打开检查：

```bash
open /absolute/path/model.rbxm
```

如果用户要把模型加入现有 `.rbxl`，再使用适合 Roblox model/place IO 的流程导入；不要为此重传 FBX。

### 4. 批量文件

每个 FBX 单独生成一个 Model/RBXM，避免把无关资产包成一个不可独立复用的根 Model：

```bash
find /absolute/input -type f -iname '*.fbx' -print0 | while IFS= read -r -d '' fbx; do
  stem="$(basename "${fbx%.*}")"
  python3 "$SKILL_DIR/scripts/fbx_to_rbxm.py" "$fbx" \
    --output "/absolute/output/${stem}.rbxm" \
    --execute
done
```

批量前先挑一个代表性 FBX 完成 dry-run、上传、LoadAsset 和 Studio 视觉检查，再展开全量。

## 关键规则

- 上传返回的是 **Model AssetId**，不是最终 `MeshPart.MeshId`；必须以云端 `LoadAsset` 结果为准。
- 不根据 FBX 文件名猜 MeshId，不用 Model AssetId 冒充 MeshId。
- 不拍平或重新推算子 MeshPart transform；`.rbxm` 直接来自云端 Model 序列化。
- 不把 API key 输出到日志、命令参数或产物；报告只保留非秘密 ID。
- 不用 `--force-upload` 处理普通重试；它会创建新的 Roblox Asset。
- “任意 FBX”表示不依赖特定项目目录或 manifest，不代表绕过 Roblox 的格式、审核、三角面、尺寸和权限限制。
- FBX 的外部贴图不会自动成为可靠的项目材质真相。需要可控 PBR/贴图时，单独上传并在 prefab 组装层绑定。

## 故障处理

- `rbxcloud` 创建成功但暂时不能 `LoadAsset`：保留 checkpoint，稍后原命令重跑；不要强制重传。
- `403`：检查 API key scope、Creator 权限和 Luau Execution universe/place 权限。
- `load_failed`：检查测试 Place 是否能访问该 Creator 的私有 Asset，以及资产是否仍在审核/处理中。
- FBX 中单件尺寸超过 Roblox 上限时，Roblox 可能等比归一化；应在源资产阶段预缩放或切块。
- 云端 `SerializationService` 生成的 `.rbxm` 可由 Studio 原生打开；老版本 rbx-dom/dmf 若报属性 wire type 不兼容，不要丢弃或拍平模型，优先升级解析器，或另走项目已有的 JSON facts + 本地 Lune 序列化路径。

实现细节与产物语义见 `references/technical-notes.md`。
