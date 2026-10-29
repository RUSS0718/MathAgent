# #102 诊断 Runner 离线验收

日期：2026-10-29（客户端 Asia/Shanghai）。合同：[实施合同](../specs/star-diagnostic-102-contract.md)。
入口为 `scripts/run_star_diagnostic_102.py`，只支持离线 fake，不创建真实批次。

## 使用合同

先在 ignored `artifacts/<new-id>/plan.json` 准备私有计划，字段如下：

```json
{
  "registration_id": "a-new-unique-id",
  "phase": "O",
  "seed": 17,
  "endpoint": "offline://socket-free",
  "window": {"start": 0, "end": 1800},
  "conditions_met": false,
  "requests": [{
    "question_id": "public-question-id",
    "arm": "current-json",
    "question": "<private full question>",
    "prompt": "<private full prompt>",
    "schema": {"type": "object"},
    "timeout_seconds": 1800,
    "stream": false
  }]
}
```

时间窗使用 Unix 秒，示例0并不可运行，必须冻结实际窗口。`conditions_met=false` 返回 not_started，不消费登记。
非 S 阶段禁止 stream；R 必须提供实际冻结的等待值，不默认替它选择。
请求列表顺序就是冻结顺序；seed 记录配对计划的随机种子，本 runner 不重新洗牌。
题单覆盖度与 P 的前三臂、T/R/S 的实验设计仍由 #103–#107 各自验收；本票只验证资源上限和身份。

在仓库根目录运行（路径均须位于本工作树 ignored artifacts；不要复用历史 #97 身份）：

```powershell
uv run --offline python scripts/run_star_diagnostic_102.py freeze --plan artifacts/<new-id>/plan.json --registration artifacts/<new-id>/registration
uv run --offline python scripts/run_star_diagnostic_102.py dry-run --registration artifacts/<new-id>/registration
uv run --offline python scripts/run_star_diagnostic_102.py fake-run --registration artifacts/<new-id>/registration --archive artifacts/<new-id>/batch --sha256 <freeze返回的摘要>
uv run --offline python scripts/run_star_diagnostic_102.py monitor --archive artifacts/<new-id>/batch
```

退出码：正常预演/完成/控制块/未启动为0；暂停/无法读取为1；准入拒绝为2。
manifest 包含 endpoint hash、stream、源码 SHA/dirty/源文件集合 hash/runner hash、上游、题面/prompt/schema hash、参数、seed、窗口及预算/停止规则。
`private/plan.json` 保留完整输入，逐请求 `private/<workspace_id>/` 保存原输入及 fake 可见回复/答案。
公开日志只包含状态、位置和随机 Run 身份；monitor 不读取 private，异常不回显任意 payload。

P 一次冻结全部最多36项，先加 `--control-only` 执行其中3项；后续在同一 archive 加 `--continue-p`。
首3项的 run/attempt/deadline/result_sha256 引用保持不变；累计计量来自原 S3 行，剩余最多33项，不新增一个36项的 P。
换目录、重复启动、unknown 后换登记均被 common-dir 下的独立 fake 消费登记簿拦截。
源码变化也会拒绝继续，因此消费者应使用冻结的同一源码环境。

`DiagnosticJob.cancel()` 创建持久取消标记；`reconcile(run_id, attempt_id, ...)` 只接收可信离线 usage，
通过 S3 结算原 HTTP 一次，不覆盖结果或暂停终态，不自动解锁或恢复批次。
实际派发前 intent 已提交但 HTTP 未落账时，monitor 显示 charged/reserved 不可用及65536未确认预留，避免漏计。
charged 已含 reserved，汇总不再相加。金额、不可观测远端并发始终 unknown/null。

## 监控与后台运行

`process.json` 指向本次实际 PID、OS 创建时间和独立 stdout/stderr；`process-*.json` 保留每次所有者记录。
该文件的 `monitor_argv` 可作为参数数组复用。monitor 的 PID 创建时间比对可以识别退出和复用；
`restart_requires_review` 仅表明本地所有者失效，不宣称远端已结束。
查询使用独立短子进程中的 SQLite mode=ro、readonly_shm=1、query_only 和单一读事务，读取 WAL，不使用 immutable=1，也不实例化写账本。
缺文件/缺表/坏账本/锁不可读时返回 unavailable；不会初始化、消费、取消、修复或自动清理。

