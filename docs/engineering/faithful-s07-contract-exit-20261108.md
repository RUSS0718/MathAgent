# F1/S07 证明依赖图与 GraphBootstrap 合同及退出记录

日期：2026-11-08（Asia/Shanghai）。初始源码基线：`47428eb7263cf2cb3a452df3967f81ffd88a8510`。当前状态：实施中。

依据 GitHub #147、#139 最终决议 `6689524325`、Faithful implement-spec（只读 `git show docs/wayfinder-chat-output-prototype-20261106:docs/specs/mathagent-faithful-implement-spec-20261107.md`）及 S03/S04 退出合同。实现仅限 F1/S07；不实现路线/APRS、Lean、Composer 或前端。

## 范围与实现接缝

- 在现有 Solver Harness 中显式启用 `proof_graph`，默认关闭且排除 `CORE_FEATURES`；配置身份冻结能力，旧 Run 不迁移。
- 图快照是 `solver_states.state_json` 中受控状态的派生索引，账本仍是数学来源。图更新在 `SolverStateStore.commit_event` 已开始的 SQLite 写事务中、读取数据库当前快照并通过 `controlled_patch` 的取消/deadline 检查后生成；不得依赖 `validated_run` 作为权威。状态快照、`state_revision` 与脱敏事件摘要同事务/CAS 提交。
- 每个合法图变化追加完整不可变 `graph_version`；Solver 状态仅指向当前版本。失败校验、CAS 冲突、取消或 deadline 不得留下部分状态或事件。
- `verified_results_ledger` 中当前有效、非 `Conjecture`、来源报告/Reasoner 调用与 Verifier 审查可核验、所有适用 receipt 完整且依赖可映射的记录，才能成为 bootstrap 锚点。导入保留原 evidence grade 和 provenance，不推断/提升。无法映射的记录留在 `not_imported_records` 并记录受控原因码，不捏造边。探索发现、Reasoner 声称、失败、unknown、Conjecture 和失效账本记录不能作锚点。
- 命题身份为规范化陈述（Unicode NFKC、空白折叠）+ scope + problem hash + specification version；稳定 ID 由控制器分配。同版本跨快照引用须重绑至当前快照节点；跨版本引用无迁移表时拒绝。
- 每个 ProofAttempt 的前提是 AND；同一命题不同有效支持 attempt 是 OR。`proposed` 仅代表模型报告候选，只有既有 Verifier/Controller 接受的账本证据可写为 `accepted`。
- 命题状态限 `unresolved / supported / invalidated / refuted`；attempt 状态限 `proposed / accepted / rejected / invalidated / unknown`。`conflict` 为独立 bool。有效支持和独立核验反例并存时置 true；撤销其中一个不清除标记，只有引用有效新审查证据的显式解除事件才清除。冲突节点不可作有效前提。普通失败不成为反例。
- 回退和重规划以既有账本的 invalidated/source validity 为准；一旦旧 attempt invalidated，不得因旧快照或恢复读取而复活。新数学尝试使用新 ID 并保留 lineage；传输续接不创建新尝试。

## S05 消费的只读投影接口

函数：`showcase.solver_harness.proof_graph_projection.proof_graph_summary(state, graph_version=None)`。

- 图关闭或旧 Run：返回 `None`，不增加旧响应字段。
- 图启用：省略版本取当前快照；显式版本仅在持久快照存在时返回；缺失/未知版本返回 `None`，不合成深链。返回以下 JSON 可序列化结构，键固定：

```json
{
  "graph_version": 3,
  "propositions": [
    {"id":"p1","status":"supported","grade":"llm_reviewed","conflict":false,
     "dependencies":[],"sources":["source-1"]}
  ],
  "attempts": [
    {"id":"a1","status":"accepted","direction":"support","grade":"llm_reviewed",
     "conclusion":"p1","dependencies":[],"sources":["source-1"]}
  ]
}
```

