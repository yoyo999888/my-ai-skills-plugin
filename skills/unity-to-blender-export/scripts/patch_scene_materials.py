#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""场景补丁:按实例 custom props 里存的 mods,补打建场景时缺库的材质 override。

实例 empty 的 ['mods'](JSON)是完整数据源,场景无需重建;
材质查找:精确名 → 基名(库里个别 canonical 带 .00N 后缀)。幂等,可重复跑。

用法: blender -b <scene.blend> --python patch_scene_materials.py -- <library.blend>
"""
import bpy, sys, json, re

argv = sys.argv[sys.argv.index("--") + 1:]
LIB = argv[0]
BASE_RE = re.compile(r'\.\d{3}$')
base = lambda n: BASE_RE.sub('', n)

with bpy.data.libraries.load(LIB, link=True) as (src, dst):
    dst.materials = list(src.materials)

def resolve(name):
    m = bpy.data.materials.get(name)
    if m is not None: return m
    for m in bpy.data.materials:
        if base(m.name) == name: return m
    return None

patched = missing = 0
seen_vcol = set()
for e in bpy.data.objects:
    if 'mods' not in e or e.instance_collection is None: continue
    vcol = e.instance_collection
    if vcol.library is not None: continue          # 纯净实例(库 collection),mods 不含可打的材质?防御跳过
    if vcol.as_pointer() in seen_vcol: continue    # 变体共享,打一次
    seen_vcol.add(vcol.as_pointer())
    mods = json.loads(e['mods'])
    matmods = [m for m in mods if m['type'] == 'materials']
    if not matmods: continue
    paths = {}
    for o in vcol.all_objects:
        paths.setdefault(o.get('u_path', ''), []).append(o)
    for m in matmods:
        tgt = paths.get(m.get('tpath', ''), [])
        if len(tgt) != 1: missing += 1; continue
        o = tgt[0]
        for i, slot in enumerate(o.material_slots):
            if i >= len(m['value']): break
            want = m['value'][i]
            cur = slot.material.name if slot.material else ''
            if cur == want or base(cur) == want: continue
            mat = resolve(want)
            if mat is None: missing += 1; continue
            slot.link = 'OBJECT'
            slot.material = mat
            patched += 1

bpy.ops.wm.save_mainfile()
print(f'PATCH_OK patched={patched} still_missing={missing} scene={bpy.data.filepath}')
