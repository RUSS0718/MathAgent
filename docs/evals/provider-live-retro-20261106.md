# Provider-live 会话复盘（2026-11-06）

readiness-31 已终态：自然题计划 6 步，前 5 步已审查（2 ACCEPTED、3 REVIEWED）；第 6 步 Verifier 流中 connectivity 中断。17 次模型/HTTP、2 次工具；运行耗时 1,265.61/28,800 秒、本地预留 1,046,223/67,108,864 tokens，预算充足。1 个请求未决，usage UNKNOWN；最终生成、整题审查和同文本绑定未运行。不能把它归为预算耗尽或已完成交付。[31 记录](provider-live-natural-20261106-readiness-31.md)

**已修复或已有防护。** 30 前已对同 scope 的重复历史前缀做精确去重，保留当前草稿和持久记录；旧请求重放从 836,145 降到 217,684 bytes，但这不是 provider token 或上下文上限测量。[上下文研究](../research/star-context-memory-paper-20261106.md)记录了 Intern 直连路径没有自动 compaction 的证据边界。完整 provider finish error 已在 JSON 解析前分类终止；格式 repair 只针对完整 stop 后的非法 JSON，不完整流保持 UNKNOWN。CI 已有 pre-commit、fast、完整离线和 release 检查；不属于常规检查缺失。

## 后续候选（按严重程度）

1. **高：归档状态一致性。** 本地 cycle.json 标记31已归档，却残留旧运行字段，如13次调用、旧错误类别和 next_run=29；与31正式记录的17次调用和 connectivity UNKNOWN 不一致。下一次归档时只需核对并更新终态摘要，明确旧字段所属 Run，防止把历史状态当成当前状态。
2. **中：保留传输终因证据。** 31 的 connectivity 子因未确认，30 则是单调用截止，且非 Run 总预算耗尽。若后续获授权运行，可在现有脱敏记录中保留异常类别、流是否有正文及 completion 标志；未知请求继续标 UNKNOWN，不据此重发或加预算。
3. **低：减少每批脚本复制并统一长测观察。** 30/31 的 ignored .review 目录各有硬编码路径的 monitor.ps1。仓库已有长测试单进程、状态阶段/完成计数、PID/开始时间/日志及30分钟静默检查约定；31 也核对了真实 runner/service 的 PID 与创建时间，排除了包装进程身份。未来若继续多批次，可复用带 Run 参数的只读监控入口；无需新增框架。状态汇报应分别列样本分母、已审查步骤、调用/工具执行和未决请求，避免把回执数或计划步数当成完成数。

本轮精简了 AGENTS.md，没有新增检查、框架或产品改动；未发请求、未运行测试。参考：[迭代审计](provider-live-iteration-audit-20261106.md)、[工程门禁](../engineering/development-gates.md)、[30 记录](provider-live-natural-20261106-readiness-30.md)。

## 全仓文本治理

已精简根 AGENTS.md：移除长篇固定阶段清单和对小型维护一刀切的材料要求，保留产品实现前的 PRD/设计/任务/验收约束及切片验证纪律；把旧实验文档禁令收窄到不应提交的原始题集、运行 raw 和废弃脚本。修正裸 python 命令，并把检查、环境与提交细节收敛到现有规范文档。

未删除其他 Markdown 或文本文件：依赖清单仍是运行入口，未自动链接的评测/合同材料保留独立历史或约束证据；本次精确内容扫描未发现重复文件。忽略目录中的 pytest 缓存不是项目文档，未清理。用户保留的 tests/test.md 未读取、未改动。
