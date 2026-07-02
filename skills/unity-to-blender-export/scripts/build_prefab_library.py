#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prefab glb 批量导入 → 一个 prefab_library.blend。

每个 prefab 一个 collection(名 = prefab 文件名,内部 GameObject 树原样保留);
mesh data / material / image 按名字去重共享(改一处 → 所有引用 prefab 联动);
贴图外链到 textures/(磁盘一份,不打包)。custom props 存 unity_path/guid 双轨保真。

用法: blender -b -P build_prefab_library.py -- <glb_root> <prefab_list.txt> <guid_map.json> <out.blend> <textures_dir>
产物: <out.blend> + <out>.map.json(unity_path → collection 实名,防截断/重名歧义)
"""
import bpy, sys, os, json, re, time
from mathutils import Matrix

argv = sys.argv[sys.argv.index("--") + 1:]
GLB_ROOT, LIST, GUIDMAP, OUT, TEXDIR = argv[0], argv[1], argv[2], argv[3], argv[4]

# u_path 消歧用:把 Blender 局部矩阵还原到 Unity 局部坐标(K = CONV @ C,与 build_scene 一致)
C = Matrix.Diagonal((-1, 1, 1, 1))
CONV = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
K = CONV @ C
KI = K.inverted()
def unity_local_pos(o):
    Lu = KI @ o.matrix_local @ K
    return (round(Lu[0][3], 3), round(Lu[1][3], 3), round(Lu[2][3], 3))

guid_of = json.load(open(GUIDMAP)) if os.path.exists(GUIDMAP) else {}
prefab_paths = [l.strip() for l in open(LIST) if l.strip() and not l.startswith('#')]

bpy.ops.wm.read_factory_settings(use_empty=True)
# 性能关键:prefab collection 一律【不挂进场景】(fake_user 持久化,libraries.load 照常可 link)。
# 挂场景会让每次 import 触发全量 depsgraph 更新 → 3238 个 glb 平方级恶化(实测 86min 才 1200 个)。

BASE_RE = re.compile(r'\.\d{3}$')
base = lambda n: BASE_RE.sub('', n)

# 贴图磁盘索引(stem → 源图路径,png 优先),增量去重直接对着它建 canonical
disk_by_stem = {}
for fn in os.listdir(TEXDIR):
    stem0 = os.path.splitext(fn)[0]
    if stem0 not in disk_by_stem or fn.lower().endswith('.png'):
        disk_by_stem[stem0] = os.path.join(TEXDIR, fn)

canon_mesh = {}   # (base名, 顶点数, v0粗坐标) → mesh data
canon_mat = {}    # base名 → material
canon_img = {}    # stem → image
known_imgs = set()  # 已处理 image 指针
col_map = {}      # unity_path → collection 实名
name_over63 = 0
t0 = time.time()
done = miss = 0

def dedup_images_incremental():
    for img in list(bpy.data.images):
        if img.as_pointer() in known_imgs or img.name == 'Render Result': continue
        bn = os.path.basename((img.filepath or '').replace('\\', '/')) or img.name
        stem0 = os.path.splitext(BASE_RE.sub('', bn))[0]
        got = canon_img.get(stem0)
        if got is not None and got is not img:
            img.user_remap(got)
        else:
            canon_img[stem0] = img
            known_imgs.add(img.as_pointer())

def purge_orphans():
    for _ in range(3):
        dead = [m for m in bpy.data.meshes if m.users == 0] + \
               [m for m in bpy.data.materials if m.users == 0] + \
               [i for i in bpy.data.images if i.users == 0 and i.name != 'Render Result']
        if not dead: break
        dead_ptrs = {d.as_pointer() for d in dead}
        known_imgs.difference_update(dead_ptrs)
        for k in [k for k, v in canon_img.items() if v.as_pointer() in dead_ptrs]:
            del canon_img[k]
        for k in [k for k, v in canon_mat.items() if v.as_pointer() in dead_ptrs]:
            del canon_mat[k]
        for k in [k for k, v in canon_mesh.items() if v.as_pointer() in dead_ptrs]:
            del canon_mesh[k]
        bpy.data.batch_remove(dead)

for ap in prefab_paths:
    rel = ap[7:] if ap.startswith('Assets/') else ap
    glb = os.path.join(GLB_ROOT, os.path.splitext(rel)[0] + '.glb')
    if not os.path.exists(glb):
        print(f'LIB_MISS_GLB {ap}'); miss += 1; continue
    stem = os.path.splitext(os.path.basename(rel))[0]
    if len(stem.encode()) > 63: name_over63 += 1

    before_sel = None
    bpy.ops.import_scene.gltf(filepath=glb)
    new_objs = list(bpy.context.selected_objects)
    if not new_objs:
        print(f'LIB_EMPTY {ap}'); miss += 1; continue

    col = bpy.data.collections.new(stem)
    col.use_fake_user = True  # 不挂场景,靠 fake_user 存盘
    col_map[ap] = col.name
    col['unity_path'] = ap
    if ap in guid_of: col['guid'] = guid_of[ap]

    new_set = set(o.as_pointer() for o in new_objs)
    kids = {}
    for o in new_objs:
        if o.parent is not None and o.parent.as_pointer() in new_set:
            kids.setdefault(o.parent, []).append(o)
    def seg(o):
        """同名兄弟按 Unity 局部坐标排序加 #k(与 GltfExporter.Seg 同一约定)。"""
        p = o.parent
        nm = base(o.name)
        if p is None or p.as_pointer() not in new_set: return nm
        same = [s for s in kids.get(p, []) if base(s.name) == nm]
        if len(same) == 1: return nm
        same.sort(key=unity_local_pos)
        return f'{nm}#{same.index(o)}'
    def relpath(o):
        segs = []
        cur = o
        while cur is not None and cur.parent is not None and cur.parent.as_pointer() in new_set:
            segs.append(seg(cur))
            cur = cur.parent
        return '/'.join(reversed(segs))
    inactive_paths = set()
    side = os.path.splitext(glb)[0] + '.inactive.json'
    if os.path.exists(side):
        inactive_paths = set(json.load(open(side)))
    for o in new_objs:
        for uc in list(o.users_collection):
            uc.objects.unlink(o)
        col.objects.link(o)
        if o.parent is None:
            o['unity_path'] = ap
            o['u_path'] = ''
        else:
            rp = relpath(o)
            o['u_path'] = rp
            if rp in inactive_paths:
                o['unity_active'] = False
            # 自身或任一祖先(prefab 内)被禁用 → 隐藏(Unity activeSelf 作用于整棵子树)
            segs = rp.split('/')
            if any('/'.join(segs[:k]) in inactive_paths for k in range(1, len(segs) + 1)):
                o.hide_viewport = o.hide_render = True
        # mesh data 去重
        if o.type == 'MESH' and o.data is not None:
            md = o.data
            v0 = md.vertices[0].co if len(md.vertices) else (0.0, 0.0, 0.0)
            key = (base(md.name), len(md.vertices), round(v0[0], 3), round(v0[1], 3), round(v0[2], 3))
            got = canon_mesh.get(key)
            if got is None:
                canon_mesh[key] = md
            elif got is not md:
                o.data = md = got
        # material 去重
        for slot in o.material_slots:
            if slot.material is None: continue
            b = base(slot.material.name)
            got = canon_mat.get(b)
            if got is None:
                canon_mat[b] = slot.material
            elif got is not slot.material:
                slot.material = got
    done += 1
    dedup_images_incremental()
    if done % 50 == 0:
        purge_orphans()
    if done % 200 == 0:
        print(f'LIB_PROGRESS {done}/{len(prefab_paths)} t={time.time()-t0:.0f}s '
              f'objs={len(bpy.data.objects)} meshes={len(bpy.data.meshes)} '
              f'mats={len(bpy.data.materials)} imgs={len(bpy.data.images)}', flush=True)

