# Solver Harness v1.2 发布验收

状态：离线工程门禁通过，`engineering-preview`。完整 live 发布被阻塞。

机器可检验的 [STAR AC/SC 最终归属矩阵](showcase-solver-v1.2-matrix.json) 覆盖 STAR AC-01..44 与 SC-001..043，每项只有一个最终责任 ticket。前置依赖以 [父规格 #32](https://github.com/RUSS0718/MathAgent/issues/32) 为准；测试 ID 对应实际 unittest 公开行为接缝。矩阵中的 covered 只表示有对应离线用例，实际执行结果在本记录收口时写入。

`scripted` 是脚本模型或模拟传输的离线工程证据；`replay` 是快照重放；`live` 是真实服务请求；`unavailable` 是所需能力没有充分证据。真实本地有限计算执行不等于真实模型工具选择，也不等于形式化证明。

[SH21 三次真实探针累计12次调用、1次工具执行；SH22 另有一组已完成的真实 Skills 配对，累计8次调用、2次工具执行。两组证据均来自同一道公开题，货币费用未知。历史 v0.2 AC-06 要求三道计算题各运行两次；当前只有五次同题 Run，因此仍为 unavailable，完整 live 发布继续阻塞。它与 STAR AC-06 的标签证据边界是不同验收项。[SH22 配对工程合同](showcase-solver-paired-report-sh22.md)记录真实配对回执及未升级为 `verified` 的限制；[SH20 零调用重放](showcase-solver-result-replay-sh20.md)仍为离线证据。

发布命令：`uv run python scripts/check_solver_release.py` 检查矩阵、文档链接、官方基线与离线范围；`--matrix-only` 仅检查归属和测试引用；`--require-live` 必须阻塞。工程门禁通过也不授权修改官方入口或合入 main。

本记录不宣称论文完整复现、完整形式化证明、数学正确率提升或真实策略收益。官方基线以根 BASELINE.json 的11个冻结文件为准，默认预算与输出合同不变。

## 前端与官方边界预检

2026-10-23，集成维护者在 integration `03a0d393dcc77f58c0a2ee9391cd32e18fcd562d` 主目录执行：`npm ci --no-audit --no-fund` 通过（66 packages），`npm audit --audit-level=high` 通过（0 vulnerabilities），`npm run check` 通过（依赖、typecheck、13项 unit、build）。前端源码未变，SH23工作树不重复安装。

同一集成版本官方 baseline hash 检查通过；相对 `6d90e51` 的 `user_agent.py`、`implementations/`、`BASELINE.json`、`requirements.txt` 无差异。本工作树的新 gate 另行重新验证11个文件hash和官方导入/JSON合同。BASELINE.json SHA-256：`7c7dba5d0eb17d916228ee7c9ce86fe7375d3ae9d359686e54a71b277215465b`。

## v1.2 显式路由

`features.star_routing=true` 才启用同 Explore 会话润色、部分解的 Meta 路由、预计划 Hint/Meta 和有界计划修复；默认关闭，保留 v1.1 调用路径。计划无效会记录 `PLAN_INVALID`，角色 JSON 解析失败会保留解析/调用审计；研究子任务超时不会记为 complete。配对实验的实际再探索开关为 `reexplore_after_replan`。

默认工程门禁的 PASS 表示映射的离线合同确实执行通过，仍不等于完整 live STAR 或真实工具闭环通过。

## 最终执行结果

2026-10-23 首轮离线门禁在 `c37220b66558346213c392ea58820e19d9cb6a53` 执行；随后对 live 报告和工具计数门禁作了小幅修订，并在 `6c7a7685495912686a0dc3501a077be14f3c10e6` 重新运行全量检查。最终 343 项测试的结果列在下表。本记录另补充获批的一次真实探针与一组配对运行；预算和结果列在机器矩阵与 SH21/SH22 记录中。

| 命令 / 检查 | 实际结果 |
| --- | --- |
| `uv run python scripts/check.py --offline` | PASS；343 项测试，184.772 秒，无跳过；workspace、公开接缝和 Demo/Showcase --help 均通过，repository_check=PASS |
| `uv run python scripts/check_showcase_release.py` | PASS；showcase_release=PASS，包含 Solver 工程门禁 |
| `uv run python scripts/check_solver_release.py` | PASS；44 AC / 43 SC，66 个映射测试实际执行通过，无 skip/expectedFailure |
| `uv run python scripts/check_solver_release.py --require-live` | 预期 exit 1；live_release=BLOCKED，needs_review，历史 v0.2 AC-06 unavailable，累计 tools=3 |
| Ruff、`git diff --check`、文档本地链接 | PASS |
| 官方11个冻结文件 hash、导入隔离、非空 JSON 返回合同 | PASS；相对 6d90e51 的官方4个范围无差异 |

标准与规格双轴审查发现的预算、研究 schema/超时、路由、计划修复、门禁绕过和润色候选绑定问题均已有公开回归并修复。v1.2 新路由采用显式开关，不改变冻结的默认官方路径。SC-019 保留 `needs_review`，历史 v0.2 AC-06 继续 `unavailable`，因为六次跨三题的 live 门槛尚未满足；真实配对成功不替代该门槛。

日志保存在被忽略的 `artifacts/sh23-release/`，已复制到主工作区同路径。机器记录保存各日志 SHA-256；日志不提交。发布矩阵是当前的唯一最终归属和实际结果入口；历史 v1.1 记录仅供追溯。上述工程通过不等于授权正式发布或合入 main。