如后续确需后台 fake，可用 `Start-Process -WindowStyle Hidden` 启动 **uv run --offline python**，
将启动器 stdout/stderr 分别重定向至独立的 ignored 文件；消费端以 batch/process.json 中实际 Python PID及创建时间为准，
不要把 uv 启动器 PID 当作 worker。使用上面的 monitor 命令查询，不按 PID 推断远端状态。
本票只运行短测试，没有后台长批次、真实派发或 heartbeat。未来真实长批次的通知由对应工单按既有偏好登记。

## 红绿与验收映射

- 冻结 call：先运行 `uv run --offline python -m unittest tests.test_star_diagnostic_registration`，缺模块报错；
  随后准入通过。追加“重封摘要后越过65536”用例先失败，再补严格字段检查。
- 公共 Job：`uv run --offline python -m unittest tests.test_star_diagnostic` 先缺模块报错；
  随后覆盖冻结顺序、独立身份、一逻辑/一HTTP/零工具、跨目录/线程/进程竞争、取消、重启、unknown、迟到幂等和故障归档。
- 只读 monitor：`uv run --offline python -m unittest tests.test_star_diagnostic_monitor` 先缺模块报错；
  注入额外 limits payload 的测试曾失败，改成数值白名单后通过；覆盖缺失/损坏/锁/WAL及前后文件 hash 一致。
- CLI / process：专属测试先因入口/模块缺失失败，实施后验证显式子命令、路径拒绝、脱敏及 PID 创建时间识别。
- P 包含关系：完整36项 fake，先3后33，前3项引用不变、总派发36、累计额度不重置；O900只是冻结影子点元数据，不新增 HTTP。
- P 续接审查补测：私有控制结果摘要损坏先复现未拒绝，再加入摘要核验；
  并发只读 monitor 曾在续接中显示 control_complete，新增公共 Job/monitor 用例后修正为 running。

## 证据与限制

最终聚焦与相关回归72项通过，零skip、零expected-failure，47.435秒；其中 #102 专属30项。
命令（完整模块，不挑选单个成功用例）：

```powershell
uv run --offline python -m unittest tests.test_star_diagnostic_registration tests.test_star_diagnostic tests.test_star_diagnostic_monitor tests.test_star_diagnostic_process tests.test_star_diagnostic_cli tests.test_run_budget tests.test_star_readiness_late tests.test_star_readiness_archive tests.test_star_readiness_runtime tests.test_request_transport_late_callback tests.test_star_late_durable_98 tests.test_star_strict_98 tests.test_baseline_snapshot
uv run --offline ruff check showcase/star_diagnostic*.py scripts/run_star_diagnostic_102.py tests/*star_diagnostic*.py
uv run --offline python -c "from scripts.check_showcase_release import check_baseline; check_baseline(); print('baseline_and_official_boundary=PASS')"
uv run --offline python scripts/check_test_seams.py
uv run --offline python demo_server.py --help
```

以上范围 Ruff、11个 baseline SHA 与官方导入边界、既有测试接缝检查和 Demo help 均通过。
`uv run --offline ruff check .` **未通过**：25处既存问题分布于16个其他文件；
对每个报错文件用 `git show dc9dc807314ad3fe27373e9a5111fdf3dcc6752a:<path>` 与当前文件比较 SHA256，全部字节一致。
未修改这些文件。详情 `ruff-all.json`；聚焦日志为 `final-focused-regression.log`，均在 ignored `artifacts/issue-102-validation-20261029/`。
前一轮70项和71项通过仅作迭代记录，以最终72项记录为准。

增加续接运行态用例后，一轮72项组合中未修改的
`tests.test_star_readiness_late.StarReadinessLateUsageTest.test_late_usage_updates_original_attempt_after_terminal_archive_is_frozen`
失败：预期 unknown_transport，实际 evidence_mismatch；保留 `combined-72-failed.log`（48.884秒）。
立即单独重跑完整 `tests.test_star_readiness_late`，3项通过（2.570秒，`readiness-late-rerun.log`）。
该用例给运行预留2秒，但此处没有定位失败根因，不把推测当作结论，也未改动该模块。
随后完整重跑相同72项组合通过（47.435秒），失败记录继续保留，供主聊天最终门禁关注。

