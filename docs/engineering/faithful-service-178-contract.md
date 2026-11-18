# #178 自然题受限形式目标接线合同

## 设计与任务

仅修改显式 Showcase 后端；官方 baseline 不变。普通输入复用原任务已计账的 problem_intake 调用，可选返回 formalization={status,reason,require_formal,obligation_ids,target}；status 为 proposed/unsupported/not_selected，target 使用 S09 单变量有理多项式全称等式结构。严格数学证明不等于机器要求；只有明确要求 Lean/机器验证时 require_formal=true，不支持时也必须保留要求。

服务器保存候选选择及原题/规格来源，source={problem_hash,specification_hash,obligation_ids,generation_call_id}，hash 为 experiment_manifest.canonical_json 的 SHA256。定义域、量词、假设和原题保留于完整 ProblemSpec，目标不可通过抹去条件扩域；受限后端拒绝非有理域、额外假设、多变量或非全称等式。

执行前基于服务器 formal_server_policy 冻结 policy，原子写入 Solver 与当前 workspace Job identity，已有 policy 不覆盖。客户端不能提交 source 或审批声明；requirement 仅表达要求，不提供审批权限。普通输入不需要手填 policy。

生成、S09 独立对应审核、Lean 执行分责；生成不授予等级，固定模板之外最多真实 L2、对应 not_reviewed，不能伪造 L3。执行仍走原工具预算和截止时间，unknown 不自动重发。execute_reserved_attempt 使用 current spec 调用共享 assess_formal_requirement 并持久/公开 assessment；恢复 unknown 清除旧 assessment。required unmet 将 pipeline 产品结果降为 NEEDS_REVIEW/formal_requirement_unmet，保留答案。

## 代表案例与验证方式

- 自然题全称有理多项式等式：intake 持久候选及来源，原调用数不增加；服务器配置后沿现有 formal 块执行。真实 Lean 和公共 UI 闭环由主 agent 验收，未执行保持 not_run。
- 实数解枚举或额外假设：保留规格、unsupported 原因；明确机器要求保留 require_formal，不退化成普通完成。
- “严格证明”没有机器要求：require_formal=false，形式化可选失败不抹去答案。
- 局部已验证 L2 或仅 solved/grade 没有有效来源：共享 evaluator 判定整题要求 unmet；不得冒充整题 L3。
- 刷新/恢复：复用冻结身份与候选；dispatched 恢复 unknown，旧 met 不得保留。

先保存最小失败见证至 `artifacts/issue-178/`，再做最小实现及聚焦回归。阶段退出依[工程门禁](development-gates.md)集中双轴审查、修复复核、冻结源码门禁，并依[接续合同](unattended-ticket-loop.md)提交推送和交接。真实能力结论以验收记录为准。

## 最终退出口径（2026-11-14）

Issue要求真实Lean及准确范围，没有要求自然题必须达到L3。初始运行脚本额外要求L3且答案匹配过窄；原失败保持不变。按接续合同取消额外L3成功门槛，保留真实L2、正确答案、来源、范围与只读恢复；live03已取得真实内核L2及正确恒等式答案，独立复核见[验收记录](../evals/faithful-service-178-20261114.md)。一般原题对应L3及自然明确机器要求正向成功仍未实证，留#183，不降低任何回执或整体满足判定。最终f008420门禁6/6通过，2087项、49 skip、源码无漂移；原gate-01失败及fixture修复保留。
