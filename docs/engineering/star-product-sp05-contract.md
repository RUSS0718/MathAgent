# SP-05 连续 Challenge 产品合同

日期：2026-10-23。父规格[#56](https://github.com/RUSS0718/MathAgent/issues/56)，本票[#61](https://github.com/RUSS0718/MathAgent/issues/61)，责任SP-AC-08；固定来源映射SC-009 / STAR AC-07..08见[来源审计](../experiments/star-product-source-audit.md)。沿用既有Harness、Job/S3和controller，不新增执行循环。

公共接缝为认证Job HTTP、Run查询、SSE、报告和Evidence。传输层有限回复标为fault_injection；实际出站请求、公开事件与结果分别断言。

1. 同一步连续三轮Challenge，每轮Reasoner收到此前双方历史和当前异议，Verifier收到本轮答复和完整历史；请求携带最新权威状态版本。双Gate合法ACCEPT才接受一次，随后最终生成和新整题审查。
2. 产品配置最多三轮Challenge，Harness硬上限五轮。同一步、计划版本和attempt最多一次Meta升级。CONTINUE保留历史并以新调用身份执行一次步骤及审查；再次CHALLENGE不重置轮数、不二次Meta升级，明确停止。ABORT终止。共享S3预算和deadline继续负责动作准入。
3. 非法Meta ACCEPT由严格角色schema拒绝，既有call audit保留interrupted和失败Job，不自动重试；合法schema中非法回退目标记录meta_invalid，以partial_aborted停止。均不接受步骤、不派发后续求解。
4. SSE增量字段限定角色、轮数、分类升级原因、提供方用量及最多500字符脱敏异议摘要。不复制Reasoner argument、完整prompt或Meta推理文本。异议为供用户阅读的Verifier输出；模型应仅返回可公开摘要。保留既有plan ordinal、事件/调用伪名化和准确模式身份。

验证：公共Job和既有Challenge/Meta聚焦回归；前端类型、单元、构建和四视口浏览器/Axe；完整offline与发布检查顺序执行。公共断言必须识别历史丢失、绕过Verifier或重置轮数。官方冻结路径保持字节稳定。结果与局限见[实际验收记录](../evals/star-product-sp05.md)。
