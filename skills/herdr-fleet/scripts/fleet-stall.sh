#!/bin/bash
# fleet-stall.sh — 用 pane 日志「是否增长」判断 herdr worker 是否停滞，不追问 worker。
#
# 用法：
#   FLEET_HOSTS="unity:d7 hufan:d1 ly:d3 no3:d5" \
#   FLEET_AGENT_SUFFIX="-dev1" \
#   FLEET_PUSH_LOG=/tmp/dmf-hub-sync.log \
#   fleet-stall.sh
#
# FLEET_HOSTS  每项 host:domain-prefix（多前缀用 | 分隔，如 duanxin:d4|d2）；domain-prefix 用于在
#              推送日志里匹配 refs/heads/<prefix>-* 取"最近推送时间"，可为空。
# FLEET_AGENT_SUFFIX  worker 名后缀（默认 -dev1）。
# FLEET_PUSH_LOG  git-serve post-receive 日志（行含 "hubpush <日期> <时间> refs/heads/<branch>"），可选。
# FLEET_STATE_DIR  快照目录（默认 ${TMPDIR:-/tmp}/herdr-fleet-stall）。
#
# 原理：每次调用抓每台 worker pane 全文算 md5 与上次快照比：变了 → changed（在干活，别打扰）；
# 不变 → STILL Nm（累计静止分钟）。另附：pane 尾 30 行的空等模式命中数（sleep N / not yet / MERGED）、
# 尾 40 行的租约/429 标志、最近推送时间。判定建议：STILL ≥ 两轮巡检间隔 → 读 pane 尾部判空等/死亡再处置。
STATE=${FLEET_STATE_DIR:-${TMPDIR:-/tmp}/herdr-fleet-stall}; mkdir -p "$STATE"
HOSTS=${FLEET_HOSTS:?set FLEET_HOSTS="host:prefix ..."}
SUF=${FLEET_AGENT_SUFFIX:--dev1}
PUSHLOG=${FLEET_PUSH_LOG:-}
NOW=$(date +%s)
printf "%-8s %-8s %-6s %-14s %-9s %s\n" host status df pane wait lastpush
for hd in $HOSTS; do
  h=${hd%%:*}; dom=${hd#*:}; [ "$dom" = "$hd" ] && dom=""
  out=$(timeout 30 ssh -o BatchMode=yes "$h" "
    A=\$(/opt/homebrew/bin/herdr agent list 2>/dev/null | python3 -c \"import sys,json
for a in json.load(sys.stdin)['result']['agents']:
    if str(a.get('name')).endswith('$SUF'): print(a.get('agent_status'), a.get('pane_id')); break\")
    st=\${A%% *}; P=\${A##* }
    T=\$(/opt/homebrew/bin/herdr pane read \$P 2>/dev/null)
    echo STATUS=\$st
    echo DF=\$(df -h ~ | awk 'NR==2{print \$4}')
    echo MD5=\$(echo \"\$T\" | md5 -q 2>/dev/null || echo \"\$T\" | md5sum | cut -c1-32)
    echo WAIT=\$(echo \"\$T\" | tail -30 | grep -E '^\s*(⎿|Bash\(|·|✶|✻|✽|✢)' | grep -cE 'sleep [0-9]+|not yet|MERGED')
    echo LEASE=\$(echo \"\$T\" | tail -40 | grep -cE '租约申请|API Error|429')
  " 2>/dev/null)
  st=$(echo "$out" | sed -n 's/^STATUS=//p'); df=$(echo "$out" | sed -n 's/^DF=//p'); md5=$(echo "$out" | sed -n 's/^MD5=//p'); wait=$(echo "$out" | sed -n 's/^WAIT=//p'); lease=$(echo "$out" | sed -n 's/^LEASE=//p')
  f="$STATE/$h"; prev_md5=""; prev_ts=$NOW
  [ -f "$f" ] && { prev_md5=$(sed -n 1p "$f"); prev_ts=$(sed -n 2p "$f"); }
  if [ -z "$md5" ]; then pane="ssh-fail"
  elif [ "$md5" != "$prev_md5" ]; then printf "%s\n%s\n" "$md5" "$NOW" > "$f"; pane="changed"
  else pane="STILL $(( (NOW - prev_ts) / 60 ))m"; fi
  lastpush=""; [ -n "$PUSHLOG" ] && [ -n "$dom" ] && [ -f "$PUSHLOG" ] && lastpush=$(grep hubpush "$PUSHLOG" | grep -E "refs/heads/($dom)-" | tail -1 | awk '{print $3}')
  flag=""; [ "${lease:-0}" -gt 0 ] && flag=" LEASE/ERR"
  printf "%-8s %-8s %-6s %-14s %-9s %s%s\n" "$h" "${st:-?}" "$df" "$pane" "wait=$wait" "${lastpush:-none}" "$flag"
done
