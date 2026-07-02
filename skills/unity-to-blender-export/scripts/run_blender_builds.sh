#!/usr/bin/env bash
# Blender 侧:prefab 库 + 三场景。用法:
#   ./run_blender_builds.sh library <prefab_list.txt>
#   ./run_blender_builds.sh scene <SceneName> <flipX|flipZ> [--only-available]
set -euo pipefail
BR="/shared/gta-resources/gta-city-resource/BlendPoly-Modular-City/blender-resources"
GLBROOT="/shared/gta-resources/unity_gltf_proj/Export/prefabs"
case "$1" in
  library)
    blender -b --python "$BR/pipeline/build_prefab_library.py" -- \
      "$GLBROOT" "$2" "$BR/manifests/prefab_guids.json" \
      "$BR/prefab_library.blend" "$BR/textures" ;;
  scene)
    LOOSE="/shared/gta-resources/unity_gltf_proj/Export/loose/$2_loose.glb"
    blender -b --python "$BR/pipeline/build_scene.py" -- \
      "$BR/manifests/$2.manifest.json" "$BR/prefab_library.blend" \
      "$BR/scenes/$2.blend" "$LOOSE" "${3:-}" ;;
  *) echo "用法见头部注释"; exit 2 ;;
esac
