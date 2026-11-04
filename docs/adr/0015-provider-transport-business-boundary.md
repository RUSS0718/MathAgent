# ADR-0015：业务回复协议与 provider 传输准入分离

状态：accepted。日期：2026-11-04。依据：用户要求降低 role 交接耦合，并优先验证线上交付。

业务 response schema 当前只写入文本 prompt，没有作为 provider 的结构化输出参数发送。此前把该 schema 指纹和消息条数列入流式白名单，使合法的 Meta action 在出网前被拒绝。

生产流式准入收敛为一个 transport profile，只绑定端点、模型、thinking、temperature、输出上限和实际 payload 字段。消息仍须为合法文本 chat；业务 role、action、prompt 内容、消息条数及业务回复 schema 不参与该传输身份。受控测试夹具保留其显式形状匹配。

各 role 的业务结果继续由原业务校验器处理。整题审查、最终文本绑定、工具隔离、硬预算、未知请求停止与禁止静默降级保持原合同。不新增统一外层响应封装，也不接入官方 baseline。

新源码使用新 manifest、profile 指纹和 Run 身份。旧登记、旧失败及旧证据保持原样；新 profile 不追溯升级历史运行的结论。
