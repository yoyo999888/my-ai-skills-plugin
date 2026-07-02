#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染快照:.blend 或 .glb 用同一机位规则出图,便于并排对比。
用法: blender -b --python render_snapshot.py -- <in.blend|in.glb> <out.png> [方位角度数,默认45]
机位由场景 bbox 决定(经 depsgraph 展开 collection instance),两边可比。
"""
import bpy, sys, os, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = argv[0], argv[1]
AZI = math.radians(float(argv[2]) if len(argv) > 2 else 45.0)

if SRC.endswith('.blend'):
    bpy.ops.wm.open_mainfile(filepath=SRC)
else:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=SRC)

SKIP = ('SkyDome', 'Cloud')  # 环境穹顶/云:不取景且不渲染(相机在穹外会被穹面全挡)
hidden = 0
for o in bpy.data.objects:
    if any(s in o.name for s in SKIP):
        o.hide_render = o.hide_viewport = True
        hidden += 1
print(f'SNAP hide_env={hidden}')

TIGHT = '--tight' in argv  # 按实例位置 5-95 分位取景(甩掉远处离群小件)
pts = []

dg = bpy.context.evaluated_depsgraph_get()
lo = Vector((1e18,) * 3); hi = Vector((-1e18,) * 3)
n = 0
for inst in dg.object_instances:
    ob = inst.object
    if ob.type != 'MESH': continue
    nm = ob.name + (inst.parent.name if inst.is_instance and inst.parent else '')
    if any(s in nm for s in SKIP): continue
    M = inst.matrix_world
    for c in ob.bound_box:
        w = M @ Vector(c)
        lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
    if TIGHT: pts.append(M.translation.copy())
    n += 1
if TIGHT and len(pts) > 100:
    xs = sorted(p.x for p in pts); ys = sorted(p.y for p in pts); zs = sorted(p.z for p in pts)
    a, b = int(len(pts) * 0.05), int(len(pts) * 0.95)
    lo = Vector((xs[a], ys[a], zs[a])); hi = Vector((xs[b], ys[b], zs[b]))
center = (lo + hi) / 2
diag = (hi - lo).length or 10
print(f'SNAP meshes={n} bbox={tuple(round(v,1) for v in lo)}..{tuple(round(v,1) for v in hi)}')

cam_data = bpy.data.cameras.new('snapcam')
cam_data.clip_end = diag * 10
cam = bpy.data.objects.new('snapcam', cam_data)
bpy.context.scene.collection.objects.link(cam)
direction = Vector((math.cos(AZI), math.sin(AZI), 0.55)).normalized()
cam.location = center + direction * diag * 0.75
look = center - cam.location
cam.rotation_euler = look.to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam

sun_data = bpy.data.lights.new('sun', 'SUN')
sun_data.energy = 3
sun = bpy.data.objects.new('sun', sun_data)
bpy.context.scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(50), 0, math.radians(120))

sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE_NEXT' if hasattr(bpy.types, 'RenderEngine') and 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
sc.render.filepath = OUT
sc.world = sc.world or bpy.data.worlds.new('w')
sc.world.use_nodes = True
bg = sc.world.node_tree.nodes.get('Background')
if bg: bg.inputs[0].default_value = (0.7, 0.8, 0.95, 1)
bpy.ops.render.render(write_still=True)
print(f'SNAP_OK -> {OUT}')
