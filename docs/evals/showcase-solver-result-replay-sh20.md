# Solver Harness 结果导出与离线重放

**状态：** engineering-preview。对应 [SH20 / #52](https://github.com/RUSS0718/MathAgent/issues/52)。

## 结果导出

`showcase.solver_harness.export_result(snapshot)` 接受 `SolverHarness.solve()` / `get_run()` 的完整返回值，或其中的 `state`，返回且仅返回 `{"final_response": str}`。

答案保留已有脱敏边界。缺少答案或答案为空时返回非空未解说明。内部 `best_effort_decision`、证据等级、候选冲突、排除原因和未知用量不会进入导出结果。该适配器只供显式 Showcase 调用；官方 `user_agent.py` 不导入它。

## 离线重放

```python
from showcase.solver_harness import export_result, replay_snapshot

snapshot = harness.get_run(run_id)
formal_result = export_result(snapshot)
audit = replay_snapshot(snapshot)
assert audit == replay_snapshot(snapshot["state"], snapshot["events"])
```

`replay_snapshot(snapshot, events=None)` 使用候选登记、步骤状态、证据回执和事件重新执行当前纯 Python 选择与证据分级规则。函数不修改输入，不读取数据库，不调用模型、Verifier 或工具。原运行不必启用 Best-Effort；没有候选时返回 `no_eligible_candidate`。

返回值包含完整内部 `decision` 和 `audit`：

- `snapshot_hash`：状态与事件的排序键紧凑 JSON 的 UTF-8 SHA-256；JSON 禁止 NaN。
- `selection_rule_version`：当前重放规则版本。
- `recorded_selection_rule_version`：快照中原有决策的规则版本；无决策时为 `None`。
- `matches_persisted_decision`：重算决策是否完整等于原决策；无原决策时为 `None`。

事件的 `run_id` 必须与状态一致。状态和事件分别传入时，其哈希与等价完整快照一致。哈希检测输入差异，不提供签名认证；若规则版本变化，重放可报告与原决策不同。数学正确性仍取决于原有审查与证据，重放不会增加数学证据。
