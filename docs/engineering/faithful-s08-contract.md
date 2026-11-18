# S08/F2 串行路线与 APRS 合同

日期：2026-11-08。适用范围：Showcase/STAR 显式 `serial_routes` Run；依据 #148 与 accepted implement-spec F2。本合同只覆盖串行路线，不代表完整并发 Population/APRS 或数学能力提升。

## 接口与所有权

- `routes.py` 以冻结 ProblemSpec、绑定 WorkUnit、当前有效证据和 ProofGraph 版本计算规范化 frontier 与 CandidateRoute lineage。frontier 不读取步骤 ID、标题或自由文本；只使用规范化根义务/其冻结前提与受控方法 ID。
- `aprs.py` 是纯确定性 Rater/Pareto/APRS：当前有效根义务/规格前提信用、结构化路线新颖性、可知的真实预算计量、硬门禁、固定平局键及 replay hash。未知成本保留为 unknown，不按零处理。
- `controller.py` 在 Planner 派发前消费 S04 当前停滞与共享预算门禁；`replan.py` 在生成替代计划后、`plan_replaced` CAS 前调用 `validate_route_frontier`。主路线停滞后至多一条替代路线；非法/重复 frontier 不进入 STEP_EXECUTE。
- `serial_routes` 由受信任服务配置显式关闭为默认；Run 初始化冻结 `schema_version` 与 `policy_version`。路线派生状态只允许 SolverStateStore 同事务/CAS 提交，普通 `state_updates` 不能伪造策略、lineage、评价或决策。
- SQLite 保留路线版本与决策事件。ProofGraph 版本变化原子标记关联路线需重评，旧路线/评价留存但不能继续作为当前有效候选。
- 公开进度只投影 `route_id`、父 ID、类别/状态、frontier digest、策略版本、有限停止原因码、Pareto/选择 ID 与 replay 状态。不得投影 frontier 文本、引理/证明内容、完整 prompt、调用凭证或个人信息。
- 前端只新增独立 `RoutePanel` 与专属 browser fixture；RunReview 集成由协调者/A 线消费此组件，不修改 RunReview 或 S06 输出组件。

## 退出验收

专属失败/公共 Job 验收覆盖：改名/改写/细拆/无关引理不能改变结构化 frontier 或证据信用；根义务与必要前提仅按当前有效证据计分；真实 token/调用/工具/时间成本越低越优，unknown 不插补；主路线未满足 S04 停滞及预算/收尾预留门禁时不得派发替代 Planner；重复 frontier 在执行前拒绝；CAS/重启/replay/旧 Run/default-off/图失效均可复核；RoutePanel 真实浏览器查看与隐私白名单通过。

路线停止后仍由既有独立 AnswerCandidate、整题审查与 exact-text binding 负责答案。产品/公共 Job、存储 CAS 与浏览器验收未通过前，本阶段保持 incomplete。
