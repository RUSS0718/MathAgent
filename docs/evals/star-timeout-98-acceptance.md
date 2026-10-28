# #98 绝对截止、未知结果与迟到对账验收

日期：2026-10-29（客户端 Europe/Paris）。实现及完整验收源码为 `f0ee72f01fb40d8d76d914fe85b1d2a13a2d8cde`；已快进集成到 `showcase-star-timeout`，集成 tree 与验收源相同。后续 #99–#110 分别验收，本记录不关闭尚未通过的真实实验门禁。

## 已通过检查

| 检查 | 结果 |
| --- | --- |
| 本地 HTTP 307、308 替身 | 各仅收到一次 POST，没有隐式重发 |
| F01/F03/F04 及相关聚焦回归 | 执行174项，53个强制用例全覆盖，零跳过、零预期失败 |
| `uv run python scripts/check.py --offline` | 1007项测试及仓库合同通过 |
| `uv run python scripts/check_showcase_release.py --require-reference` | 1007项测试、Reference及发布合同通过 |
| 源码与官方边界 | 门禁结束时SHA未变且工作树干净；11个baseline文件哈希与官方导入边界通过 |

隔离检查实际使用固定 Linux/amd64 镜像 `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d`，设置 `MATHAGENT_TEST_PYTHON_IMAGE` 和 `RUN_STAR_READINESS_DOCKER_INTEGRATION=1` 后执行上述完整门禁。无真实provider请求，使用离线假凭证及本地替身；本地HTTP不等于无socket。

运行证据位于实施工作树被忽略的 `artifacts/issue-98-validation-20261029-5d41312b/`，包含 `launch.json`、`state.json`、`stdout.log`、`stderr.log`。三项门禁退出状态均为0，最终 `VALIDATION=PASS`。宿主UTC日志完成时间为 `2026-10-28T17:56:44.4350555Z`，与客户端日期分别保存，不改写原日志。此前失败或中断的运行不能代替本次证据。

## 验收映射

- F01：`test_star_deadline_98`、`test_star_dispatch_boundary_98`、`test_star_parse_deadline_98` 等覆盖无头、静默、慢字节、heartbeat及请求/阶段/Run/批次最早截止。
- F03：`test_star_job_unknown_98`、`test_star_strict_98`、`test_star_transport_policy` 等区分超时、断流、缺终止标记、缺用量；保留原请求身份、未决预留和截止，未知状态零自动重发。
- F04：`test_star_stream_late_race_98`、`test_star_job_parse_deadline_98`、`test_star_late_durable_98` 等覆盖迟到重复结算、旧/新Run隔离、终态与文本不变、迟到工具不执行、数据库锁后恢复对账。
- 锁竞争：`test_star_job_read_lock_98`、`test_star_job_sqlite_deadline_98`、`test_star_sqlite_timeout_contention_98` 覆盖公共查询或调用在后台写入竞争时的有界返回，以及未落盘终态的诚实投影。

以上模块均包含于全仓1007项回归；可先用 `uv run python -m unittest tests.test_star_deadline_98 tests.test_star_job_read_lock_98 tests.test_star_late_durable_98` 执行短聚焦检查，再运行表中的完整门禁。

## 行为与限制

显式Showcase使用最早绝对截止；未确认请求保留原attempt、预留和原deadline。迟到结果只结算原请求，不覆盖终态、最终文本或新arm，不触发后续数学动作。文件STAR Job查询读取同一份已提交快照；终态尚未落盘时仅显示非终态截止观察，不伪称数据库已完成写入。

迟到落账重试耗尽后，白名单身份、分类和usage写入独立pending证据。`showcase.run_budget_late.reconcile_late_evidence` 仅显式结算原文件数据库中已有的HTTP attempt，重复调用不重复收费，也不派发模型请求。目录不可写、证据写入失败或内存账本消失时不承诺恢复成功，未知预留继续保留；该机制不提供断电持久性保证。

逻辑派发承诺不等于物理发包，不声明硬实时或远端取消。离线工程验收不证明数学能力提升或真实provider兼容。整个系列的最终两轴代码审查仍须单独完成，不能把未完成的审查记为通过。
