# ALIGN-10 全机制来源映射与七类修复来源复核

状态：ALIGN-AC-17 的来源映射记录；完成声明由 [ALIGN-10 发布记录](star-product-align10-release.md) 的实际证据决定。日期：2026-10-25。

本表编号沿用本项目合同（SC 来自 STAR Core 本地合同、ALIGN-AC 来自 spec #70），**都不是原论文自带编号**。原论文与固定上游源码用于独立核对机制；本地测试是结果证据，不能反向定义上游。

## 固定输入

- 论文：[arXiv:2605.19338v1](https://arxiv.org/html/2605.19338v1)。行号引用自 2026-10-24 审查固存的论文快照（`artifacts/star-alignment-review-20261024/paper.txt`，ignored 产物；§/附录编号与 arXiv HTML 一致）。
- 上游：[Julius-Woo/STAR-PolyaMath](https://github.com/Julius-Woo/STAR-PolyaMath/tree/5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d) 固定 commit `5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d`（2026-06-08）。行号经该 commit 的原始文件逐个核对（GitHub raw）。
- 本地基点：集成分支 `showcase-star-align` 尖端（ALIGN-01..09 已合入）；完整 43 行 SC→论文/上游定位继承 [SP-01 来源审计](../experiments/star-product-source-audit.md)，本表只更新分类结论与本轮七类修复的来源复核，不重写 SP-01 历史。

## 一、全机制分类总表（相对固定论文与固定上游 commit）

分类口径：**一致**＝论文描述的机制在本项目公共路径实际存在且语义相同；**缺失**＝论文/上游有而本项目没有（修复前曾缺失、本轮恢复的机制单独标注）；**有意适配**＝保留机制意图但实现边界不同，且差异有书面理由；**项目扩展**＝本项目新增、论文无对应合同；**冲突**＝上游实现与论文或本项目合同互相矛盾，本项目选择其中一方并记录。

| 机制（SC） | 论文定位 | 上游锚（固定 commit） | 分类 | 本地实际路径与结果证据 |
| --- | --- | --- | --- | --- |
| 隔离实验入口、官方合同冻结（SC-001/025） | B.1 | `src/runner.py` | 有意适配 | `showcase/flask_app.py` 公共 Job 入口替代 CLI runner；BASELINE.json/导入边界由 `scripts/check_showcase_release.py` 门禁 |
| 确定性状态机（SC-002） | 3.1, B.1 | `orchestrator_solve.py` | 一致 | `showcase/solver_harness/controller.py`；ALIGN-02 修复后 CONTINUE 不再撞事件身份 |
| Exploration 与提前成功（SC-003） | 3.2 | `orchestrator_exploration.py` | 一致（计算通道为适配） | `star_routing.py` 快通道；ALIGN-06 后 Explore 可提受控计算（见七类表 §4.6） |
| 预计划 Meta 与用户 Hint（SC-004） | 3.3 | `orchestrator_planning.py` | 有意适配 | `star_routing.py` hint/预计划入口；策略库以 skills 协议文本承载 |
| 计划生成与结构验证（SC-005） | 3.3 | `orchestrator_planning.py` | 一致 | `planning.py`/`plan_generation.py`（一次修复重试） |
| 逐步 Reasoner 与验证标签（SC-006/007） | 3.4 | `orchestrator_execution.py` | 一致 | `step.py`/`verification.py`；verified/easy-verify/hard-verify 标签语义保持 |
| 双 Gate 与四类裁决（SC-008） | 3.4 | `orchestrator_execution.py` | 一致 | `verification.py`（ACCEPT 必须 goal=YES&logic=PASS） |
| 有界连续 Challenge（SC-009） | 3.4 | `orchestrator_challenge.py` | 一致 | `challenge.py`；本轮 ALIGN-07 后 CHALLENGE 保留分类部分成果 |
| Trace-Back、归档、救援（SC-010/035） | 3.4, B.5 | `src/state.py:575-` | 一致（消费语义为适配加强） | `traceback.py`；ALIGN-01 后仅消费当前转换关联裁决（见 §4.1） |
| 持久化 Meta 裁决（SC-011） | 3.4, C.3 | `orchestrator_failure.py:99-148` | 一致 | `meta.py`；裁决按转换即时消费 |
| Re-Plan 与禁止方向（SC-012） | 3.4, B.1 | `orchestrator_solve.py:113-187,308-326` | 有意适配（审批边界） | `replan.py` 经独立 ReplanDecision（见 §4.2） |
| 最终生成及整题审查（SC-013/036） | 3.5 | `orchestrator_solve.py:427-490` | 一致（失败分支见冲突行） | `finalize.py`；ALIGN-08 后证明正文实际传递（见 §4.5） |
| 七种按需 Skill（SC-014） | B.2 | `.github/skills/` | 一致 | `skills.py` `PROTOCOLS` 七类协议 |
| 角色会话与状态注入（SC-015/029/030/037） | B.3 | `agent_runner.py`, `hooks/inject_problem_context.py` | 有意适配 | `sessions.py`/`context_injection.py`；CLI 会话换为 SQLite 角色会话 |
| 快照、事件与恢复（SC-016/038） | B.5, B.1 | `src/state.py` 双文件 | 有意适配（加强） | `storage.py` CAS+事件；恢复合同按 ADR-0014，ALIGN-09 跨流程验收 |
| 本地工具与权限（SC-017） | B.4 | `agent_runner.py`（CLI 执行） | 有意适配（加强） | `tool_ports.py`+Docker 隔离 Registry；上游 CLI/工作目录执行不复刻 |
| 预算、循环与超时（SC-018） | A | `src/config.py` | 一致（数值不同） | `run_budget.py` S3 唯一账本；参考预算 48/48/8/262144/1100s |
| 模型适配与真实用量（SC-019） | 3.1, A | `agent_runner.py` | 有意适配 | `intern_port.py`+`adapters.py`；Intern S2 单模型（上游亦单模型 gpt-5.5，数值见 SP-01 默认配置核对） |
| 错误分类与有界恢复（SC-020） | B.1 | `orchestrator_execution.py:560-561,637` | 有意适配（严格 schema） | `calls.py`；ALIGN-04 后已知协议失败与 unknown 分离（见 §4.4） |
| 输出 JSON 合同（SC-021/042） | 3.5 | `orchestrator_solve.py` | 项目扩展（输出隔离） | `result.py` 只导出 `final_response`；官方合同隔离 |
| Feature Flags 与模式身份（SC-022） | A | `src/config.py` | 项目扩展 | `star_product_config.py`/`star_product_modes.py`；完整 9 核心特性门禁 |
| 脱敏 Trace 与事件审计（SC-023） | B.5 | `src/state.py` | 项目扩展 | `star_product_events.py` 白名单+`redaction.py` |
| 端到端验收与发布边界（SC-024/025） | 项目验收 | 无上游编号 | 项目扩展 | `tests/`+`scripts/check*.py` |
| 配对实验（SC-026） | 4.3, D | `agent_runner.py` | 一致 | `paired.py`/SP-13 AC-20 公共配对 |
| 接受≠形式化定理（SC-027） | 3.4 | `orchestrator_execution.py` | 一致（加强） | `verification.py`/`final_binding.py` limitations 固定写入 |
| 四层记忆与正负账本（SC-028） | B.3, B.5 | `src/state.py:993-,2218` | 一致（本轮恢复） | 分类账本 `verified_results_ledger`（见 §4.3） |
| 后重规划再探索（SC-033） | B.4 | `orchestrator_exploration.py:344` | 一致 | `research.py` 非代码研究委派 |
| easy-verify 自动预检（SC-034） | 3.4, C.1 | `orchestrator_execution.py` | 一致 | `tool_precheck.py` 回执制预检 |
| 候选登记/零调用选择/回放/定性等级（SC-039..043） | 项目扩展 | 无上游合同 | 项目扩展 | `candidates.py`/`best_effort.py`/`replay.py`/`confidence.py`；不得归功原 STAR |

### 冲突与已知差异（保留 SP-01 结论，按本轮复核更新）

| 冲突/差异 | 论文/上游观察 | 本项目处理 |
| --- | --- | --- |
| 整题审查调用失败仍接受 | 上游 `orchestrator_solve.py:485` "accepting solution without verification"；论文 §3.5 要求整题审核 | 不复制：审查失败标 `completed_unverified`/needs_review，永不标 verified（`final_binding.py`、SP-10 验收） |
| Guidance replan 短路换计划 | 上游 `orchestrator_execution.py:362-386` 把 Guidance `action_type=replan` 短路为 APPROVE_REPLAN，注释自述避免重复 Meta 调用；论文 §3.4 要求统一 ReplanDecision（paper.txt:659-663） | 按论文与 STAR Core §11.3：进入独立 ReplanDecision，仅当前转换有效 APPROVE_REPLAN 归档（ALIGN-03）。这是对上游短路的有意适配，不宣称上游错误 |
| `[verified]` 视为直接 grounded | 论文 C.1（paper.txt:2534-2538）verified 直接 grounded、easy-verify 由 Verifier 独立复算 | 保留标签语义但加范围约束：finite_computation 之外不升级；模型自标无回执即降级（`tool_precheck.py`/`step.py`） |
| 上游无未知调用合同 | 上游 CLI 平台无 unknown 预留/显式重试概念；本项目 S3/ADR-0014 要求保留 unknown 人工处置 | 项目扩展：unknown_outcome 零自动重发，显式新身份 resume（SP-08、ALIGN-09 验收） |
| 平台差异 | 上游 Copilot CLI 会话+工作目录文件+URL deny | Intern S2 API、共享 SQLite、Docker network=none 隔离、较小硬预算、独立 Best-Effort（ADR-0013/0014 已说明，均非本轮重写目标） |

### 当前仍缺失/未覆盖（诚实清单）

- live 自然触发的 Challenge、Trace-Back、Replan：本轮真实批次未触发即记 not_covered，其适用行为由 scripted/故障注入公共验收支撑（#70 证据分层要求，不得强迫模型表演）。
- 上游 CLI 平台的文件编辑/工作目录能力：有意不引入（隔离合同），不作为缺失缺陷。
- 论文多角色可配置不同模型（§4.1 消融）：本项目固定单模型 Intern S2，属平台适配，不做模型混合消融。

## 二、本轮七类修复的来源、路径、唯一责任与结果证据

每行：来源＝论文定位＋上游锚；实际路径＝本轮修复落点；唯一责任＝该缺陷的最终责任票；结果证据＝公共验收与旁路反例（全部在集成分支上真实执行，执行记录见 [ALIGN-10 发布记录](star-product-align10-release.md)）。

| # | 缺陷（spec #70） | 来源（论文/上游） | 实际路径 | 唯一责任 | 结果证据 |
| --- | --- | --- | --- | --- | --- |
| 1 | 旧 MetaGuidance 覆盖后续合法回退/重规划裁决 | 论文 §3.4 单一 ReplanDecision 按提案裁决（paper.txt:659-663）、B.1 orchestrator 无状态重算（paper.txt:2123）；上游每提案即时返回新决定并当场消费（`orchestrator_failure.py:99-148`、`orchestrator_solve.py:113-187`） | `traceback.py` `transition_decision` 只认当前转换关联裁决；`meta.py` 裁决带作用域与消费标记（commit `dee503c`） | ALIGN-01 #71 | `tests/test_star_product_guidance_consumption.py`（含 `test_bypassing_the_consumption_gate_reproduces_stale_preemption` 旁路反例；Docker 门控 reference 用例） |
| 2 | 首次 PROPOSE_REPLAN 后 Meta CONTINUE 复用旧事件身份 | 论文 B.1 伪代码 PROPOSE_REPLAN→Replan Decision 子流程；上游 CONTINUE 落回执行不再派发同一步（`orchestrator_solve.py:324` "treating verifier verdict as challenge"） | `meta.py` CONTINUE 进入新求解动作；`step.py` challenge-continuation 后缀新事件/调用身份（commit `3f4f75b`+`11a8c9e`） | ALIGN-02 #72 | `tests/test_star_product_continue_identity.py`（新动作身份、Challenge 历史不清空、进程退出恢复、reference 预设） |
| 3 | Guidance replan 直接换计划，绕过 ReplanDecision | 论文 §3.4 "All proposals are routed to a single Replan Decision"（paper.txt:659-663）；上游短路见冲突表（`orchestrator_execution.py:362-386`，有意适配对象） | `meta.py` 独立 ReplanDecision 相位；`replan.py` `replan_ruling` 只认本次 APPROVE_REPLAN 的禁止方向/救援（commit `05be841`） | ALIGN-03 #73 | `tests/test_star_product_replan_decision.py`（三分支、`test_bypassing_the_approval_gate_reproduces_the_stale_guidance_archive` 旁路反例、恢复只裁一次、reference 预设） |
| 4 | 完整收到但格式非法的响应被归为 unknown | 论文 B.1 决策重算；上游把空响应记为已知失败（`orchestrator_execution.py:560-561`）、不可解析裁决落回 CHALLENGE（`:637`）、终稿以错误模式判失败（`orchestrator_solve.py:431-450`） | `calls.py`/`intern_port.py` 已知协议失败（invalid_json/invalid_role_schema/empty/truncated）与 unknown 分离，有界格式修复或诚实终止（commit `a4dc901`）；ALIGN-10 live 复核后补：探索阶段获得与 Planner 相同的一次格式修复属主（commit `f9861b3`），explore/reasoner 回复协议接受显式 null 候选（commit `0abf438`） | ALIGN-04 #74（修复属主扩展：ALIGN-10 #80） | `tests/test_star_product_protocol_failure.py` + `tests/star_protocol_failure_mutations.py`（4 旁路反例；探索修复/耗尽两用例为 #80 新增） |
| 5 | Verifier 声明计算权限却无法提出计算请求 | 论文 C.1 验证标签协议 "[easy-verify] claims are independently re-executed by the Verifier"（paper.txt:2538） | `verifier_compute.py`+`intern_schemas.py` step_verifier 可选 tool_request；回执前不得接受/升级（commit `9a5e20a`） | ALIGN-05 #75 | `tests/test_star_product_verifier_compute.py` + `tests/verifier_compute_mutations.py`（2 旁路反例） |
| 6 | Explore 固定为无计算探索 | 论文 §3.2 "enumerating small cases"（paper.txt:569）；上游 explore 提示明确 "run small cases when useful"、脚本存 `explore_*.py`（`agents_reasoner.py:674-680`） | `explore.py` 受控 tool_request+续接，发现保持未证探索身份（commit `517c901`） | ALIGN-06 #76 | `tests/test_star_product_explore_compute.py` + `tests/explore_compute_mutations.py`（3 旁路反例） |
| 7 | Verifier 无法分类成果；账本批量收集 Reasoner 陈述；最终生成丢证明正文 | 论文 C.1 Verdict schema "Verified Results — tagged [Lemma]/[Conjecture]/[Computation]/[Definition]/[Answer]"（paper.txt:2794-2797）、B.5 Verified Results Ledger（paper.txt:2218）、§3.5 "consolidates the accepted step reports"（paper.txt:685）；上游账本取自 Verifier 文件（`state.py:993`）、救援带来源（`:640-666`）、终稿注入已完成步骤上下文（`orchestrator_solve.py:427,454`；`state.py:955-986` 优先 Verified Results、回落完整报告） | 分类账本：`classified.py`+`verification.py`+`verified_results_ledger`（commit `7ccc392`，#77）；证明传递：`finalize.py` `proof_basis`（commit `67bb62c`，#78） | ALIGN-07 #77；ALIGN-08 #78 | 分类：`tests/test_star_product_classified_outcomes.py`+`classified_outcomes_mutations.py`（3 反例）；证明：`tests/test_star_product_final_proof.py`+`final_proof_mutations.py`（3 反例，含 S4 绑定旁路）；S4 本体 `final_binding.py`（SP-10 合同不变） |
| 8（配套） | 干预消费/回执/成果/最终候选的持久边界中断恢复 | 论文 B.5 双层状态恢复；ADR-0014 跨状态提交合同 | `star_product_recovery.py`+既有恢复原语覆盖新边界（commit `c00d4a5`） | ALIGN-09 #79 | `tests/test_star_product_align_recovery.py`（五窗口真实进程退出、`test_bypassing_receipt_recovery_reexecutes_the_computation` 敏感性反例、reference 预设真实隔离） |

## 三、旁路敏感性检查（ALIGN-AC-16 汇总）

五类机制各有最小旁路反例且当前全部生效（故意绕过→对应公共验收失败）：

| 机制 | 旁路反例 | 执行方式 |
| --- | --- | --- |
| 裁决消费 | `test_bypassing_the_consumption_gate_reproduces_stale_preemption`、`test_bypassing_the_approval_gate_reproduces_the_stale_guidance_archive`（重现缺陷即证明检查有效） | `python -m unittest`（随套件） |
| 独立工具执行 | `verifier_compute_mutations`（2）、`explore_compute_mutations`（3） | `python -m tests.*_mutations` |
| 分类账本 | `classified_outcomes_mutations`（3：丢分类、无回执/依赖、猜想升级） | 同上 |
| 证明传递 | `final_proof_mutations`（丢正文、归档复活） | 同上 |
| S4 绑定 | `final_proof_mutations`（未绑定交付）；协议栅栏 `star_protocol_failure_mutations`（4） | 同上 |

实际执行输出与逐条结果记录在 [ALIGN-10 发布记录](star-product-align10-release.md)。