purge_orphans()

# 贴图:canonical 已按 stem 去重,重链到磁盘源图(glTFast 会把 png 重编码成 jpg + 内嵌图可能坏)
relinked = missing_tex = 0
for bn, img in canon_img.items():
    disk = disk_by_stem.get(bn)
    if disk and os.path.exists(disk):
        try:
            if img.packed_file: img.unpack(method='REMOVE')
            img.filepath = disk
            img.reload()
            relinked += 1
        except Exception as e:
            print('TEX_WARN', bn, e)
    else:
        missing_tex += 1
        print(f'TEX_NO_DISK {bn}(保留 glb 内嵌数据)')
        try:
            if not img.packed_file: img.pack()
        except Exception: pass
bpy.data.batch_remove([i for i in bpy.data.images if i.users == 0 and i.name != 'Render Result'])

os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT, relative_remap=True)
json.dump(col_map, open(OUT + '.map.json', 'w'), ensure_ascii=False, indent=0)

print(f'LIB_OK prefabs={done} miss={miss} objs={len(bpy.data.objects)} '
      f'meshes={len(bpy.data.meshes)} mats={len(bpy.data.materials)} '
      f'imgs={len(bpy.data.images)} tex_relinked={relinked} tex_no_disk={missing_tex} '
      f'name_over63={name_over63} t={time.time()-t0:.0f}s -> {OUT}')
