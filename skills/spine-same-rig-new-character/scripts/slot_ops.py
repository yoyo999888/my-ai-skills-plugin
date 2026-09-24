#!/usr/bin/env python3
"""Spine JSON (3.x) 的 slot 操作: 新增 slot、移动附件、复制/改写显示时间线, 且不破坏原有绘制顺序。

原则: 骨骼、IK、骨骼时间线、原 slot 的定义和时间线一律不动; 修穿帮只靠新增 slot。

drawOrder 关键帧只存偏移, 没列出的 slot 按原顺序补进剩余位置 (Spine 读取规则)。
本模块先按规则还原每个关键帧的完整顺序, 插入新 slot 后, 为全部 slot 重新写出偏移 (按 slot 序号升序, 读取器要求)。

库用法:
    from slot_ops import insert_slot, hide_window, check_relative_order
    # 前层裙: 插在腿组中最靠上的那个之后, 附件与时间线从原 slot 移过来 (原 slot 留空)
    insert_slot(skel, {'name': 'skirt_front', 'bone': 'bone60'}, anchor=LEG_SLOTS, where='after',
                move_attachments_from='skirt', copy_timelines_from='skirt')
    # 鬓发移到脸的下一层
    insert_slot(skel, {'name': 'lock_b', 'bone': 'bone6'}, anchor='head', where='before',
                move_attachments_from='lock', copy_timelines_from='lock')
    # 新部件 (如侧面脖子): 显示时间线复制侧面头部 slot, 附件名映射成自己的
    insert_slot(skel, {'name': 'neck_s', 'bone': 'bone106'}, anchor='side_torso', where='before',
                copy_timelines_from='side_head', attachment_map={'side_head': 'neck_s'})
    # 某动作某时间段内不显示
    hide_window(skel, 'lock_b', 'attack4', 0.5333, 0.7667, restore='lock')

命令行自检: python3 slot_ops.py check <原骨架.json> <新骨架.json>
    静态核对每个动作每个 drawOrder 关键帧里原 slot 的相对顺序、原 slot 时间线、骨骼与 IK 是否未变。
    (静态核对不能代替渲染核对: 仍需在全部采样姿势里读运行库的实际绘制顺序。)
"""
import copy, json, sys


def full_order(key, names):
    """drawOrder 关键帧 -> 完整绘制顺序 (slot 名列表)。无 offsets 的关键帧 = 初始顺序。"""
    if 'offsets' not in key:
        return list(names)
    n = len(names); idx = {s: i for i, s in enumerate(names)}
    draw = [None] * n; unchanged = []; oi = 0
    for o in key['offsets']:
        si = idx[o['slot']]
        while oi != si:
            unchanged.append(oi); oi += 1
        draw[oi + o['offset']] = oi; oi += 1
    while oi < n:
        unchanged.append(oi); oi += 1
    ui = 0
    for i in range(n):
        if draw[i] is None:
            draw[i] = unchanged[ui]; ui += 1
    return [names[i] for i in draw]


def offsets_for(order, names):
    """完整顺序 -> 全部 slot 的偏移 (按 slot 序号升序, 保证任意顺序都能精确还原)。"""
    pos = {s: i for i, s in enumerate(order)}
    return [{'slot': s, 'offset': pos[s] - i} for i, s in enumerate(names)]


def _insert_at(order, new, anchor, where):
    anchors = [anchor] if isinstance(anchor, str) else list(anchor)
    ids = [order.index(a) for a in anchors]
    at = max(ids) + 1 if where == 'after' else min(ids)
    return order[:at] + [new] + order[at:]


