# #102 离线诊断 Runner 合同

状态：实施合同；Refs: #102。基点 dc9dc807314ad3fe27373e9a5111fdf3dcc6752a，复用 #98 已验收的 S3。

## 范围与接缝

用户已确认公共 call / Job / CLI 接缝。本票分别测试 `freeze` / `dry_run` 的准入、
`DiagnosticJob.run/cancel/reconcile` 的持久化状态，以及 CLI 的四个显式子命令和只读 `monitor`。
这些测试覆盖诊断控制合同，不声称完整 STAR 或 provider 兼容。本票没有真实派发接口，fake 禁止所有 socket。

1. 冻结独立计划与题目/臂的 run、session、workspace、ledger 身份。
   验证：源码/runner/upstream、题面/prompt/schema、参数/seed/window/budget/stop 均绑定摘要；过长输入原样拒绝。
2. 用独立 registry 独占消费；每个 Run 复用 S3 的一逻辑/一 HTTP/零工具账本。
   验证：跨 archive/并发启动仅一方成功；取消/退出/unknown 停全批；原 attempt/deadline/预留保留；迟到仅结算一次。
3. 只读快照与显式 CLI、脱敏归档。
   验证：缺失计量 unavailable，WAL 一致读取，不创建 DB、不修复、不派发；日志不含输入或回复。

## 上限（核对本机已验证的 #103–#107 正文）

| 阶段 | 请求 | charged/reserved | 总等待秒 | 批次秒 | 单次秒 |
| --- | ---: | ---: | ---: | ---: | --- |
| P | 36 | 2359296 | 32400 | 36000 | 900；首3次在36内 |
| O | 3 | 196608 | 5400 | 7200 | 1800；900仅影子观察 |
| T | 24 | 1572864 | 32400 | 36000 | 900/1800 |
| T-3600 | 4 | 262144 | 14400 | 16200 | 3600；条件分支 |
| R | 16 | 1048576 | 28800 | 32400 | 明确冻结，最多1800 |
| S | 8 | 524288 | 14400 | 16200 | 1800；条件分支 |

每请求 max charged/reserved=65536、logical=1、HTTP=1、tools=0；intern-s2、thinking=true、temperature=0.2、max_tokens=16384、retry=1。
输入估算沿用 S3 的 UTF-8 字节口径，不能解释为实际 provider 费用。charged 已包含 reserved，不二次相加。

## 恢复和保密边界

registry 放在 Git common-dir 下，跨 worktree/archive 共用；以登记身份及摘要独占消费。
P 首3个控制请求与其余最多33个冻结在同一登记内；`run(limit=3)` 可在控制块边界停下，
`continue_remaining` 仅沿原 archive/manifest/Run 列表继续。公开结果引用保留原 attempt 与内容摘要，
累计额度来自同一组 S3 账本；不复制成新 P 的36个请求。dry-run 显示36包含3，而非39。
在途或未知 registry 阻止新批次；重启仅投影原批次，不恢复派发。迟到显式对账不解除批次暂停或自动执行后续阶段。
SQLite 中保存调度 intent 及 S3；intent 有而 HTTP 未落账时按全 envelope 保留，无法确认计量时不报零。
源码身份包括 runner 及全部 tracked/untracked Python 源码、依赖文件（排除 tests/test.md、缓存与产物）。
manifest 只含 hash 和受限元数据；题面、prompt、完整可见回复和答案在 ignored artifacts 私有目录；不保存隐藏推理。
PID、OS进程创建时间、stdout/stderr 路径写入运行记录；PID 不代表远端状态。monitor 只读 SQLite，不能使用 immutable=1。
生产者在终态/控制边界 checkpoint 并切换 DELETE 后关闭；P 续接由生产者恢复 WAL。
monitor 每次使用独立短子进程、`mode=ro&readonly_shm=1`、query_only 和单一读事务，
避免复用当前进程 writer 的可写 SHM 映射。WAL 缺少既有 WAL/SHM 时返回 unavailable，不初始化或修复。
监控子进程最多等待5秒，SQLite 锁等待0.2秒；锁冲突或子进程失败保守返回 unavailable。
本票不启动长批次或 heartbeat；完整组合门禁由主聊天协调，skip 不计通过。
