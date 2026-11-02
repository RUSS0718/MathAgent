# SP-11 候选历史与零调用选择合同

状态：accepted implementation contract；基点 871f709，关联 #56/#67。

## 范围与接缝

复用既有 candidates、best_effort、replay 和 STAR Job 循环。主接缝为认证后的 Job 创建/查询、报告、Run Evidence 和只读候选 replay；真实 HTTP Adapter 出站数为调用证据。官方冻结路径不变。完整 star_reference/star_best_effort 仍由 SP-12/13 门禁拒绝。显式 star_limited_best_effort 准确标识受限 Best-Effort；它使用服务器可信配置，不接收客户端 feature patch。

## 验收步骤

1. 公共 Job 选择受限 Best-Effort，在 Explore 用完硬调用预算。
   → 验证：候选追加版本和实际交付一致；出站数等于预算；零额外 Verifier/工具；S4 记录选择来源、理由和定性等级。
2. 相同 Job 重复读取、重开服务并重放。
   → 验证：历史/版本/决定不变，快照 hash 与决定一致，不产生调用；只输出公开白名单，正式 export_result 仍仅 final_response。
3. Step/Final 全版本审查与回退、冲突、无候选。
   → 验证：实际审查对象对应候选；失效依赖不可选；同级冲突保留；无候选给非空未解决说明。通过最小故障注入证明栅栏可识别旁路。

## 事实边界

测试证据标 fault_injection/replay，不代表 live 数学效果。候选等级为启发式审查/有限计算证据，不输出概率，不称 LLM 意见为独立证明。完整模式以及前端生命周期与真实发布证据仍分别属于 SP-12/SP-13。