ID 是按指定快照内稳定排序重生成的 `pN`/`aN`，只在 `(run_id, graph_version)` 内有效；同一快照来源身份排序后生成一份共享 `source-N` 映射。`dependencies` 是命题 `pN` 的列表（attempt 上表示 AND 前提，命题上表示当前有效支撑前提并集）；命题的多个 accepted attempt 构成 OR。`status` 限各自四/五个状态；`grade` 仅为 `llm_reviewed`、`tool_verified`、`mixed` 或 null，不高于来源等级；`direction` 限 `support`/`counterexample`；来源为遍历生成的 `source-N` 别名。摘要不含命题陈述、证明正文、原始 ID、来源字符串、报告、prompt、调用凭证或工具回执正文。来源别名不使用账本或模型提供的任意文本。

## 聚焦退出条件

1. 默认关闭与旧 Run 字节语义兼容；opt-in 运行创建显式 bootstrap 记录，Run 冻结图策略。
2. A/B OR 独立支持同一命题；C 依赖该命题时逐个撤销支持，最后支撑撤销才令 C 失效。
3. AND 前提完整有效才可接受；循环、悬空/重复 ID、旧/未来版本引用、无效/冲突前提及缺失报告/调用/review/receipt 整次拒绝。
4. 反例与支持并存时独立 conflict；撤销反例不清 conflict，必须有可核验的新审查并显式解除；失败/unknown 不作 refutation。
5. Bootstrap 保留未导入原因与来源/等级，不导入 Conjecture、未验证模型报告、失效项或无法完整映射依赖的项。
6. SQLite 事务/CAS、取消/deadline 原子性，重启后保留快照；traceback、replan 和旧恢复不会复活已失效来源；旧 Run 不回填。
7. 投影白名单和序列化回归通过；官方 baseline 保持字节一致。

每个行为组先有失败验收，再实现最小生产路径并聚焦回归；退出时记录 Standards/Spec 双轴审查及修复。协调者负责集成与全仓最终门禁；此工作树不运行全仓长门禁。provider-live、真实数学效果、自然题方法忠实性和 Docker/Reference 覆盖不因离线验收改变状态。

## 退出证据

### 集成前纵切记录

状态：实现纵切待提交，阶段仍待 Standards/Spec 审查结果及集成后的真实 Job 验收；本记录不声明 S07 工程退出。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| S07 graph 聚焦 | 13 项通过 | 协调者记录 `artifacts/faithful-s07/coordinator-focused-04.log`；`uv run python -m unittest discover -s tests -p 'test_faithful_s07_*.py'` |
| 新增持久边界验收 | 4 项通过 | `uv run python -m unittest tests.test_faithful_s07_boundaries`；合法格式伪造历史与旧 Run 热启在公共 CAS 入口拒绝，取消/deadline 写栅栏、来源核验及拒绝原因重启保持 |
| Harness 相关回归 | 33 项运行，32 项通过、1 项 skip | persistence 5、classified 13、events 6、STAR classified 9；分别运行 `uv run python -m unittest discover -s tests -p 'test_solver_harness_persistence.py'`、`...classified.py`、`...events.py` 和 `uv run python -m unittest discover -s tests -p 'test_star_product_classified_outcomes.py'`。skip 未计通过 |
| Ruff 与差异 | 通过 | `uv run ruff check` 覆盖本纵切修改的 Python 文件；`git diff --check` |
| 来源分类回归 | 28 项通过、1 项 skip | `artifacts/faithful-s07/classified-regression.log`；skip 未计通过 |
| 真实公共 Job 投影 | 尚待集成 | 协调者在集成树维护 `tests/test_faithful_graph_public_integration.py`；S07 工作树未接入 S05 的 `report.progress.proof_graph` 投影，此项不标为通过 |
| 最终工程门禁 | 未运行 | 由协调者在 S05、S07 集成并冻结源码后执行；本工作树不启动全仓长门禁 |

源码门禁 SHA 与最终文档交接 SHA 分开记录。此纵切未验证 Docker/Reference 覆盖、真实 provider、容量/SLA、自然题方法语义或数学效果，不据此声称能力提升。任何中止门禁都单独保留，不计通过。
