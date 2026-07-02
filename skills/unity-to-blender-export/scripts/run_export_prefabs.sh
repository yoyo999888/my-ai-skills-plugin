#!/usr/bin/env bash
# prefab 清单 → 逐个 glb(单次 Unity 会话,镜像 Assets 相对路径)
# 用法: ./run_export_prefabs.sh <prefab_list.txt> [READABLE=1]
set -euo pipefail
UNITY="/Applications/Unity/Hub/Editor/6000.4.0f1/Unity.app/Contents/MacOS/Unity"
UPROJ="/shared/gta-resources/unity_gltf_proj"
export EXPORT_PREFAB_LIST="$1"
export EXPORT_PREFAB_DIR="/shared/gta-resources/unity_gltf_proj/Export/prefabs"
export EXPORT_READABLE="${2:-0}"
LOG="${UNITY_LOG:-/tmp/unity_prefabs.unitylog}"
"$UNITY" -batchmode -nographics -projectPath "$UPROJ" \
  -executeMethod GltfExporter.ExportPrefabs -logFile "$LOG" -quit || true
grep -E "PREFAB_DONE|PREFAB_PROGRESS|PREFAB_FAIL|Exception|error CS" "$LOG" | tail -30
