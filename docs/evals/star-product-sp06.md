# SP-06 回退与重规划产品验收

日期：2026-10-23。本票 [#62](https://github.com/RUSS0718/MathAgent/issues/62)，父规格 [#56](https://github.com/RUSS0718/MathAgent/issues/56)，覆盖 SP-AC-09/10；见[验收合同](../engineering/star-product-sp06-contract.md)。这些证据证明工程控制行为，不证明数学正确率提升。

## 同一 Run 证据链

`tests/test_star_product_traceback.py` 从认证 Job HTTP 入口穿过真实 STAR controller、InternModelAdapter、S3 账本和持久 Solver 状态。仅 HTTP 传输注入有限回复，Evidence 明确标注 `fault_injection`；没有 live 调用，也不是 replay。运行预算上限为模型调用 28 次、HTTP attempt 28 次。

| 触发 → 决策 | 实际动作 → 持久状态 → 用户结果 |
| --- | --- |
| 第四步 Verifier TRACE_BACK 到第二步 | 同 Run 归档第二至第四步，错误及依赖成果失效，只救援独立已审查成果；attempt 增加、Reasoner 会话与调用身份更新，实际重做第二步。Job 最终成功，SSE 和 Evidence 保留区间及数量。 |
| 重试后 PROPOSE_REPLAN → Meta APPROVE_REPLAN | 实际派发新版 Planner，携带禁止方向、两次失败历史及合法复用事实；旧计划与失败报告留档，新计划版本为 2，Reasoner 实际执行新目标。Meta 提到的失效事实及凭空定理均不能进入事实字段。 |
| Verifier 目标缺失、布尔或未来步骤 | 严格协议拒绝，Job 失败；只有初始 Reasoner 请求，没有猜测目标、重试步骤或接受事件。 |

公开事件只增加版本、attempt、步骤序号及归档/失效/救援数量；公共测试断言私有 argument、旧错误事实、候选文本不进入 SSE。报告与 Evidence 关联原 Run，Evidence timeline 复用持久事件。

所属 `solve/get_run` 回归还证明：缺少来源/ID 的坏成果也被失效；同来源中失效成果不能借安全成果恢复其模糊来源依赖，但精确依赖安全 result_id 的成果保留原证据等级。两项反例均先观察失败，再做最小修复。正常 Verifier 接受路径始终生成步骤来源；无来源案例验证坏持久状态的失败关闭。

## 上游核对与适配

固定本地上游 SHA 为 `5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d`。`src/state.py:637` 从 VERIFIED 步骤的审查文件提取 Verified Results，并带计划/步骤来源；`src/orchestrator_mixins/orchestrator_failure.py:122` 将 Meta 的 reusable_results 文本作为 rescued_results 返回。项目采用更严格的结构化成果引用：Meta 只能选取现有有效且已审查成果，检查依赖闭合并保留证据等级，不能新创救援定理。非法目标不猜测。这是有意适配，不声称与上游逐字一致。

## 实际检查

| 检查 | 结果 |
| --- | --- |
| 公共回退、重规划及所属 traceback/replan/sessions/candidates/Challenge/Meta 回归 | PASS，40 项，23.941 秒。 |
| 进程内最小 mutation 探针 | PASS：恢复回退前事实、重规划重新注入失效事实，两个公共验收均因事实字段错误而断言失败。无持久源码 mutation。 |
| 修改 Python 文件 `uv run ruff check`；`git diff --check` | PASS。 |
| `uv run python scripts/check.py --offline` | PASS，408 项，340.549 秒，9 项跳过；`repository_check=PASS`。 |
| `uv run python scripts/check_showcase_release.py` | PASS，在 offline 结束后顺序执行；`showcase_release=PASS`。 |
| 官方冻结文件差异 | `BASELINE.json`、`user_agent.py`、`implementations/`、`requirements.txt` 空差异。 |

日志及临时 mutation 探针保留在忽略的 `artifacts/star-sp06/`。提交前 `git merge --no-edit showcase-star-product` 返回 Already up to date，已包含集成基点 `bf74358`。

## 边界与下一切片

本片没有前端代码变化，使用现有时间线承载事件；全生命周期 UI 属 SP-12。记忆、Skill、研究委派和 MetaGuidance 属 SP-07，安全恢复属 SP-08，真实 Intern 批次和最终来源/综合发布审查属 SP-13。完整 reference 仍拒绝启动；官方默认入口、调用预算和输出合同不变。故障注入不能替代 live 能力验收。
