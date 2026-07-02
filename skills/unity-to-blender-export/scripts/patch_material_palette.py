#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把材质调色板 glb 补进 prefab_library.blend:库内已有同名材质保持不动,
缺的材质挂 fake_user 存入(贴图按 stem 重链磁盘源图);调色板几何删除。
用法: blender -b --python patch_material_palette.py -- <library.blend> <palette.glb> <textures_dir>
"""
import bpy, sys, os, re

argv = sys.argv[sys.argv.index("--") + 1:]
LIB, PAL, TEXDIR = argv[0], argv[1], argv[2]
BASE_RE = re.compile(r'\.\d{3}$')
base = lambda n: BASE_RE.sub('', n)

bpy.ops.wm.open_mainfile(filepath=LIB)
have_mats = {m.name: m for m in bpy.data.materials}
have_imgs = {}
for img in bpy.data.images:
    if img.name == 'Render Result': continue
    bn = os.path.basename((img.filepath or '').replace('\\', '/')) or img.name
    have_imgs[os.path.splitext(BASE_RE.sub('', bn))[0]] = img

before_mats = set(m.as_pointer() for m in bpy.data.materials)
before_imgs = set(i.as_pointer() for i in bpy.data.images)
bpy.ops.import_scene.gltf(filepath=PAL)
new_objs = list(bpy.context.selected_objects)

kept = dropped = 0
for m in list(bpy.data.materials):
    if m.as_pointer() in before_mats: continue
    b = base(m.name)
    if b in have_mats:
        m.user_remap(have_mats[b]); dropped += 1
    else:
        m.name = b
        m.use_fake_user = True
        have_mats[b] = m
        kept += 1

# 新贴图:stem 已有 → 重映射;新的 → 重链磁盘源图
disk_by_stem = {}
for fn in os.listdir(TEXDIR):
    s = os.path.splitext(fn)[0]
    if s not in disk_by_stem or fn.lower().endswith('.png'):
        disk_by_stem[s] = os.path.join(TEXDIR, fn)
for img in list(bpy.data.images):
    if img.as_pointer() in before_imgs or img.name == 'Render Result': continue
    bn = os.path.basename((img.filepath or '').replace('\\', '/')) or img.name
    stem = os.path.splitext(BASE_RE.sub('', bn))[0]
    if stem in have_imgs:
        img.user_remap(have_imgs[stem])
    elif stem in disk_by_stem:
        if img.packed_file: img.unpack(method='REMOVE')
        img.filepath = disk_by_stem[stem]; img.reload()
        have_imgs[stem] = img
    else:
        try: img.pack()
        except Exception: pass
        have_imgs[stem] = img

bpy.data.batch_remove(new_objs)
for _ in range(3):
    dead = [m for m in bpy.data.meshes if m.users == 0] + \
           [i for i in bpy.data.images if i.users == 0 and i.name != 'Render Result'] + \
           [m for m in bpy.data.materials if m.users == 0 and not m.use_fake_user]
    if not dead: break
    bpy.data.batch_remove(dead)

bpy.ops.wm.save_as_mainfile(filepath=LIB, relative_remap=True)
print(f'PALETTE_PATCH_OK 新增材质={kept} 已有跳过={dropped} 总材质={len(bpy.data.materials)} '
      f'imgs={len([i for i in bpy.data.images if i.name != "Render Result"])}')
