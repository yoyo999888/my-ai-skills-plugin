---
name: ci-polling-discipline
description: 约束 GitHub Actions、PR checks 等 CI 状态查询频率，避免等待期间空转和浪费 token；在 push 后检查 CI、等待构建、跟踪 PR checks 或排查 CI 失败时使用。触发词：检查 CI、等待 CI、跟踪 checks、CI 轮询、GitHub Actions。
---

# CI polling discipline

用最低查询频率跟踪 CI，不为等待本身消耗 token。

## 何时使用

- push 后确认 CI 是否创建。
- 等待 GitHub Actions、PR checks 或其他远端 CI。
- CI 失败后读取结论与失败日志。

## 规则

1. push 后可以立即查询一次，确认 CI run 已创建。
2. CI 处于 queued 或 running 时，最多每 10 分钟查询一次；两次状态查询的间隔不得短于 10 分钟。`gh run view`、`gh pr checks`、网页/API 查询都算一次状态查询。
3. 等待期间禁止倒计时、重复状态播报、`sleep`、空等待、无意义工具调用，或为了凑够轮询间隔而做与任务无关的工作。
4. 当前工作已经完成且用户没有明确要求持续监控时，确认 run 创建后立即交付，不留在当前 turn 等 CI；用户后续询问时再查。
5. 用户明确要求持续监控时，优先使用产品提供的自动唤醒或监控机制。没有这类机制时仍遵守 10 分钟最小查询间隔，不用对话 token 模拟计时器。
6. CI 已结束、失败通知已经到达，或用户提供了新的失败状态后，可以立即读取结论和失败日志，无需额外等待。
7. 查询时一次拿齐所需状态；失败后集中读取失败 job 日志，避免对同一状态做多次等价查询。

## 交付

简洁报告 run 或 checks 的当前结论、失败根因（如有）和下一步。不要复述等待过程。
