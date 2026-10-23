# SH22 配对运行工程合同

**关联：** [#54](https://github.com/RUSS0718/MathAgent/issues/54)、父规格 [#32](https://github.com/RUSS0718/MathAgent/issues/32)。

**状态：** 离线报告工程验收通过。2026-10-23 获准执行一组真实 Skills 配对：两臂均完成并保留真实用量与工具回执；真实费用未知，`live_gate` 保持 `needs_review`。单组运行不构成能力提升或完整 live 发布证据。

## 公共入口与条件

`showcase.solver_harness.paired.PairedRunner` 暴露 `run_pair(...)` 与 `get_report(pair_id)`。runner 复用 `SQLiteStore`、`SolverHarness` 和同一 SQLite 文件，不创建第二个网络服务。`solver_pairs` 保存配对 manifest、两条独立 Run ID、逐臂结果和最终报告。

两臂使用相同原题、角色可用性、声明模型版本、Profile、工具权限、传输限制与硬预算。仅 `strategy_feature` 指定的一个布尔开关可以不同。当前允许 `skills`、`reexplore_after_replan`、`candidate_registry`、`best_effort`。非开关配置、工具注册集合、执行来源或可观察模型不一致时，在任何调用前拒绝整对运行。跨臂复用 port 实例也会拒绝。

可观察的客户端模型 ID 优先于 adapter 声明；若与声明不符，则拒绝运行。模型 revision 可观察时同样验证。服务通常不提供固定 revision，报告保留 `declared_only`，不声称提供了不存在的版本证据。脚本 port 没有可观察模型标识时，报告明确为 `identity_status=unknown`，只支持工程结论。

脚本运行依靠已有 Harness 预算。包含真实 adapter 的注入运行另外绑定已有 `RunBudgetLedger`，在发送逻辑调用和每次 HTTP attempt 前预留预算；本次真实运行还将每臂预算绑定到 Registry 工具线程，保留工具计数。离线脚本 CLI 仍不提供 live 开关；真实调用使用显式 `provider_live` 端口和相同预算条件。

## 保留和恢复

两臂按顺序执行，每臂调用前持久化 `dispatching`，完成后保存结果。一个臂失败不会删除另一个臂结果。报告根据 Harness 的 `failed_runtime`、`partial_aborted`、`interrupted` 和 `running` 区分失败、未知与未完成，不以“没有抛异常”推定成功。

`get_report` 不重新发送模型请求。进程在臂执行期间退出时，恢复报告把 `dispatching` 标为 `unknown_outcome`，同时读取已持久化 Solver Run；未发送的另一臂仍是 `not_dispatched`。中断时长无法恢复，保留 `null` 并注明来源，而非编造测量。已完成的同一 `pair_id` 与相同输入返回原报告；绑定其他原题或条件会拒绝。

报告保留角色输出、失败类别、未知调用、provider attempts、实际模型记录、usage、预算、工具回执、精确 Profile 和关闭能力原因。原题只保留 SHA-256，组合 prompt、角色输入、会话历史和原始 provider response 不进入报告。每条 provider response 保留哈希。缺失 token 字段和未知费用为 `null`；usage 仅在所有相应字段均已知时求和，不把部分已知和误称总量。

完成臂的耗时使用 `time.monotonic()` 包围 Solver 调用，来源为 `monotonic_wall_clock`，属于测得的工程运行时间。报告不根据耗时、调用数或一次答案比较推导数学能力提升。

## 离线使用

```powershell
uv run python scripts/run_solver_pair.py
```

命令运行两个独立脚本臂，比较 `skills=false` 与 `skills=true`，把 SQLite 和 `report.json` 写入被忽略的 `artifacts/paired-<id>/`。可用 `--database <path>` 和 `--pair-id <id>` 复取已存在的配对报告。输出中的 `completed` 只表示两臂均已归档；`live_gate` 仍为 `needs_review`。

离线检查：

```powershell
uv run python -m unittest discover -s tests -p test_solver_harness_paired.py
uv run ruff check showcase/solver_harness/paired.py showcase/solver_harness/paired_conditions.py scripts/run_solver_pair.py tests/test_solver_harness_paired.py
```

测试覆盖两 Run 隔离、条件不一致预先拒绝、失败保留、进程中断恢复、未知 usage 和费用、真实 adapter 的模拟 HTTP attempt 审计，以及同一配对身份不可重新绑定。模拟 HTTP 测试不是实际服务证据。

## 一组真实配对记录

本次只比较 `skills=false` 与 `skills=true`，其余题目、Intern-S2 模型、工具权限、Profile、传输限制和预算相同。配对条件观测到的模型 ID 为 `intern-s2`，返回 ID 为 `Intern-S2`；服务未提供 revision，因此 revision 仅声明，未冒称为服务观测值。

| 臂 | Skills | HTTP / 逻辑调用 | 本地工具 | Provider tokens | Run 结果 | 未知调用 | 费用 |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| control | off | 4 | 1 | 5927 | `completed_llm_reviewed` | 0 | `null` |
| variant | on | 4 | 1 | 5761 | `completed_llm_reviewed` | 0 | `null` |

两臂的真实 `polynomial_check` 均返回成功，step Verifier 的调用记录均包含对应 receipt ID，整题结果均通过 LLM review。两份 receipt 的 `assertion_matched=false`：模型未提供与本地结果完全匹配的 `expected_output`，所以工具结果没有被升级为 `verified`。工具仅检查候选代回；答案完整性仍由其代数论证和 LLM review 表示，不等于形式化证明。

本组配对 ID 为 `solver-pair-live-skills-v1`，报告保存在被忽略的 `artifacts/sh23-release/solver-pair-live-skills-v1/report.json`，SHA-256 为 `cae1c8f26f1f177bd4fd37abde97b77b204be65e460d2482fbc12e3d29c094be`；`summary.json` SHA-256 为 `c923fff394b4848f9f902cb90ad6b3f3f7e41303fdfb468ea920d4c41f4b6b1c`。本组实际使用 8 次 HTTP、2 次工具调用和 11688 provider tokens，花费未知。配对报告状态为 `completed`，live gate 仍为 `needs_review`。

新授权轮次合计使用 12 次 HTTP、3 次本地工具执行和 17478 provider tokens；每次请求只有一次物理 attempt，未知调用为 0，货币费用未知。SH21 的 probe 与本组配对共包含三次 Run，均为同一道公开题。旧 `v0.2 AC-06` 要求三道计算题各运行两次，目前总计五次 Run 且只有一道题，因此仍为 `unavailable`。本组不用于推断策略收益或数学正确率提升。
