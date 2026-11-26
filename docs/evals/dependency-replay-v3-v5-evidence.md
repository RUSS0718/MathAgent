# 真实依赖复用复算 v3–v5 · 2026-11-26

本记录复算 [双循环 v3–v5](dual-loop-real-20261126-v3-v5-evidence.md) 的 12 个真实 Run，覆盖 #256 的依赖构建、请求送达和明确引用。实验源码为 `556857aa1d5489d8b5cd67ab5179ec4d0a09b744`。

| 观察项 | 计数 |
| --- | ---: |
| 独立接受的推导 | 35 |
| 带已接受 AND 前提的推导 | 18 |
| 同命题且同作用域的替代支撑 | 1 |
| 送达至少一项有效核查证据的确认请求 | 26 |
| 送达带 AND 前提的推导的确认请求 | 19 |
| 模型明确引用已送达证据的确认请求 | 20 |
| 模型明确引用带 AND 前提的推导的确认请求 | 14 |
| 实际撤销 | 0 |

复算按 Trace 顺序重建有效证据集。新增推导时检查其全部前提已有适用证明。随后将准备派发的证据 ID 与实际 Provider 请求记录对照，再将模型明确报告的引用与该次请求送达的证据对照。最终有效证据集与 Run 图快照一致。

## 同一个真实 Run 的两种证明支撑

DLV3-05 的 `run_3e785f40cfe64384b96c1e433f6acb9b` 包含同一候选完备性命题 `proposition_d70e7a5d02597d0cd6f11061` 的两项已接受支撑。它们均依赖已验证的平方约束 `proposition_ad4f696eed64e220788ff840`，作用域相同。

| 请求序号 | 证据动作 |
| --- | --- |
| 002 | Runtime 接受因式分解证据 `evidence_834ae4977500720a89296a64`。 |
| 006 | 请求送达 002 的证据，模型明确引用，Runtime 另外接受判别式证据 `evidence_c0f93c57757854749f7b3488`。 |
| 007 | 同一请求送达两项有效证据。模型明确引用两项证据。 |

## 验收范围

真实证据支持 #256 AC1、AC3 的运行时依赖构建和后续使用，并覆盖 AC4 的真实前提和支撑消费。AC2 与 AC4 的撤销传播仍以 [受控 Runtime 复跑](https://github.com/RUSS0718/RiCL/blob/556857aa1d5489d8b5cd67ab5179ec4d0a09b744/tests/test_runtime_scoped_derivations.py#L81) 为证。

常规 CLI 构造 Runtime 时未提供独立撤销来源。精确核查在固定题面上先评价再入图。错误提议被拒绝入图，题面不变时后来出现的错误提议不会推翻先前通过独立核查的证明。真实撤销验收仍需具有明确失效条件的独立证书，并在证书失效后复核只撤销实际失去支撑的结论和目标。[#256](https://github.com/RUSS0718/RiCL/issues/256)

## 复算

在实验工作树执行 `uv run python -B artifacts/dual-loop-dependency-replay.py ricl-dual-loop-20261126-v3 ricl-dual-loop-20261126-v4 ricl-dual-loop-20261126-v5`。脚本使用既有 Run 和 Trace 哈希，且不调用 Provider。

| 产物 | SHA-256 |
| --- | --- |
| `dual-loop-dependency-replay.py` | `39c8fb36a7dbfb23de36ef3c7847ef59e3b3c1541c3bcf004b8d1848b42474f4` |
| `dual-loop-dependency-replay.json` | `84d7d3041af2250224f2718965896bcb695ccdb2abed5336eb9db26a96d9cb4e` |
