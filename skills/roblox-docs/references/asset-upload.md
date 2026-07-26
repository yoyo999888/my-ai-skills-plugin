# 资产上传（Open Cloud）

> 验证日期 2026-07-27。工具：`rbxcloud` 0.17.0 + `roblox-fbx-to-rbxm` 技能。

## 两条链路

### mesh：FBX → Model AssetId → MeshId

用同仓库的 `roblox-fbx-to-rbxm` 技能：

```
local FBX -> rbxcloud assets create --asset-type model-fbx
          -> Model AssetId
          -> Open Cloud Luau Execution: InsertService:LoadAsset
          -> SerializationService:SerializeInstancesAsync -> 本地 .rbxm
```

上传返回的是 **Model AssetId，不是 MeshId**。真正的 `MeshPart.MeshId`
要从报告 JSON 的 `summary.meshParts[].meshId` 里取。

必须先 dry-run（不带 `--execute`）确认 creator / universe / place / expected-size，
再执行。`--expected-size` 要用源文件的真实包围盒，不能凭经验拍。

⚠️ **FBX 是 Y-up、Blender 是 Z-up**：Blender 里的 `(X, Y, Z)` 传给
`--expected-size` 时要写成 `(X, Z, Y)`。

### 贴图：PNG → Decal AssetId

```bash
rbxcloud assets create --asset-type decal-png \
  --display-name "<name>" --description "<desc>" \
  --creator-id <id> --creator-type user \
  --filepath /abs/path.png --api-key "$KEY"
```

返回的是**异步 operation**，要轮询才拿得到 assetId 和审核状态。

## 两个坑

1. **`RBXCLOUD_CREATOR_ID` 环境变量可能和 API key 实际所属账号不一致**，
   直接跑会 403：
   `User <A> is unauthorized to create an Model asset as User <B>`。
   以配置文件里的 `owner.id` 为准，显式 `export RBXCLOUD_CREATOR_ID=<owner.id>` 覆盖。

2. **`rbxcloud assets get` 没有 `--operation-id` 参数**（只有 `--asset-id`），
   贴图上传的异步 operation 必须直接打 REST：

   ```bash
   curl -H "x-api-key: $KEY" \
     "https://apis.roblox.com/assets/v1/operations/<operationId>"
   ```

   返回里看 `done` / `response.assetId` / `response.moderationResult.moderationState`。

## 凭证

Open Cloud **不吃 `.ROBLOSECURITY` cookie**，必须是 API key。
需要的 scope：`asset:read` + `asset:write`，以及绑定某个 universe/place 的
**Luau Execution** 权限（`roblox-fbx-to-rbxm` 靠它把 Model 取回本地）。

推荐用 `ROBLOX_UPLOADER_CONFIG` 指向一个配置文件，**不要把 key 写进命令行**：

```json
{
  "robloxApiKey": "<secret>",
  "owner": { "type": "user", "id": "..." },
  "luauExecution": { "universeId": "...", "placeId": "..." }
}
```

## 权限观察

用 Open Cloud 上传的资产默认私有，但实测**同一账号体系下的本机 Studio 能正常
`InsertService:LoadAsset`**，不需要设为公开。跨账号未验证。
