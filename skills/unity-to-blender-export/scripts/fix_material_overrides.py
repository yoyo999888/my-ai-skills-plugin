#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""事后应用材质 override(免重建场景):
打开场景 .blend → 从库链入全部材质(含调色板)→ 对每个带 mods 的实例,
在其变体 collection 的对象上按 u_path 重放 type=materials 的 mod(每变体一次)。
用法: blender -b --python fix_material_overrides.py -- <scene.blend> <library.blend>
"""
import bpy, sys, json

argv = sys.argv[sys.argv.index("--") + 1:]
SCENE, LIB = argv[0], argv[1]

bpy.ops.wm.open_mainfile(filepath=SCENE)
have = {m.name for m in bpy.data.materials}
with bpy.data.libraries.load(LIB, link=True) as (src, dst):
    dst.materials = [m for m in src.materials if m not in have]

done_cols = set()
applied = miss_mat = miss_path = 0
for e in bpy.data.objects:
    mods_json = e.get('mods')
    if not mods_json or e.instance_collection is None: continue
    col = e.instance_collection
    if col.library is not None: continue          # 纯净实例(库 collection)不该有 mods,跳过
    if col.as_pointer() in done_cols: continue    # 同签名变体只应用一次
    done_cols.add(col.as_pointer())
    paths = {}
    for o in col.objects:
        paths.setdefault(o.get('u_path', ''), []).append(o)
    for m in json.loads(mods_json):
        if m['type'] != 'materials': continue
        tgt = paths.get(m.get('tpath', ''), [])
        if len(tgt) != 1: miss_path += 1; continue
        o = tgt[0]
        for i, slot in enumerate(o.material_slots):
            names = m['value']
            if i < len(names):
                mat = bpy.data.materials.get(names[i])
                if mat is None: miss_mat += 1; continue
                slot.link = 'OBJECT'; slot.material = mat
        applied += 1

bpy.ops.wm.save_mainfile()
print(f'MATFIX_OK 变体={len(done_cols)} 应用={applied} 缺材质={miss_mat} 路径未中={miss_path} -> {SCENE}')
