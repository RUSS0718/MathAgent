# #127 历史自然多步线上运行：d6e9ea5-02（2026-11-04）

本记录只描述这一份独立冻结运行，不与其他源码或 manifest 合并。结论为已执行未通过；它早于 `handoffloose-02`，后者仍是当前最新有效 readiness Run。本次不评估数学正确性。

## 冻结身份与预算

- Manifest：`issue127-natural-20261104-d6e9ea5-02`；SHA-256 `e26a60a91c06cfbd1fcf847884f63058fb84680327ad24d44138dee417f253c0`。
- Run：`issue127-natural-20261104-d6e9ea5-02-run01`。
- 源码 revision：`d6e9ea58b6b53401dff527cc08d08b4e26323b26`；SHA-256 `189ec467feeb6b1bb29146df1a93cc9e5ad8723817a45be2e361cfb648984944`；归档标为 clean。
- 两个登记样本：`simple` 与自然多步 `vieta-equation`。模型 `intern-s2`，thinking=false，temperature=0.2，输出上限 32768，stream-first；单次请求 900 秒、流空闲 30 秒、Run 截止 3600 秒。best-effort 关闭，整题审查与交付绑定启用，usage 为 observe-only。
- Run 于北京时间 2026-11-04 21:00:03.854 左右启动，名义截止 22:00:03.854；进程于 21:02:29.662 退出，退出码 0。退出码 0 不代表 readiness 通过。

## 结果与独立核验

- Run 完成 1/2。简单题 Job `run_df1152dc2d8af3ef4491ab841b787de5` 成功，返回非空答案并通过整题审查及同文本绑定。
- 自然多步 Job `run_0e08c27aaf9f5d313233ae6b6f55259a` 以 `job_execution_failed` 失败。Solver 持久状态仍为 running，停在 `STEP_VERIFY` / revision 1520；没有最终答案、整题审查或最终文本绑定。
- 末个 researcher 正文首 token 为 21:02:05.404，末 token/活动为 21:02:12.415；该流没有 completion。完整登记分母仍为两题，多步路径 planned=1、audited=1、failed=1、path_completed=0。
- 独立核验为 `FAIL`：task/process_path=FAIL，coverage=UNKNOWN，transport=PASS（仅表明登记配置匹配），usage=UNKNOWN。未知请求没有在原 Run 内恢复或重发；#128 两臂没有派发。
- 归档状态文件与独立验证文件的 usage 计数覆盖范围不同：前者只累计已完成样本，后者按已派发账本统计。现有证据不足以把差异归因于计量错误；usage 保持 UNKNOWN，不标 PASS。

## 事务异常的证据边界

流生成器清理期间记录到 `sqlite3.OperationalError: cannot start a transaction within a transaction`，发生在 `RunBudgetLedger.settle()` 的 `BEGIN IMMEDIATE`。该日志证明清理阶段的账本结算失败，不能证明它是此前 Job 进入 `job_execution_failed` 的首发原因。

随后代码修复让失败的 workspace 进度事务回滚，并增加 `test_failed_progress_rolls_back_and_budget_can_settle` 与 `test_reader_contention_does_not_leave_a_nested_transaction`。两项离线回归通过，说明注入的进度写失败不会遗留连接事务；这不是旧 Run 的追溯性修复，也不证明 #127 已通过。最新 `handoffloose-02` 仍在 3600 秒 Run 截止处失败，见[该 Run 记录](provider-live-natural-20261104-handoffloose-02.md)。

不改官方 baseline，不启用 best-effort，不宣称数学能力提升。
