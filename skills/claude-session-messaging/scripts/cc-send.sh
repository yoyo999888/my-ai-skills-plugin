#!/usr/bin/env bash
# 给本机指定 Claude Code 会话注入一条消息（走 claude 自带的 UDS 会话通讯协议）。
#
# 用法:
#   cc-send.sh list                        列出本机在线会话（名字 / pid / 状态 / cwd）
#   cc-send.sh <会话名|pid> [--now] <消息>  发消息；--now 打断对方当前轮次立即处理，默认排队
#
# 依赖: python3。收方会话 ~/.claude/settings.json 需 "crossSessionInbound": "accept"。
set -euo pipefail
REG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/sessions"

usage() { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }
[[ $# -ge 1 ]] || usage

if [[ "$1" == "list" ]]; then
  python3 - "$REG" <<'PY'
import json,sys,glob,os
reg=sys.argv[1]; rows=[]
for f in glob.glob(os.path.join(reg,'*.json')):
    try: d=json.load(open(f))
    except Exception: continue
    if os.path.exists(d.get('messagingSocketPath','')):
        rows.append((d.get('name','?'),d['pid'],d.get('status','?'),d.get('cwd','')))
if not rows: print("没有在线会话"); sys.exit(0)
w=max(len(r[0]) for r in rows)
for n,p,s,c in sorted(rows): print(f"{n:<{w}}  pid={p:<6} {s:<5} {c}")
PY
  exit 0
fi

target="$1"; shift
priority="queue"
if [[ "${1:-}" == "--now" ]]; then priority="now"; shift; fi
msg="${*:?缺少消息文本}"

if [[ "$target" =~ ^[0-9]+$ ]]; then pid="$target"; else
  pid=$(python3 - "$REG" "$target" <<'PY'
import json,sys,glob,os
reg,name=sys.argv[1],sys.argv[2]; hits=[]
for f in glob.glob(os.path.join(reg,'*.json')):
    try: d=json.load(open(f))
    except Exception: continue
    if d.get('name')==name and os.path.exists(d.get('messagingSocketPath','')): hits.append(d)
if not hits: sys.exit(f"找不到名为 {name!r} 的在线会话（用 `cc-send.sh list` 查看）")
if len(hits)>1: sys.exit(f"同名会话有 {len(hits)} 个, 请改用 pid: "+", ".join(str(h['pid']) for h in hits))
print(hits[0]['pid'])
PY
  )
fi

[[ -f "$REG/$pid.json" ]] || { echo "会话 pid=$pid 未登记（$REG/$pid.json 不存在）" >&2; exit 1; }
python3 - "$REG" "$pid" "$priority" "$msg" <<'PY'
import json,sys,glob,socket
reg,pid,priority,msg=sys.argv[1:5]
sock=json.load(open(f"{reg}/{pid}.json"))['messagingSocketPath']
keys=glob.glob(f"{reg}/{pid}.*.key")
if not keys: sys.exit(f"找不到 {reg}/{pid}.*.key（对方会话没发布 peerToken）")
token=json.load(open(keys[0]))['peerToken']
frame={"type":"user","message":{"role":"user","content":msg}}
if priority=="now": frame["priority"]="now"
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.settimeout(5)
try: s.connect(sock)
except OSError as e: sys.exit(f"连不上 {sock}: {e}（会话可能已退出）")
s.sendall((json.dumps({"type":"auth","token":token})+"\n"+json.dumps(frame,ensure_ascii=False)+"\n").encode())
s.shutdown(socket.SHUT_WR); s.close()
print(f"已发送 -> pid={pid} priority={priority} sock={sock}")
PY