def insert_slot(skel, slot_def, anchor, where='after', move_attachments_from=None,
                copy_timelines_from=None, attachment_map=None):
    """新增 slot, 放在 anchor (slot 名或名单) 的后面 ('after': 名单中最靠上的之后) 或前面 ('before': 名单中最靠下的之前)。
    同一规则用于初始顺序和每个 drawOrder 关键帧, 原 slot 之间的相对顺序保持不变。
    move_attachments_from: 把该 slot 在所有皮肤中的附件移到新 slot (原 slot 留空, 原定义与时间线不动)。
    copy_timelines_from: 复制该 slot 在每个动作里的显示时间线 (attachment/color)。
    attachment_map: 复制时改写附件名 {旧名: 新名}; 未列出的名字保持原样。"""
    d = {'attachment': None, 'color': 'ffffffff', 'blend': 'normal'}
    if copy_timelines_from or move_attachments_from:
        src = next(s for s in skel['slots'] if s['name'] == (move_attachments_from or copy_timelines_from))
        d = {k: v for k, v in src.items() if k not in ('name', 'bone')}
        if attachment_map and d.get('attachment') in attachment_map:
            d['attachment'] = attachment_map[d['attachment']]
    d.update(slot_def)
    new = d['name']
    old_names = [s['name'] for s in skel['slots']]
    if new in old_names:
        raise ValueError(f'slot {new} already exists')
    new_order = _insert_at(old_names, new, anchor, where)
    by = {s['name']: s for s in skel['slots']}; by[new] = d
    skel['slots'] = [by[s] for s in new_order]
    if move_attachments_from:
        skins = skel['skins']
        for sk in (skins.values() if isinstance(skins, dict) else [s['attachments'] for s in skins]):
            if move_attachments_from in sk:
                sk[new] = sk.pop(move_attachments_from)
    for name, anim in skel.get('animations', {}).items():
        st = anim.get('slots', {})
        if copy_timelines_from and copy_timelines_from in st:
            tl = copy.deepcopy(st[copy_timelines_from])
            if attachment_map and 'attachment' in tl:
                for f in tl['attachment']:
                    if f.get('name') in attachment_map:
                        f['name'] = attachment_map[f['name']]
            st[new] = tl
            anim['slots'] = st
        for key in anim.get('drawOrder', []) or anim.get('draworder', []):
            if 'offsets' not in key:
                continue
            order = full_order(key, old_names)
            key['offsets'] = offsets_for(_insert_at(order, new, anchor, where), new_order)
    return skel


def hide_window(skel, slot, anim, t0, t1, restore):
    """在动作 anim 的 [t0, t1] 内让 slot 不显示, t1 时恢复为附件 restore; 删除窗口内原有的附件关键帧。"""
    st = skel['animations'][anim].setdefault('slots', {}).setdefault(slot, {})
    keys = [f for f in st.get('attachment', []) if not (t0 <= f['time'] <= t1)]
    keys += [{'time': t0, 'name': None}, {'time': t1, 'name': restore}]
    st['attachment'] = sorted(keys, key=lambda f: f['time'])
    return skel


def check_relative_order(orig, new):
    """静态核对: 原 slot 在每个 drawOrder 关键帧中的相对顺序、原 slot 定义与时间线、骨骼/IK/骨骼时间线。"""
    on = [s['name'] for s in orig['slots']]; nn = [s['name'] for s in new['slots']]
    added = [s for s in nn if s not in on]
    report = {'added_slots': added, 'problems': []}
    if orig.get('bones') != new.get('bones'): report['problems'].append('bones differ')
    if orig.get('ik') != new.get('ik'): report['problems'].append('ik differ')
    if [s for s in new['slots'] if s['name'] not in added] != orig['slots']: report['problems'].append('original slot definitions differ')
    if [s for s in nn if s not in added] != on: report['problems'].append('setup order of original slots differs')
    for name, a in orig.get('animations', {}).items():
        b = new['animations'].get(name)
        if b is None: report['problems'].append(f'{name}: missing'); continue
        if a.get('bones') != b.get('bones'): report['problems'].append(f'{name}: bone timelines differ')
        if {k: v for k, v in b.get('slots', {}).items() if k not in added} != a.get('slots', {}):
            report['problems'].append(f'{name}: original slot timelines differ')
        ka, kb = a.get('drawOrder', []), b.get('drawOrder', [])
        if len(ka) != len(kb): report['problems'].append(f'{name}: drawOrder key count differs'); continue
        for x, y in zip(ka, kb):
            if [s for s in full_order(y, nn) if s not in added] != full_order(x, on):
                report['problems'].append(f"{name}@{x['time']}: relative order changed")
    return report


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == 'check':
        r = check_relative_order(json.load(open(sys.argv[2])), json.load(open(sys.argv[3])))
        print(json.dumps(r, ensure_ascii=False, indent=1))
        sys.exit(1 if r['problems'] else 0)
    print(__doc__); sys.exit(2)
