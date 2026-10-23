# SP-03 共享账本与控制合同

状态：共享控制实现与本票离线工程验收通过。父规格[#56](https://github.com/RUSS0718/MathAgent/issues/56)，本票[#59](https://github.com/RUSS0718/MathAgent/issues/59)。继承[ADR-0014](../adr/0014-star-product-state-and-recovery.md)及[执行合同](star-product-execution.md)。本票不关闭完整参考模式的恢复、隔离和最终Evidence验收缺口。

## 唯一权威与接缝

Job/Run保持同一ID，STAR始终在Workspace既有S3 budget/control绑定内执行。InternModelAdapter只预留一次logical调用；InternChatClient每次真实HTTP attempt分别准入/结算，retry不重复logical；Registry只预留一次工具。Harness counters保存数学活动，产品资源预检使用原S3快照、limits和deadline。独立Harness保持原API及离线默认预算。

数学状态CAS在同一SQLite BEGIN IMMEDIATE中检查Job和原deadline，与取消写入串行化。取消/截止后拒绝新的数学接受、计划或候选推进；迟到call_audit仅能更新calls，不改数学status/phase。HTTP usage照常结算，unknown费用不推断为零。数学提交才发现deadline到期时，worker投影failed及checkpoint终态。

公共测试接缝为认证Job创建/查询/取消、同ID Run、SSE、report及Evidence；真实STAR Harness/controller/Adapter/Registry，提供方仅替换为有限scripted HTTP。实际出站与handler独立计数，不用helper PASS或私有SQL验收。

## 可信服务端配置

`SHOWCASE_STAR_BUDGET`接受`RunBudgetLimits`，原limits/deadline一经创建不由恢复配置覆盖。`SHOWCASE_STAR_FEATURES`只接受已有机制布尔白名单，不能关闭基础star_routing/persistent_sessions/stream_recovery。`SHOWCASE_STAR_REGISTRY`仅接受真实ToolRegistry，当前计算权限限polynomial_check；不启用生成Python。HTTP `solver_options`仍拒绝，完整reference/best_effort仍因独立门槛拒绝启动。

默认保持三调用受限配置。按需启用已有final_generation/final_solution_review/local_code_tool/reexplore_after_replan/skills路径；Meta及research复用同一个InternModelPort。桥接通过既有controller.advance推进，最多64次，终态、interrupted或无revision变化立即退出；不是独立测试求解器，也不是SP-08阶段恢复。SP-04/07仍负责机制语义与完整验收。

## 验证顺序与退出

每片先公共失败反例，再最小修改，聚焦与相关回归通过后提交。验收包括retry的1logical/2attempt、token预留拒绝、工具线程同账本、cancel后的数学提交、截止窗口、迟到usage、Meta/异步research共享额度及旁路敏感性。工具precheck和Registry handler两个线程入口均复制原ContextVar；不创建新账本。

调用链新增`solver_call_id`关联Harness动作与S3 logical/HTTP attempt，公开报告只暴露经白名单处理的身份。Run查询可读真实Solver脱敏phase/status/revision，避免Job终态投影掩盖迟到数学写入；不导出prompt或原始回复。

纯推理状态不因配置中仍列出工具而误判工具超额；真实MetaGuidance切换的公共触发与纯推理请求注入由SP-07验收，本票不能以修改predicate称为完整切换已通过。已授权工具真正用尽后仍硬终止，不能静默把工具缺失当完整模式。

实际证据、敏感性结果与未覆盖项见[SP-03验证记录](../evals/star-product-sp03.md)。官方冻结文件、依赖和默认入口保持不变。
