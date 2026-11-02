# RB04 产品结果语义

适用范围：spec #87、RB04 #91、ROB-AC-10/11。仅适用于显式 STAR 产品入口。

`solver.semantics` 是只读、增量、可版本化的产品投影，不是第二份数学账本。
Job 与 Run 的 `result.solver.semantics`、报告 `report.semantics`、Evidence 顶层及内嵌报告、终态 SSE `semantics` 和 RB01 runner 的 `semantics` 使用同一投影。旧快照无须迁移或外部派发；读取时从现有来源计算。

## 字段合同

版本为 `star-result-semantics-v1`。

| 字段 | 含义 |
| --- | --- |
| `execution` | 沿用现有 Run 生命周期：`queued`、`running`、`waiting_input`、`completed`、`needs_review`、`failed`、`canceled`。取消和执行失败优先于未结束的 Solver 进展。没有持久化产品终态时，按当前 Solver 进展投影。 |
| `transport` | `known` 表示已有调用结果可确定；`pending` 表示执行中的在途请求；`unknown` 表示未决远端结果；没有调用记录为 `unavailable`。旧未知调用即使已显式重试仍保留未知含义，不把未知费用改成零。 |
| `whole_review` | `accepted`、`rejected`、`not_reviewed`、`invalid_source`。依据实际整题记录及已完成调用，不依据报告徽章或角色顺序。 |
| `binding` | `same_artifact`、`artifact_changed`、`unbound`。文本改写可保留历史 ACCEPT，但当前文本不继承其绑定或完成资格。 |
| `formal_verification` | 当前固定 `not_verified`。LLM 审查、有限计算、局部候选检查均不是形式化证明。 |
| `verification_requirement` | 默认 `default`。`required` 模式为 `required_unmet`，保留原有额外验证门槛及 `verification_needs_review`，不会因 LLM 接受而完成。该字段不承诺形式化工具已经实现。 |

`completed` 还要求当前 Solver 已完成整题审查且绑定有效。旧 Run 状态声称完成但实际绑定已失效时，语义降为 `needs_review`。Job 保持既有枚举：例如需复核的 Run 仍可投影成 legacy Job `failed`；额外语义解释其原因，不修改既有控制合同。

## 来源与兼容

`solver_harness.final_binding.review_binding` 共同校验 Run、计划、attempt、候选版本、已完成 Verifier 调用、裁决和请求中的实际文本身份。交付绑定与 RB01 evaluator 复用此校验。RB01 继续独立核对捕获的 wire context、生成版本与步骤证明，`proof_delivered` 不因新增产品语义自动为真。

原 `verification.status=unknown` 与 `acceptance=needs_review` 表示数学证据等级，保持兼容。它们不表示传输未知，也不统一升级为 `pass`。`verification.binding` 仍表示最近一项 legacy 检查的文本绑定；`semantics.binding` 专指实际整题审查与当前交付文本的绑定。

追加局部检查仅追加原有 `history`，不改变审查账本。产品语义从实际整题来源重算，保留整题和局部两个范围。Workbench 沿用现有报告样式，明确展示五种含义及 required 门槛，并提供可展开的完整检查历史。无新字段的报告仍按旧徽章保守显示。

## 验证边界

`tests.test_star_product_semantics` 经认证公共 Job、Run、报告、Evidence、SSE 验证成功、真实 ReadTimeout、REJECT、伪造来源、改写、局部追加、required、运行中、取消和 deadline。提供方为受控 HTTP 回复；不证明真实模型效果。

前端 `tests/report-semantics.test.ts` 经现有 ReportSection 的实际 Vue SSR 渲染与报告 schema 验证文案、安全输出、历史范围和旧字段兼容。它不替代浏览器布局、依赖审计或真实模型验收；完整发布门禁归 RB08。
