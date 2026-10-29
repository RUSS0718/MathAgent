# #100 纯序列化修复候选验收

日期：2026-10-29，Asia/Shanghai；本机日志的 UTC 时间单独保存。范围为离线工程候选，不是 provider-live 或数学能力验收。实施合同见 [修复合同](../engineering/star-format-repair-100-contract.md)。

## 源码与提交

工作树 `star-format-repair-100/Challenge-Cup-2026`，分支 `feat/showcase-format-repair-100`。初始干净，先 `git merge --ff-only showcase-star-timeout`，实际集成基点为 `dc9dc807314ad3fe27373e9a5111fdf3dcc6752a`。完成前再合并集成 tip，未使用 reset。

| 提交 | 结果 |
| --- | --- |
| `7273fd9` | 受限可见回复、字节引用与全字段保真校验 |
| `0e4b979` | 原 Run 账本、持久一次额度、显式 opt-in 与旧重问隔离 |
| `790b88c` | 审查来源绑定、本地处理截止、F05/F06/F08/F10 与子进程恢复 |
| `13fa95bd1457498c431a97610b07a0a5f23d0757` | 并发陈旧快照只能有一个额度领取者；最终代码验收源 |

## 实际行为与共享接缝

服务端受信任配置 `SHOWCASE_STAR_FEATURES={"serialization_repair": True}` 启用受限模式候选；完整模式可在保留核心开关的 `SHOWCASE_STAR_FULL_FEATURES` 中增加同名开关。默认关闭，不增加默认预算。Standalone Harness 还要求 `stream_recovery=True`、显式私有回复目录及已有 Run 预算。开关开启后强制 strict completion，并阻断旧同角色重问与 Planner 的结构重问。

仅完整可见回复进入候选。可证明子集是严格角色对象或包裹它的单个完整 JSON fence；仅修复外层序列化。实际数学字符串、证明、代码、参数和可选字段全部比较，不能通过删除字段、改变内容或自述“已保真”取得成功。修复子集拒绝重复键、浮点数字、非法转义、缺失原值、schema 回显、多个工具提议、伪造回执/verified 标签。正常严格 JSON 仍交由原角色流程处理。

完整坏回复保存在数据库旁的 `restricted-protocol-replies/`，与工具下载目录分开。原始 UTF-8 字节引用绑定 Run、problem hash、role、call 与 SHA-256；Windows 当前用户/SYSTEM 的受保护 DACL 已实际设置并复核。公开审计无原文、片段或流式半成品；原文无法经工具 artifact 下载。保留期跟随本地工作区，由管理员离线清理目录；不承诺断电持久性。

每个请求根通过持久 `serialization_repairs` 与独立领取身份消费一次额度，之后使用新的 `:serialization-1` 调用身份。领取失败、修复失败、进程退出、普通恢复或并发请求均不重置额度。模型/HTTP/token 继续走同一 Run 的 S3 账本及原 deadline。unknown 零自动重发，保留原 attempt 与预留。私有读写与校验使用 #98 的有界本地处理接缝，迟到工作仅可留存私有证据，不改数学状态。

新增模块：`restricted_replies.py`、`serialization_values.py`、`serialization_port.py`、`serialization_repair.py`。必要共享接线如下，供集成审查：

- `calls.py`：失败引用、抑制公开片段、调用修复候选。
- `intern_port.py`：完整可见文本留存、严格解码与候选相等校验。
- `harness.py`：开关约束、problem hash、strict completion、修复工具权限为空。
- `protocol_repair.py`、`plan_generation.py`：关闭旧重问并解析新的完成调用谱系。
- `star_product_config.py`、`star_product_pipeline.py`：受信任开关和独立私有目录。

未修改传输重试、#101 恢复控制器、#102 诊断模块、官方 baseline、默认调用/令牌预算、历史消耗登记或运行时依赖。

## 红绿证据

每条命令均以 `uv run python -m unittest` 执行；最终本票完整模块覆盖这些绿例。

| 红例命令后缀 | 实际失败 | 绿例行为 |
| --- | --- | --- |
| `tests.test_format_repair_port_100` | 构造器不接受 `restricted_reply_dir` | 完整长证明受限留存且同值返回 |
| `tests.test_format_repair_job_100` | `star_features_invalid` | opt-in Job 新 logical/HTTP 调用计入原 Run |
| `tests.test_format_repair_port_100.FormatRepairPortTest.test_f10_foreign_run_reference_is_rejected_before_http` | 泄出普通 `ValueError` | 安全拒绝，无新 HTTP |
| `tests.test_format_repair_job_100.FormatRepairJobTest.test_f05_all_owning_roles_consume_the_same_public_repair_path` | whole_solution_verifier 绑定仍指向失败调用 | 六个角色同值修复完成，审查绑定有效 |
| `tests.test_format_repair_port_100.FormatRepairPortTest.test_f08_blocked_private_write_returns_by_deadline_without_repair` | 私有 fsync 阻塞调用者 | 原截止内返回，无新修复/数学动作 |
| `tests.test_format_repair_port_100.FormatRepairPortTest.test_f06_f10_ambiguous_or_semantically_illegal_original_is_ineligible` | 浮点参数被误判为可证明 | 拒绝舍入可能合并原值的修复 |
| `tests.test_format_repair_claim_100` | 两个旧快照取得两次领取通知 | 独立 claim 身份使竞争者失败，只有一次派发 |

