#!/usr/bin/env bash
# 把一个模型当成「无工具、无会话」的纯规划函数调一次，拿回一张任务图。
# packet 走 stdin 或参数。绝不在 packet 里放密钥。
set -euo pipefail

if [[ $# -gt 0 ]]; then packet="$*"; else packet="$(cat)"; fi
if [[ -z "${packet//[[:space:]]/}" ]]; then
  echo "需要在 stdin 或参数里给出非空的 packet。" >&2
  exit 64
fi

# 规划端命令：裸 claude = 本机订阅登录态；c0/c1/c2/c3 等 = GLM alias（含鉴权）。
PLANNER_CMD="${PLANNER_CMD:-claude}"
# 模型必须显式指定，空表示「用该命令的当前默认模型」。不做任何猜测式发现。
PLANNER_MODEL="${PLANNER_MODEL:-}"
PLANNER_EFFORT="${PLANNER_EFFORT:-medium}"

# 清掉宿主会话注入的变量，否则新起的 claude 会被识别成子会话：
# 不在 sessions/ 登记、transcript 关闭、--session-id 失效。
while IFS='=' read -r key _; do
  [[ -n "$key" ]] && unset "$key" || true
done < <(env | grep -E '^(CLAUDE|ANTHROPIC)[A-Za-z0-9_]*=' || true)

sys_file="$(mktemp)"; packet_file="$(mktemp)"
trap 'rm -f "$sys_file" "$packet_file"' EXIT

cat > "$sys_file" <<'SYS'
你是编排控制器。你只做规划与裁决，绝不实现任何东西，也绝不把任务分配给自己。
只使用 packet 里给出的事实，不要假设 packet 之外的 workspace 状态。

输出一张紧凑的可执行任务图，不是实现。每个节点必须写全：
- id
- 目的
- 依赖（其它节点的 id）
- 执行者（只能从 packet 给出的「可用执行端清单」里选，不得发明）
- 独占的文件或职责（并行节点之间不得重叠）
- 预期产出
- 验证方式
- 停止条件

另外：
- 标出哪些节点可以安全并行；
- 在满足目标的前提下把节点数压到最少；
- 结尾必须有一个集成 + 终验节点；
- 保持用户原本的范围与审批边界，不扩权；
- 如果 packet 里没有可用的执行端，直接报告这个阻塞点，不要编造模型或代理名；
- 不要输出思维链，只给决策和一句话理由。

开头先用每行一条的形式列出可立即开始的分配：
执行者 — 模型: 有界的职责
SYS

printf '%s' "$packet" > "$packet_file"

model_arg=""
[[ -n "$PLANNER_MODEL" ]] && model_arg="--model $PLANNER_MODEL"

# 用交互式 zsh 执行，好让 c0/c1/c2 这类 .zshrc alias 可用（非交互 shell 里 alias 不存在）。
set +e
response="$(zsh -ic "${PLANNER_CMD} --print ${model_arg} --effort ${PLANNER_EFFORT} \
  --tools '' --no-session-persistence --output-format text \
  --system-prompt \"\$(cat ${sys_file})\" \"\$(cat ${packet_file})\"" 2>&1)"
status=$?
set -e

if [[ $status -ne 0 ]]; then
  echo "规划端调用失败（PLANNER_CMD=${PLANNER_CMD} PLANNER_MODEL=${PLANNER_MODEL:-default}）：" >&2
  echo "$response" >&2
  exit 69
fi

printf '规划端 (%s / %s) 返回：\n\n%s\n' "$PLANNER_CMD" "${PLANNER_MODEL:-default}" "$response"
