#!/usr/bin/env python3
"""给新贴图重建网格附件, 并把原网格的蒙皮权重迁移过去 (Spine JSON 3.x 加权网格)。

思路: 在"绑定姿势"(任选一帧, 如待机第 0 帧) 下, 原网格把图像坐标分段仿射地映射到世界坐标。
新贴图 (画布可比原图大) 上铺规则网格; 每个新顶点在原网格里找包含它(或最近)的三角形,
按截断后的重心坐标混合三个原顶点的影响骨骼与局部坐标; 三角形外的点把"外推位置 - 截断位置"
的差转到各骨骼局部坐标里加上。最后校验: 绑定姿势下蒙皮结果应等于分段仿射外推位置 (误差 < 0.01)。

坐标: 图像坐标以原附件 orig 尺寸像素为单位, u 右 v 下; 世界坐标 x 右 y 上。

库用法:
    from mesh_rebind import mesh_image_points, bone_mats_from_info, rebind_mesh
    img = mesh_image_points(att, region)             # region: {'size':[w,h], 'orig':[W,H], 'offset':[ox,oy]}
    mats = bone_mats_from_info(info['bones'])         # render_spine.cjs 输出的 [[name, wx, wy, a, b, c, d], ...]
    new_att, err = rebind_mesh(att, img, bind_world, triangles, mats, bounds=(u0, v0, u1, v1),
                               alpha=new_tex[..., 3], path='part_name')
自检: python3 mesh_rebind.py selftest
"""
import sys
import numpy as np


def barycentric(P, S):
    v0 = S[1] - S[0]; v1 = S[2] - S[0]; v2 = P - S[0]
    d00 = v0 @ v0; d01 = v0 @ v1; d11 = v1 @ v1; d20 = v2 @ v0; d21 = v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-12:
        return np.full((len(P), 3), np.nan)
    l1 = (d11 * d20 - d01 * d21) / den; l2 = (d00 * d21 - d01 * d20) / den
    return np.stack([1 - l1 - l2, l1, l2], 1)


def locate(P, src, tris):
    """每个点所属(或最近)三角形: 返回 (三角形数组, 三角形序号, 原始重心坐标, 截断重心坐标)"""
    T = np.array(tris).reshape(-1, 3)
    bt = np.full(len(P), -1); bd = np.full(len(P), np.inf)
    bl = np.zeros((len(P), 3)); blc = np.zeros((len(P), 3))
    for ti, t in enumerate(T):
        L = barycentric(P, src[t])
        if np.isnan(L).any():
            continue
        outside = np.clip(-L, 0, None).sum(1)
        Lc = np.clip(L, 0, None); Lc /= np.maximum(Lc.sum(1, keepdims=True), 1e-9)
        dist = np.linalg.norm(P - Lc @ src[t], axis=1) + outside * 1e-6
        m = dist < bd
        bd[m] = dist[m]; bt[m] = ti; bl[m] = L[m]; blc[m] = Lc[m]
    return T, bt, bl, blc


def image_to_world(P, src, dst, tris):
    """图像坐标 -> 世界坐标 (三角形内插值, 外部按最近三角形仿射外推)"""
    T, bt, L, _ = locate(P, src, tris)
    W = np.zeros((len(P), 2))
    for ti in np.unique(bt):
        m = bt == ti
        W[m] = L[m] @ dst[T[ti]]
    return W


def parse_weighted(vertices, nverts):
    """JSON 加权顶点 [n, bone, x, y, w, ...] -> [[(bone, x, y, w), ...], ...]"""
    out, i = [], 0
    for _ in range(nverts):
        n = int(vertices[i]); i += 1; infl = []
        for _ in range(n):
            infl.append((int(vertices[i]), vertices[i + 1], vertices[i + 2], vertices[i + 3])); i += 4
        out.append(infl)
    return out


def to_json_vertices(infl):
    V = []
    for vi in infl:
        V.append(len(vi))
        for b, x, y, w in vi:
            V += [int(b), round(float(x), 4), round(float(y), 4), round(float(w), 5)]
    return V


def embed_weights(P, src, dst, tris, orig_infl, bone_mats, max_bones=8):
    T, bt, L, Lc = locate(P, src, tris)
    Wq = image_to_world(P, src, dst, tris)
    res = []
    for k in range(len(P)):
        t = T[bt[k]]; lam = Lc[k]; acc = {}
        for j in range(3):
            if lam[j] <= 0:
                continue
            for (b, x, y, w) in orig_infl[t[j]]:
                W_, Px, Py = acc.get(b, (0.0, 0.0, 0.0))
                acc[b] = (W_ + lam[j] * w, Px + lam[j] * w * x, Py + lam[j] * w * y)
        delta = Wq[k] - lam @ dst[t]
        infl = []
        for b, (W_, Px, Py) in acc.items():
            if W_ <= 1e-6:
                continue
            p = np.array([Px / W_, Py / W_]) + np.linalg.solve(bone_mats[b][0], delta)
            infl.append((b, float(p[0]), float(p[1]), float(W_)))
        infl.sort(key=lambda z: -z[3]); infl = infl[:max_bones]
        s = sum(z[3] for z in infl)
        res.append([(b, x, y, w / s) for b, x, y, w in infl])
    return res


def skin_world(infl, bone_mats):
    out = []
    for vi in infl:
        p = np.zeros(2)
        for b, x, y, w in vi:
            M, t = bone_mats[b]; p += w * (M @ np.array([x, y]) + t)
        out.append(p)
    return np.array(out)


