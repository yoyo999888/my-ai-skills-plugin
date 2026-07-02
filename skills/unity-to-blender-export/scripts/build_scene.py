#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""manifest + prefab 库 → 场景 .blend。

- 纯净实例(无 mods):collection-instance,零本地对象。
- 带 mods 实例:按 (prefab, mods签名) 去重生成「变体 collection」——从库 collection
  实体拷贝对象(mesh data 仍链接库里同一份),应用 transform/active/materials/removed
  修改;相同签名的实例共享同一变体。
- 分组 empty 树照搬 Unity 场景层级路径;实例名/unity 路径/guid/mods 存 custom props。
- <scene>_loose.glb(场景独有散件,世界坐标已烘焙)导入到 SceneOnly collection。

坐标:E_blender = K @ M_unity @ K⁻¹,K = CONV(glTF→Blender) @ C(Unity→glTF)。
C = flipX = diag(-1,1,1,1),由 verify_manifest_vs_glb.py 对基线 24,169 实例实证(误差 1e-7)。

用法: blender -b --python build_scene.py -- <manifest.json> <library.blend> <out.blend> [loose.glb] [--only-available]
"""
import bpy, sys, os, json, re, time
from mathutils import Matrix

argv = sys.argv[sys.argv.index("--") + 1:]
MANIFEST, LIB, OUT = argv[0], argv[1], argv[2]
LOOSE = argv[3] if len(argv) > 3 and not argv[3].startswith('--') else None
ONLY_AVAIL = '--only-available' in argv

C = Matrix.Diagonal((-1, 1, 1, 1))
CONV = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
K = CONV @ C
KI = K.inverted()
def conv(m16):
    Mu = Matrix([m16[0:4], m16[4:8], m16[8:12], m16[12:16]])
    return K @ Mu @ KI

BASE_RE = re.compile(r'\.\d{3}$')
base = lambda n: BASE_RE.sub('', n)

man = json.load(open(MANIFEST))
col_map = json.load(open(LIB + '.map.json'))

bpy.ops.wm.read_factory_settings(use_empty=True)
root = bpy.context.scene.collection

want_prefabs = {i['prefab'] for i in man['instances']}
# added mods 里挂的嵌套 prefab(如车内角色)也要 link
for i in man['instances']:
    for m in i.get('mods', []):
        if m['type'] == 'added' and m.get('prefab'):
            want_prefabs.add(m['prefab'])
need = sorted({p for p in want_prefabs if p in col_map})
absent = sorted({i['prefab'] for i in man['instances'] if i['prefab'] not in col_map})
if absent and not ONLY_AVAIL:
    print(f'SCENE_FAIL 缺 {len(absent)} 个 prefab,如 {absent[:5]}'); sys.exit(1)
with bpy.data.libraries.load(LIB, link=True) as (src, dst):
    dst.collections = [col_map[p] for p in need if col_map[p] in src.collections]
    dst.materials = list(src.materials)  # 全部材质(含调色板),供逐实例材质 override 按名查找
linked = {p: bpy.data.collections.get(col_map[p]) for p in need}
linked = {p: c for p, c in linked.items() if c is not None}
print(f'SCENE_LINKED {len(linked)}/{len(need)} (缺库 {len(absent)})')

groups = {}
def group_empty(path):
    if not path: return None
    if path in groups: return groups[path]
    head, _, name = path.rpartition('/')
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.1
    root.objects.link(e)
    e.parent = group_empty(head)
    groups[path] = e
    return e

# ---------- 变体 ----------
variants = {}          # (prefab, sig) → collection
warn = {'tpath_miss': 0, 'mat_miss': 0, 'added_skip': 0, 'removed_ambig': 0, 'unity_pathmap_miss': 0}

def subtree(objs_by_parent, o):
    out = [o]
    for c in objs_by_parent.get(o, []): out += subtree(objs_by_parent, c)
    return out

def make_variant(prefab, mods, vid):
    src_col = linked[prefab]
    vcol = bpy.data.collections.new(f'VAR_{vid:04d}_{src_col.name[:40]}')
    # 资产内默认禁用(hide)的堆叠备选子树不拷贝——不可见且是对象数大头;
    # 除非本变体有 active:true mod 涉及它(目标本身/其祖先/其后代)
    show_paths = [m['tpath'] for m in mods if m['type'] == 'active' and m.get('value')]
    def want(o):
        if not o.hide_viewport: return True
        up = o.get('u_path', '')
        return any(sp == up or sp.startswith(up + '/') or up.startswith(sp + '/')
                   for sp in show_paths)
    omap = {}
    for o in src_col.all_objects:
        if not want(o): continue
        n = o.copy()
        omap[o] = n
        vcol.objects.link(n)
    roots = []
    for o, n in omap.items():
        if o.parent in omap: n.parent = omap[o.parent]
        else: n.parent = None; roots.append(n)
    # 路径索引:库构建时已在每个对象存 u_path(资产侧消歧路径,copy() 会带过来)
    paths = {}
    for o, n in omap.items():
        paths.setdefault(n.get('u_path', ''), []).append(n)
    kids = {}
    for o, n in omap.items():
        if n.parent is not None: kids.setdefault(n.parent, []).append(n)
    for m in mods:
        tp = m.get('tpath', '')
        if tp.startswith('!'):  # Unity 侧 pathMap 查表失败的兜底路径,无法应用
            warn['unity_pathmap_miss'] += 1; continue
        tgt = paths.get(tp, [])
        if m['type'] == 'transform':
            if len(tgt) == 1: tgt[0].matrix_local = conv(m['matrix'])
            else: warn['tpath_miss'] += 1
        elif m['type'] == 'active':
            if len(tgt) == 1:
                show = bool(m['value'])
                if not show:
                    for d in subtree(kids, tgt[0]):
                        d.hide_viewport = d.hide_render = True
                else:
                    def unhide(o, is_target):
                        # 激活子树,但内部自身仍标记禁用的子件保持隐藏(Unity 语义)
                        if not is_target and o.get('unity_active') is not None and not o['unity_active']:
                            return
                        o.hide_viewport = o.hide_render = False
                        for c in kids.get(o, []): unhide(c, False)
                    unhide(tgt[0], True)
                tgt[0]['unity_active'] = show
            else: warn['tpath_miss'] += 1
        elif m['type'] == 'materials':
            if len(tgt) == 1:
                o = tgt[0]
                names = m['value']
                for i, slot in enumerate(o.material_slots):
                    if i < len(names):
                        mat = bpy.data.materials.get(names[i])
                        if mat is None: warn['mat_miss'] += 1; continue
                        slot.link = 'OBJECT'; slot.material = mat
            else: warn['tpath_miss'] += 1
        elif m['type'] == 'added':
            # tpath = 父节点资产路径('' = 根);prefab 有值 → 挂子 collection instance
            parent_tgt = paths.get(tp, [])
            acol = linked.get(m.get('prefab', ''))
            if acol is not None and len(parent_tgt) == 1:
                ae = bpy.data.objects.new(m.get('name', 'added'), None)
                ae.instance_type = 'COLLECTION'
                ae.instance_collection = acol
                vcol.objects.link(ae)
                ae.parent = parent_tgt[0]
                ae.matrix_local = conv(m['matrix'])
                ae['added_prefab'] = m['prefab']
            else:
                warn['added_skip'] += 1
        elif m['type'] == 'removed':
            cand = paths.get(m['tpath'], [])
            if len(cand) == 1:
                for d in subtree(kids, cand[0]):
                    for uc in list(d.users_collection): uc.objects.unlink(d)
            else: warn['removed_ambig'] += 1
    # 变体根对齐:根对象保持自身局部矩阵(库里已是根 TRS 归零后的内容)
    return vcol

# ---------- 实例 ----------
t0 = time.time()
n = hidden = skipped = pure = varused = 0
for inst in man['instances']:
    col = linked.get(inst['prefab'])
    if col is None: skipped += 1; continue
    mods = inst.get('mods', [])
    if mods:
        sig = (inst['prefab'], json.dumps(mods, sort_keys=True))
        if sig not in variants:
            variants[sig] = make_variant(inst['prefab'], mods, len(variants))
        col = variants[sig]; varused += 1
    else:
        pure += 1
    e = bpy.data.objects.new(inst['name'], None)
    e.instance_type = 'COLLECTION'
    e.instance_collection = col
    root.objects.link(e)
    e.parent = group_empty(inst['path'].rpartition('/')[0])
    e.matrix_world = conv(inst['matrix'])
    e['unity_path'] = inst['path']; e['prefab'] = inst['prefab']; e['guid'] = inst.get('guid', '')
    if mods: e['mods'] = json.dumps(mods, ensure_ascii=False)
    if not inst.get('active', True):
        e.hide_viewport = e.hide_render = True
        e['unity_active'] = False
        hidden += 1
    n += 1
    if n % 10000 == 0: print(f'SCENE_PROGRESS {n} t={time.time()-t0:.0f}s', flush=True)

# ---------- 场景独有散件 ----------
loose_n = 0
if LOOSE and os.path.exists(LOOSE):
    so = bpy.data.collections.new('SceneOnly')
    root.children.link(so)
    bpy.ops.import_scene.gltf(filepath=LOOSE)
    for o in bpy.context.selected_objects:
        for uc in list(o.users_collection):
            if uc is not so: uc.objects.unlink(o)
        so.objects.link(o)
        loose_n += 1

os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT, relative_remap=True)
print(f'SCENE_OK instances={n}(纯净 {pure} / 变体实例 {varused},变体 {len(variants)}) '
      f'hidden={hidden} skipped={skipped} groups={len(groups)} loose_objs={loose_n} '
      f'warn={warn} t={time.time()-t0:.0f}s -> {OUT}')
