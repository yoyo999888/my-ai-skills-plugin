#!/usr/bin/env bash
# 三场景 → prefab 实例清单 JSON(单次 Unity 会话)
set -euo pipefail
UNITY="/Applications/Unity/Hub/Editor/6000.4.0f1/Unity.app/Contents/MacOS/Unity"
UPROJ="/shared/gta-resources/unity_gltf_proj"
OUT="/shared/gta-resources/gta-city-resource/BlendPoly-Modular-City/blender-resources/manifests"
export EXPORT_SCENES="Assets/BlendPoly Modular City/Scenes/DemoScenes/CityCenter.unity,Assets/BlendPoly Modular City/Scenes/DemoScenes/Port_Island.unity,Assets/BlendPoly Modular City/Scenes/DemoScenes/University_Island.unity"
export EXPORT_MANIFEST_DIR="$OUT"
LOG="${UNITY_LOG:-/tmp/unity_manifests.unitylog}"
"$UNITY" -batchmode -nographics -projectPath "$UPROJ" \
  -executeMethod GltfExporter.ExportSceneManifests -logFile "$LOG" -quit || true
grep -E "MANIFEST_OK|Exception|error CS" "$LOG" | tail -20
