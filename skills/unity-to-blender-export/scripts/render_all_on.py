#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""点亮场景里全部 unity_active=False 的隐藏实例后渲染(不保存 .blend)。
用法: blender -b <scene.blend> --python render_all_on.py -- <out.png> [方位角]
"""
import bpy, sys, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[0]
AZI = math.radians(float(argv[1]) if len(argv) > 1 else 45.0)

n = 0
for o in bpy.data.objects:
    ua = o.get('unity_active')
    if ua is not None and not ua:
        o.hide_viewport = o.hide_render = False
        n += 1
print(f'UNHIDDEN {n}', flush=True)

SKIP = ('SkyDome', 'Cloud')
for o in bpy.data.objects:
    if any(s in o.name for s in SKIP):
        o.hide_render = o.hide_viewport = True

dg = bpy.context.evaluated_depsgraph_get()
lo = Vector((1e18,) * 3); hi = Vector((-1e18,) * 3)
cnt = 0
for inst in dg.object_instances:
    ob = inst.object
    if ob.type != 'MESH': continue
    nm = ob.name + (inst.parent.name if inst.is_instance and inst.parent else '')
    if any(s in nm for s in SKIP): continue
    M = inst.matrix_world
    for c in ob.bound_box:
        w = M @ Vector(c)
        lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
    cnt += 1
center = (lo + hi) / 2
diag = (hi - lo).length or 10
print(f'SNAP meshes={cnt} bbox={tuple(round(v,1) for v in lo)}..{tuple(round(v,1) for v in hi)}', flush=True)

cam_data = bpy.data.cameras.new('snapcam'); cam_data.clip_end = diag * 10
cam = bpy.data.objects.new('snapcam', cam_data)
bpy.context.scene.collection.objects.link(cam)
d = Vector((math.cos(AZI), math.sin(AZI), 0.55)).normalized()
cam.location = center + d * diag * 0.75
cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam
sun_data = bpy.data.lights.new('sun', 'SUN'); sun_data.energy = 3
sun = bpy.data.objects.new('sun', sun_data)
bpy.context.scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(50), 0, math.radians(120))
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print(f'SNAP_OK -> {OUT}')
