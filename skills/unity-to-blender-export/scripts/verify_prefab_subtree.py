#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证:基线场景 glb 里 prefab 实例的内部子树 ≈ prefab glb 内部链 × manifest 实例矩阵。

对每个实例:W_baseline(实例路径/内部路径) ≟ (C M_u C⁻¹) @ L_prefabglb(内部路径)。
同时比对内部节点【名字集合】(层级+命名保真)。

用法: python3 verify_prefab_subtree.py <manifest.json> <baseline.glb> <prefab_glb_root> <smoke_list.txt>
"""
import json, sys, os
import numpy as np
from verify_manifest_vs_glb import read_glb_json, node_local

C = np.diag([-1.0, 1, 1, 1])

def walk(gltf):
    nodes = gltf['nodes']
    out = {}
    def rec(idx, M, pp):
        n = nodes[idx]
        path = (pp + '/' + n.get('name', f'node{idx}')) if pp else n.get('name', f'node{idx}')
        M2 = M @ node_local(n)
        out.setdefault(path, []).append(M2)
        for c in n.get('children', []):
            rec(c, M2, path)
    for r in gltf['scenes'][gltf.get('scene', 0)]['nodes']:
        rec(r, np.eye(4), '')
    return out

man_p, base_p, root, list_p = sys.argv[1:5]
man = json.load(open(man_p))
base = walk(read_glb_json(base_p))
base_uniq = {p: m[0] for p, m in base.items() if len(m) == 1}
prefabs = [l.strip() for l in open(list_p) if l.strip()]

total_nodes = bad_nodes = name_mismatch = insts_checked = 0
for ap in prefabs:
    rel = os.path.splitext(ap[7:] if ap.startswith('Assets/') else ap)[0] + '.glb'
    pg = walk(read_glb_json(os.path.join(root, rel)))
    stem = os.path.splitext(os.path.basename(rel))[0]
    # prefab glb 的根就是 prefab 名节点;内部路径去掉根前缀
    inner = {p[len(stem):].lstrip('/'): m[0] for p, m in pg.items() if len(m) == 1 and p.startswith(stem)}
    insts = [i for i in man['instances'] if i['prefab'] == ap][:20]
    for inst in insts:
        Mu = np.array(inst['matrix']).reshape(4, 4)
        E = C @ Mu @ C
        hit = False
        for ip, L in inner.items():
            bp = inst['path'] + ('/' + ip if ip else '')
            if bp not in base_uniq: continue
            hit = True
            pred = E @ L
            got = base_uniq[bp]
            scale = max(1.0, np.abs(got[:3, 3]).max())
            total_nodes += 1
            if np.abs(pred - got).max() / scale > 1e-4:
                bad_nodes += 1
                if bad_nodes <= 5:
                    print(f'BAD {bp}\n pred_t={pred[:3,3]} got_t={got[:3,3]}')
        if hit: insts_checked += 1
        else: name_mismatch += 1
    print(f'{stem}: 实例查验 {len(insts)}, 内部节点 {len(inner)}')

print(f'\nRESULT insts_checked={insts_checked} 路径未对齐实例={name_mismatch} '
      f'节点比对={total_nodes} 超差={bad_nodes} ({(bad_nodes/max(1,total_nodes)):.2%})')