本票改动路径：`showcase/star_diagnostic{,_registration,_store,_monitor,_process}.py`、
`scripts/run_star_diagnostic_102.py`、`tests/star_diagnostic_support.py`、
`tests/test_star_diagnostic{,_registration,_monitor,_process,_cli}.py`、
`docs/specs/star-diagnostic-102-contract.md` 与本文。官方、#97和其他票文件没有修改。

本票不测真实900/1800秒等待，不提供 live 派发或物理远端取消保证；进程中断用 fake crash 窗口建模，不宣称断电持久性。
没有工具执行，未调用 Docker；既有 #98 固定镜像验收只作为上游证据引用，不把未运行的隔离检查计为通过。
全仓 offline / Reference / release 组合门禁留给主聊天协调。本票的工程验收不能证明数学能力或真实 provider 兼容。

## 集成评审修复候选（2026-10-29）

原只读测试在 `run()` 已执行首次快照后才记录文件 hash，遗漏关闭 WAL 库没有 sidecar 的情况。
新增测试直接使用生产者 initialize / S3 / status 后关闭连接，不经过 Job 快照；旧实现首次监控新增 WAL/SHM，明确失败。
生产者现在在终态（含 P 控制边界）执行 checkpoint 与 DELETE journal 切换，续接时恢复 WAL；
缺少 sidecar 的旧 WAL 库返回 unavailable，成功 Job 的终态返回、后续 CLI 监控和 P 续接仍可使用。

只调整关闭流程仍不足：新增活跃 WAL 首读文件 hash 断言发现 SHM read mark 被修改。
实测运行时为 uv Python 3.12.13 / SQLite 3.50.4；`readonly_shm=1` 独立进程读取保持 hash，
同进程则复用 writer 的可写 SHM 节点，故所有监控均隔离到短子进程（DELETE 也可能在续接时切回 WAL）。
固定版本 [Windows VFS 源码](https://raw.githubusercontent.com/sqlite/sqlite/version-3.50.4/src/os_win.c)
第4122行读取此参数，第4127–4143行复用进程内 winShmNode；
[Unix VFS](https://github.com/sqlite/sqlite/blob/version-3.50.4/src/os_unix.c) 也处理此参数。没有以参数无报错作为支持证据。
生产者关闭前切换 DELETE 的依据是 [SQLite WAL 文档第5节](https://www.sqlite.org/wal.html#read_only_databases)。没有升级运行时或依赖。
文件路径与字节 hash 测试覆盖：关闭 WAL 库首次及重复读取、正常终态归档、未 checkpoint 的新 WAL 提交首次及重复读取，
以及已完成 backfill 后与重复 PASSIVE checkpoint 并发读取。checkpoint 自身有待写页时会合法改变文件，不能把该变化算作 reader 写盘。

运行限制：每次监控增加一次子进程启动，5秒进程上限/0.2秒 SQLite 等锁后可返回 unavailable；
生产者切换 journal 需要取得 SQLite 锁。损坏、缺 sidecar 或需要恢复的归档由拥有写权限的生产者处理，monitor 不执行恢复。
不支持把此 Windows 实测外推到自定义 SQLite VFS，也未独立执行 POSIX 宿主验证。
最终五个诊断专属完整模块，加 `tests.test_run_budget` 与 `tests.test_baseline_snapshot` 共47项通过（106.019秒），零跳过；
命令为 `uv run --offline --no-sync python -B -m unittest tests.test_star_diagnostic_registration tests.test_star_diagnostic tests.test_star_diagnostic_monitor tests.test_star_diagnostic_process tests.test_star_diagnostic_cli tests.test_run_budget tests.test_baseline_snapshot`。
本轮变更 Python 文件的 Ruff、11个 baseline hash 与官方导入边界均通过。
这是聚焦修复候选，全系列门禁与修复后的验收复审仍由主聊天协调，不声明最终通过。
