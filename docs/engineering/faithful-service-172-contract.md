# #172 B2 必要澄清合同

范围：父规格 #168 的 B2；基点 `4b4ab9458c8ae587b6a61454496b3f406208e3a7`。仅显式 Faithful 自动规格路径，官方 baseline 不变。

公共边界：普通浏览器提交 → 已有 Job/Run → 必要问题 → 版本化回答 → 同任务求解及结果恢复。离线仅保留该 API 行为和冲突/到期/失效反例；真实 provider、缺尺寸三角形浏览器闭环及最终门禁由集成负责人验收，本切片标 `not_run`。

- intake 的可选 `clarification` 包含具体问题及必要性原因；能完整分情况回答的题目直接求解。服务固定请求身份、任务身份和输入版本。
- `POST /api/agent/jobs/<job_id>/clarifications/<request_id>` 接收 `task_id`、`input_version`、`answer` 和原有 Idempotency-Key。认证与 CSRF 复用现有入口。GET/SSE 只读。
- 回答作为该必要问题的用户条件写入同任务 ProblemSpec 新版本，保留原题；使用已有规格依赖失效机制撤销旧候选、审查和表达资格，重新进行推理和整题检查。
- 原预算、deadline、能力授权不变；重复相同回答重放，身份/版本或内容冲突拒绝。deadline 到期返回 `409 clarification_expired` 与 `answer_saved: true`，不继续派发；用户可显式 `POST` 同一路径的 `/new-task`，关联原任务、请求和输入版本。
- 其他任意改题/追加要求的新任务流程属于后续票；不把普通 resume 当作回答入口。

退出条件：聚焦 API 与前端回归通过，提交可审阅；真实功能验收、独立审查与完整门禁保持待执行。交接继续使用当前选择的同一模型，不变更模型配置。
