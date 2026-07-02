#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从三份 manifest 汇总:全部用到的 prefab 清单 + guid 映射 + override/loose 概况。
用法: python3 gen_prefab_list.py <manifests_dir> <out_list.txt> <out_guidmap.json>
"""
import json, sys, os, glob, collections

mdir, out_list, out_guid = sys.argv[1], sys.argv[2], sys.argv[3]
prefabs = {}
stats = collections.Counter()
for mp in sorted(glob.glob(os.path.join(mdir, '*.manifest.json'))):
    man = json.load(open(mp))
    name = os.path.basename(mp).replace('.manifest.json', '')
    per = collections.Counter()
    for i in man['instances']:
        prefabs[i['prefab']] = i['guid']
        per['instances'] += 1
        if i.get('mods'): per['overridden'] += 1
        if not i['active']: per['inactive'] += 1
    per['loose'] = len(man.get('loose', []))
    per['unique_prefabs'] = len({i['prefab'] for i in man['instances']})
    print(f"{name}: instances={per['instances']} unique_prefabs={per['unique_prefabs']} "
          f"overridden={per['overridden']} inactive={per['inactive']} loose={per['loose']}")
    stats.update(per)

with open(out_list, 'w') as f:
    f.write('\n'.join(sorted(prefabs)) + '\n')
json.dump(prefabs, open(out_guid, 'w'), indent=0)
print(f"TOTAL unique_prefabs={len(prefabs)} instances={stats['instances']} "
      f"overridden={stats['overridden']} loose={stats['loose']} -> {out_list}")
