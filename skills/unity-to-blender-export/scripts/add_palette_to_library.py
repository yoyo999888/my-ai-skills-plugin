#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把材质调色板 glb 并入 prefab_library.blend。

只补【库里没有的】材质(按基名判重,已有的不动、更不改名——场景按名字链接,改名会断)。
新材质设 fake_user 持久化;调色板的 Quad/mesh/重复材质全部清掉;贴图按 stem 去重+外链磁盘。

用法: blender -b <library.blend> --python add_palette_to_library.py -- <palette.glb> <textures_dir>
"""
import bpy, sys, os, re

argv = sys.argv[sys.argv.index("--") + 1:]
PAL, TEXDIR = argv[0], argv[1]
BASE_RE = re.compile(r'\.\d{3}$')
base = lambda n: BASE_RE.sub('', n)

have = {}
for m in bpy.data.materials:
    have.setdefault(base(m.name), m)
imgs_have = {}
for i in bpy.data.images:
    if i.name == 'Render Result': continue
    bn = os.path.basename((i.filepath or '').replace('\\', '/')) or i.name
    imgs_have.setdefault(os.path.splitext(BASE_RE.sub('', bn))[0], i)

before_mats = set(m.as_pointer() for m in bpy.data.materials)
bpy.ops.import_scene.gltf(filepath=PAL)
pal_objs = list(bpy.context.selected_objects)

added = dup = 0
for m in list(bpy.data.materials):
    if m.as_pointer() in before_mats: continue
    b = base(m.name)
    if b in have:
        m.user_remap(have[b]); dup += 1
    else:
        if m.name != b: m.name = b  # 新材质给干净名
        m.use_fake_user = True
        have[b] = m
        added += 1

# 贴图:新 image 按 stem 并到已有,或外链磁盘源图
disk = {}
for fn in os.listdir(TEXDIR):
    st = os.path.splitext(fn)[0]
    if st not in disk or fn.lower().endswith('.png'): disk[st] = os.path.join(TEXDIR, fn)
tex_new = 0
for img in list(bpy.data.images):
    if img.name == 'Render Result': continue
    bn = os.path.basename((img.filepath or '').replace('\\', '/')) or img.name
    st = os.path.splitext(BASE_RE.sub('', bn))[0]
    if st in imgs_have and imgs_have[st] is not img:
        img.user_remap(imgs_have[st]); continue
    if st not in imgs_have:
        imgs_have[st] = img; tex_new += 1
        if st in disk:
            try:
                if img.packed_file: img.unpack(method='REMOVE')
                img.filepath = disk[st]; img.reload()
            except Exception as e: print('TEX_WARN', st, e)

# 清调色板载体与孤儿
for o in pal_objs:
    bpy.data.objects.remove(o)
for _ in range(3):
    dead = [m for m in bpy.data.meshes if m.users == 0] + \
           [m for m in bpy.data.materials if m.users == 0 and not m.use_fake_user] + \
           [i for i in bpy.data.images if i.users == 0 and i.name != 'Render Result']
    if not dead: break
    bpy.data.batch_remove(dead)

bpy.ops.wm.save_mainfile()
print(f'PALETTE_OK added={added} dup={dup} tex_new={tex_new} mats_total={len(bpy.data.materials)} imgs_total={len(bpy.data.images)}')