## 冻结检查

两次检查均核对结束 HEAD 与开始相同、工作树干净，全部命令退出 0，零 skip、零 expected-failure。Docker 实际预检为 `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d linux/amd64`，设置 `MATHAGENT_TEST_PYTHON_IMAGE` 与 `RUN_STAR_READINESS_DOCKER_INTEGRATION=1` 后运行，不以跳过替代隔离验证。

第一轮 `790b88c`：`artifacts/issue-100-validation/{launch.json,results.json,00.log..12.log}`，验证进程 PID 11932，UTC 创建时间 `2026-10-28T18:28:47.474607+00:00`，`VALIDATION=PASS`。

- 本票 18 项：`uv run python -m unittest discover -s tests -p 'test_format_repair_*100.py'`。
- Harness 全模块 180 项：`uv run python -m unittest discover -s tests -p 'test_solver_harness_*.py'`。
- 产品、#98、预算和 baseline 的 23 个完整相关模块共 169 项。完整模块名/实际子命令见该轮 `launch.json`；包括 `test_star_product_recovery`、`test_star_product_streaming_recovery`、`test_star_product_protocol_failure`、`test_star_product_final_binding`、工具/控制/预算/审查、deadline/unknown/迟到/派发回归。

第二轮最终代码 `13fa95b`：`artifacts/issue-100-final/{launch.json,results.json,00.log..11.log}`，进程 PID 2508，UTC 创建时间 `2026-10-28T18:36:05.336508+00:00`，`VALIDATION=PASS`。并发修复后复跑受影响集合：

```powershell
uv run python -m unittest discover -s tests -p 'test_format_repair_*100.py'
uv run python -m unittest tests.test_star_product_protocol_failure tests.test_star_product_final_binding tests.test_solver_harness_streaming tests.test_solver_harness_sessions tests.test_run_budget tests.test_star_strict_98 tests.test_star_job_unknown_98
```

分别 19 项（33.953 秒）和 64 项（57.406 秒）通过。两轮测试数属于不同源码阶段且有交集，不相加为唯一用例数。

两轮还通过：

- `uv run python -m tests.star_protocol_failure_mutations` 与 `uv run python -m tests.star_recovery_mutations`：六个旁路均被公共验收拒绝。
- 修改文件的 `uv run ruff check <本票全部 Python 路径>`；`uv run python scripts/check_test_seams.py`。
- `uv run python -c "from scripts.check_showcase_release import check_baseline; check_baseline()"`。
- `uv run python demo_server.py --help`、`uv run python showcase_server.py --help`。
- `uv run python scripts/run_solver_intern_live.py`（无 `--live`，not_run、0 HTTP）及 `uv run python scripts/run_solver_pair.py --pair-id format-repair-100-offline`（纯 scripted）。

全仓 `uv run ruff check .` 仍报告 25 个既存问题，涉及 16 个未改文件，与本票路径无交集；未顺手修复，不能声称全仓 Ruff 通过。

## 验收映射与限制

| 条件 | 受控结论 / 用例 |
| --- | --- |
| F05 | `test_format_repair_port_100` 与 `test_format_repair_job_100`：完整长证明、代码/参数/转义、六角色接线、同 Run logical/HTTP 及用量、审查绑定、私有字节与公开投影 |
| F06 | Port/Job 拒绝空、length、半截 JSON、schema 回显及缺少可证原值；没有格式修复派发 |
| F08 | 取消、预算、原 deadline、阻塞私有 I/O、并发恢复拒绝、陈旧快照竞争、无工具权限；`test_format_repair_restart_100` 实际子进程以 71 退出后保留原请求、预留、deadline、已消费额度 |
| F10 | 外来 Run 引用、字节篡改、追加指令/跨题文本、数学或代码修改、缺字段、重复工具提议、伪造工具动作和浮点舍入均拒绝；公开 Job/report/evidence/events 与 artifact 下载隔离 |

这些证据只支持工程候选。任意损坏 JSON、非法转义或无法还原原值的回复不在修复范围；不研究续写。修复不会判断原数学内容是否正确或与题目相关，原文中的指令仍是不可信数据，后续原角色审查负责数学判断。工具提议不等于工具回执或已证事实。

未执行真实 provider、真实配对效果实验、全仓约 22 分钟组合门禁或全系列两轴最终审查；这些由主聊天分别协调。宿主实测为 Windows ACL；POSIX 权限分支未独立运行。历史 v7 没有完整回复，未构造其原文，也未更改或续跑历史批次。`tests/test.md` 未读取、修改、提交或删除。
