# Technical notes

## Why the Model AssetId is not enough

`rbxcloud assets create --asset-type model-fbx` returns a Roblox **Model asset** identifier. It is valid for `InsertService:LoadAsset`, but it is not interchangeable with the `MeshPart.MeshId` values created by the Roblox FBX importer.

The authoritative boundary is therefore:

```text
Model AssetId
  -> InsertService:LoadAsset
     -> returned Model pivot and hierarchy
        -> child MeshPart.MeshId / Size / CFrame
```

The generic converter does not need to predict or locally reconstruct these facts. It asks Roblox to load the asset and serializes the returned Model directly.

The same boundary is authoritative for scale. Successful upload and a non-empty
RBXM do not prove that FBX units survived import. The cloud task therefore records
the aggregate bounds and each MeshPart's size and position. Callers with an
authoritative source size should pass it through `--expected-size`; the converter
compares each axis using a relative tolerance, independent of the caller's unit
system.

## Why cloud binary serialization is used

Open Cloud Luau Execution supports binary output. The task runs:

```lua
local loaded = InsertService:LoadAsset(assetId)
local buffer = SerializationService:SerializeInstancesAsync({ loaded })
return { BinaryOutput = buffer }
```

The signed `binaryOutputUri` is downloaded immediately and saved as `.rbxm`. This preserves more arbitrary FBX importer output than a MeshPart-only JSON reconstruction, including nested Models and importer-created child instances.

## Checkpoint identity

The upload checkpoint is reusable only when all of these match:

- exact FBX SHA-256;
- uploader recipe version;
- Creator type;
- Creator ID;
- successful numeric Model AssetId.

Changing the output path does not require a new Roblox asset. Changing FBX bytes or Creator does.

## Known compatibility boundary

Roblox Studio can open the engine-generated RBXM directly. Some older rbx-dom/dmf builds have rejected engine-written properties whose wire encoding differs from their local schema. That is a consumer-parser compatibility issue, not proof that the RBXM or upload is invalid.

If a downstream project requires local rbx-dom parsing, use that project's proven cloud-facts-to-local-serialization path or upgrade the parser. Do not silently flatten the model or replace cloud pivots/CFrames with guessed transforms.

## What “any FBX” means

The converter accepts an FBX at any local path without a Unity project, manifest, GUID convention, upload queue, or project-specific registry. Roblox still controls accepted FBX features, moderation, mesh limits, size normalization, embedded material handling and permissions.

The output contains whatever Roblox's current `model-fbx` importer returns. External textures and separately published animation assets are outside this converter's responsibility.

## Scale provenance

This skill deliberately has no default game unit. A source may use studs, meters,
centimeters, tile-local units, or another convention. The calling project owns:

- the expected three-axis bounds;
- the DCC-to-game conversion;
- scene-origin and pivot policy;
- any world placement transform applied after import.

For Blender FBX, `Apply Scalings = FBX Unit Scale` avoids a common default-export
scale mismatch. This is an FBX metadata/export rule, not a declaration that every
project uses the same geometry unit. A dimension-sensitive run is verified only
when the project-provided expected size matches the cloud-loaded bounds.