def grid_mesh(alpha, u0, v0, u1, v1, nx, ny, thresh=0.02, dil=1):
    """在图像坐标矩形上铺 nx*ny 方格, 只保留覆盖不透明像素的格子 (外扩 dil 格), 对角线交替。
    返回 (顶点图像坐标 (N,2), 三角形列表, 归一化 UV (N,2))"""
    from scipy import ndimage
    h, w = alpha.shape
    xs = np.linspace(u0, u1, nx + 1); ys = np.linspace(v0, v1, ny + 1)
    keep = np.zeros((ny, nx), bool)
    for j in range(ny):
        for i in range(nx):
            a0, a1 = int(np.floor(j / ny * h)), int(np.ceil((j + 1) / ny * h))
            b0, b1 = int(np.floor(i / nx * w)), int(np.ceil((i + 1) / nx * w))
            keep[j, i] = a1 > a0 and b1 > b0 and alpha[a0:a1, b0:b1].max() > thresh
    if dil > 0:                                   # 注意: iterations=0 在 scipy 里是"膨胀到收敛"
        keep = ndimage.binary_dilation(keep, iterations=dil)
    idx = -np.ones((ny + 1, nx + 1), int); verts, tris = [], []
    for j in range(ny):
        for i in range(nx):
            if not keep[j, i]:
                continue
            for jj, ii in ((j, i), (j, i + 1), (j + 1, i), (j + 1, i + 1)):
                if idx[jj, ii] < 0:
                    idx[jj, ii] = len(verts); verts.append((xs[ii], ys[jj]))
            a, b, c, d = idx[j, i], idx[j, i + 1], idx[j + 1, i], idx[j + 1, i + 1]
            tris += [a, b, d, a, d, c] if (i + j) % 2 == 0 else [a, b, c, b, d, c]
    verts = np.array(verts, float)
    uvs = np.stack([(verts[:, 0] - u0) / (u1 - u0), (verts[:, 1] - v0) / (v1 - v0)], 1)
    return verts, tris, uvs


def mesh_image_points(att, region):
    """JSON 网格的 uvs 是相对打包矩形的归一化坐标 -> 原附件图像坐标。libgdx offset 以左下为原点。"""
    uv = np.array(att['uvs'], float).reshape(-1, 2)
    pw, ph = region['size']; ow, oh = region.get('orig', region['size']); ox, oy = region.get('offset', (0, 0))
    return np.stack([ox + uv[:, 0] * pw, (oh - oy - ph) + uv[:, 1] * ph], 1)


def bone_mats_from_info(bones):
    return {i: (np.array([[b[3], b[4]], [b[5], b[6]]], float), np.array([b[1], b[2]], float)) for i, b in enumerate(bones)}


def rebind_mesh(att, img_pts, bind_world, triangles, bone_mats, bounds, alpha, path, cell=3.5, max_bones=8):
    """返回 (新的 JSON 网格附件, 绑定姿势误差)。bounds = 新贴图在原图像坐标中的范围 (u0, v0, u1, v1)。"""
    u0, v0, u1, v1 = bounds
    nx = max(2, int(round((u1 - u0) / cell))); ny = max(2, int(round((v1 - v0) / cell)))
    verts, tris, uvs = grid_mesh(alpha, u0, v0, u1, v1, nx, ny)
    src = np.asarray(img_pts, float); dst = np.asarray(bind_world, float)
    infl = embed_weights(verts, src, dst, triangles, parse_weighted(att['vertices'], len(src)), bone_mats, max_bones)
    err = float(np.abs(skin_world(infl, bone_mats) - image_to_world(verts, src, dst, triangles)).max())
    new = {'type': 'mesh', 'path': path, 'uvs': [round(float(x), 6) for x in uvs.ravel()], 'triangles': [int(t) for t in tris],
           'vertices': to_json_vertices(infl), 'hull': 0, 'width': round(u1 - u0, 3), 'height': round(v1 - v0, 3)}
    return new, err


def _selftest():
    """两根骨骼、4 个顶点的小网格; 新贴图画布比原图大一圈, 迁移后误差应 < 1e-6。"""
    rot = lambda a: np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    mats = {0: (rot(0.3) * 1.2, np.array([5.0, 7.0])), 1: (rot(-0.8), np.array([12.0, 3.0]))}
    img = np.array([[0, 0], [10, 0], [10, 20], [0, 20]], float)
    world_of = lambda p: np.array([p[0] * 0.8 + 3, -p[1] * 0.8 + 40])        # 绑定姿势下图像->世界
    infl = []
    for p in img:
        w0 = 1 - p[1] / 20; wp = world_of(p); vi = []
        for b, w in ((0, w0), (1, 1 - w0)):
            if w > 0:
                M, t = mats[b]; loc = np.linalg.solve(M, wp - t); vi.append((b, loc[0], loc[1], w))
        infl.append(vi)
    att = {'type': 'mesh', 'uvs': [0, 0, 1, 0, 1, 1, 0, 1], 'triangles': [0, 1, 2, 0, 2, 3], 'vertices': to_json_vertices(infl)}
    bind = np.array([world_of(p) for p in img])
    alpha = np.ones((40, 24))
    new, err = rebind_mesh(att, img, bind, att['triangles'], mats, (-2, -2, 12, 22), alpha, 'test', cell=2.0)
    print('selftest verts', len(new['uvs']) // 2, 'bind error', err)
    assert err < 1e-3, err
    print('ok')


if __name__ == '__main__':
    if sys.argv[1:] == ['selftest']:
        _selftest()
    else:
        print(__doc__)
