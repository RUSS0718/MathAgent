# SP-06 回退与重规划产品合同

日期：2026-10-23；基点 `bf74358`，责任 [#62](https://github.com/RUSS0718/MathAgent/issues/62) 的 SP-AC-09/10，承接父规格 #56。固定来源 SC-010..012、SC-035 / STAR AC-09..10、28..29；沿用现有 controller、Harness、S3 和 S4。

1. 从公共 Job HTTP 发起，在同一 Run 的实际出站请求、SSE、报告和 Evidence 验证合法 Trace-Back 的区间归档、传递依赖失效及独立已审查成果救援。未知依赖、候选、失效成果不得作为事实。回退增加 attempt，重新建立角色会话，原报告和失败历史保留。
2. 非法目标（缺失、布尔、未来步骤）由严格协议或控制器拒绝；不猜测目标，不重新执行步骤。Meta 结构裁定 APPROVE_REPLAN 才归档旧计划，生成和执行新版本。禁止方向、失败记录和合法复用成果进入实际 Planner/Reasoner 请求。
3. Meta 的 reusable_results 仅精确引用现存成果的 result_id 或 statement，不创造成果；受选成果仍须有效、已审查且依赖闭合，保持原证据等级。旧计划当前未被接受的步骤报告留在历史中，不能作为新计划事实。
4. 公开事件仅增加版本、attempt、区间序号和归档/失效/救援数量，不公开模型 argument、完整 prompt、内部步骤 ID 或禁止方向正文。Evidence 和报告沿用同一持久事件。

执行顺序：公共失败用例 → 最小实现 → 聚焦回归与依赖栅栏旁路敏感性 → 完整 offline → release。UI 全生命周期仍属 SP-12；此片使用现有时间线承载分类事件，无 UI 改动。传输层故障注入与 live 证据分开，官方冻结字节不变。

上游核对：固定 `5f2a86b` 的 `src/state.py::_collect_rescued_results` 从 VERIFIED 步骤的审查文件提取 Verified Results 文本；`orchestrator_failure.py` 将 Meta reusable_results 文本作为 rescued_results 返回。本项目明确采用更严格适配：引用已有成果、检查有效性和依赖，不直接信任新生成救援文本；不猜测非法目标。该差异不声称与上游逐字一致。
