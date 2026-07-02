#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用整场景基线 glb 验证 manifest 的 Unity 世界矩阵 + 确定 Unity→glTF 共轭。

原理:基线 glb(glTFast 整场景导出)的 node 树带完整名字层级,按 path 与 manifest
的实例对齐;对候选共轭 C 检验 M_gltf ≈ C @ M_unity @ C⁻¹。全体实例通过 = 公式实证。

用法: python3 verify_manifest_vs_glb.py <manifest.json> <baseline.glb>
"""
import json, struct, sys
import numpy as np

def read_glb_json(path):
    with open(path, 'rb') as f:
        magic, ver, _total = struct.unpack('<III', f.read(12))
        assert magic == 0x46546C67, 'not a glb'
        clen, ctype = struct.unpack('<II', f.read(8))
        assert ctype == 0x4E4F534A, 'first chunk not JSON'
        return json.loads(f.read(clen))

def node_local(n):
    if 'matrix' in n:
        return np.array(n['matrix'], dtype=np.float64).reshape(4, 4).T  # glTF 列主序
    M = np.eye(4)
    if 'rotation' in n:
        x, y, z, w = n['rotation']
        M[:3, :3] = np.array([
            [1-2*(y*y+z*z), 2*(x*y-z*w),   2*(x*z+y*w)],
            [2*(x*y+z*w),   1-2*(x*x+z*z), 2*(y*z-x*w)],
            [2*(x*z-y*w),   2*(y*z+x*w),   1-2*(x*x+y*y)]])
    if 'scale' in n:
        M[:3, :3] = M[:3, :3] @ np.diag(n['scale'])
    if 'translation' in n:
        M[:3, 3] = n['translation']
    return M

def walk_world(gltf):
    """返回 path → (world_matrix, count)。同 path 多次出现记 count,验证只用唯一 path。"""
    nodes = gltf['nodes']
    out = {}
    def rec(idx, parentM, parentPath):
        n = nodes[idx]
        name = n.get('name', f'node{idx}')
        path = parentPath + '/' + name if parentPath else name
        M = parentM @ node_local(n)
        if path in out:
            out[path] = (out[path][0], out[path][1] + 1)
        else:
            out[path] = (M, 1)
        for c in n.get('children', []):
            rec(c, M, path)
    scene = gltf['scenes'][gltf.get('scene', 0)]
    for r in scene['nodes']:
        rec(r, np.eye(4), '')
    return out

def main():
    manifest_path, glb_path = sys.argv[1], sys.argv[2]
    man = json.load(open(manifest_path))
    gltf = read_glb_json(glb_path)
    world = walk_world(gltf)
    uniq = {p: M for p, (M, c) in world.items() if c == 1}
    print(f'glb nodes: {len(gltf["nodes"])}, 唯一 path: {len(uniq)}')

    candidates = {
        'flipX': np.diag([-1.0, 1, 1, 1]),
        'flipZ': np.diag([1.0, 1, -1, 1]),
        'identity': np.eye(4),
    }
    insts = man['instances']
    matched = []
    for inst in insts:
        p = inst['path']
        if p in uniq:
            Mu = np.array(inst['matrix'], dtype=np.float64).reshape(4, 4)  # 行主序
            matched.append((p, Mu, uniq[p]))
    print(f'manifest 实例: {len(insts)}, 与 glb 唯一 path 对齐: {len(matched)}')
    if not matched:
        print('FAIL: 无可对齐实例(检查 path 约定)'); sys.exit(1)

    for name, C in candidates.items():
        Ci = np.linalg.inv(C)
        errs = []
        for _, Mu, Mg in matched:
            pred = C @ Mu @ Ci
            scale = max(1.0, np.abs(Mg[:3, 3]).max())
            errs.append(np.abs(pred - Mg).max() / scale)
        errs = np.array(errs)
        print(f'候选 {name:9s}: 相对误差 max={errs.max():.2e} mean={errs.mean():.2e} '
              f'超1e-4比例={float((errs > 1e-4).mean()):.4f}')

if __name__ == '__main__':
    main()
