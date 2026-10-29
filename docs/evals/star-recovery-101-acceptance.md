# #101 恢复、工具回执与 Meta 裁决验收

日期：2026-10-29（Asia/Shanghai）。Refs: #101。范围和公共接缝见[实施合同](../engineering/star-recovery-101-contract.md)。基点为已验收 #98 的 `dc9dc807314ad3fe27373e9a5111fdf3dcc6752a`；初始工作树干净，已通过 `git merge --ff-only showcase-star-timeout` 同步。

实现提交：`d45f9d6`（来源校验）、`32297fd`（隔离组合）、`3ea148df7ad0f8c16b41da418bd4ce661e8ee79a`（最近一次干预）。交付前再次合并当时的 `showcase-star-timeout` tip `dc9dc807314ad3fe27373e9a5111fdf3dcc6752a`，结果为 Already up to date，无冲突。

## 实现与红绿证据

产品代码仅修改 `showcase/solver_harness/traceback.py::transition_decision`。裁决沿用原 Run、plan、attempt、step 和未消费身份栅栏，并要求整数来源版本、对应的已提交 Meta 事件、同一动作最近一次干预的匹配内容。合法中间审计事件可以推进 State Revision，不要求来源版本等于最新 State Revision。

两个公共 Job 反例均先失败，再修复：

| 命令（均以 `uv run python -m unittest` 开头） | 红阶段 | 绿阶段 |
| --- | --- | --- |
| `tests.test_star_recovery_decisions_101.RecoveryDecision101Test.test_missing_decision_revision_cannot_authorize_traceback` | 缺失来源版本仍执行两次回退 | 拒绝推进，HTTP 保持 6 次 |
| `tests.test_star_recovery_decisions_101.RecoveryDecision101Test.test_superseded_genuine_approval_cannot_replace_the_current_ruling` | 较早真实 approval 覆盖新裁决并归档计划 | 拒绝旧裁决，重新取得合法裁决后终止，无归档/替换 Planner |

`uv run python -m unittest tests.test_star_recovery_decisions_101` 最终 9 项通过（19.125 秒）。除上述反例外，覆盖未来/非裁决/布尔版本、篡改目标、伪造 approval、合法审计间隔和已保存进展后的 Meta unknown。拒绝用例核对最终 HTTP、模型、工具、已知用量和预留；unknown 核对原公开调用身份、预留、deadline 与零自动重发。

## F07 / F08 / F09 映射

| 编号 | 本轮实际执行的证据 | 结果 |
| --- | --- | --- |
| F07 | `test_star_product_recovery` 的已接受步骤、已审计回复、协议修复回复、会话、工具/Verifier/Explore 回执及归档前后真实退出；`test_star_rb06_recovery` 的 limited / Reference 真实隔离回执退出 | 同一 Job 续算；已完成动作、接受步骤和回执不重复；原预算和 deadline 保留；在途工具无回执时拒绝恢复 |
| F08 | 新增 `test_star_recovery_receipts_101` 两项：既有 Reasoner repair 触发隔离工具，回执落盘后 `os._exit(71)`；重启后两个恢复者、重复 key、冲突 body；恢复中取消 | 两恢复者为 202/409；重复 key 为 200 且 `existing=true`，冲突为 409；成功账本为 7 模型/7 HTTP/1 工具、70 已知 tokens；取消账本为 5/5/1、50 已知 tokens，无步骤接受或后续派发 |
| F08 | `test_solver_harness_events`、`test_star_product_protocol_failure`、`test_star_compute_bounds` 及恢复链 | 版本 CAS、事件身份、修复中取消、已答复工具请求重复拒绝；最终账本一致 |
| F09 | 新增裁决模块；完整 Guidance / ReplanDecision / Trace-Back / CONTINUE / Harness Meta 模块；`test_star_product_align_recovery`、研究恢复和结果身份反例 | 当前真实裁决只消费一次；旧裁决不抢占；救援只保留合法成果，依赖失效的旧事实不进入最终审查；Meta unknown 普通 resume 为 409，保留原调用与预留 |

上述隔离场景固定 `MATHAGENT_TEST_PYTHON_IMAGE=sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d`。运行前 `docker image inspect` 实际确认 ID 为该值、平台为 linux/amd64。新增两项实际运行通过（25.083 秒，零跳过），各只创建和销毁一个容器，回执输出 `391\n`，`cleanup_verified=true`。两例均保留原限额、deadline 和预留。

## 完整相关模块与必要回归

第一层来源栅栏和隔离组合的完整回归为 108 项、297.951 秒，零失败、零错误、零跳过、零预期失败；baseline 及导入边界通过。日志在本工作树被忽略的 `artifacts/issue-101-validation/{validate.py,stdout.log,stderr.log,state.json}`；`state.json` 记录 PID 42004、UTC 起止时间和通过状态。测试使用 `scripts.run_unittest_report.run_suite` 强制要求全部 108 项实际执行，skip 不计通过。

108 项的模块命令如下（先设置上述固定镜像环境变量）。最终树已增加一个旧 approval 反例，不能将历史 108 项重标为最终树 109 项全绿。

```powershell
uv run python -m unittest tests.test_star_recovery_decisions_101 tests.test_star_recovery_receipts_101 tests.test_star_product_recovery tests.test_star_rb06_recovery tests.test_star_product_align_recovery tests.test_star_product_replan_reexplore_recovery tests.test_star_product_skill_recovery tests.test_star_product_protocol_failure tests.test_star_compute_bounds tests.test_solver_harness_events tests.test_solver_result_identity tests.test_star_job_unknown_98
```

108 项结果属于增加“较早真实 approval”反例之前的完整组合；新增反例及最终来源栅栏以随后 9 项专属模块和受影响完整模块的重跑结果为准。此后没有再次运行全仓约 22 分钟长门禁。

最终受影响模块重跑 36 项、178.032 秒，零失败、零错误、零跳过、零预期失败；产品源码与最终实现一致，之后仅修改注释和验收文档。最终输出保存在 `artifacts/issue-101-validation/affected-final.log`。

```powershell
uv run python -m unittest tests.test_star_product_guidance_consumption tests.test_star_product_replan_decision tests.test_star_product_traceback tests.test_star_product_continue_identity tests.test_solver_harness_meta tests.test_star_product_align_recovery tests.test_star_product_replan_reexplore_recovery
```

其他已执行检查：

- `uv run ruff check showcase/solver_harness/traceback.py tests/test_star_recovery_decisions_101.py tests/test_star_recovery_receipts_101.py tests/recovery_101_worker.py` 通过。
- `uv run python -c "from scripts.check_showcase_release import check_baseline; check_baseline(); print('baseline_and_import_boundary=PASS')"` 通过，11 文件字节及官方导入边界不变。
- `uv run python scripts/check_test_seams.py`、`uv run python demo_server.py --help`、`uv run python showcase_server.py --help`、`git diff --check` 通过。
- `uv run ruff check .` 未通过：未修改文件中已有 25 项（18 I001、4 F401、2 F841、1 E731），本票修改文件为 0 项。详细诊断保存在 `artifacts/issue-101-validation/ruff-existing.json`；未越界修复。

## 限制

全部为离线脚本替身或显式 `127.0.0.1` HTTP 加真实 Docker，不发真实 provider 请求，不改变历史消耗登记。提供方隐藏思考、远端会话恢复及数学能力提升均为 `not_covered`。完整全仓离线/发布组合门禁和系列最终两轴代码审查由主聊天协调，本记录不将其标为通过。

官方 baseline、默认开关、默认预算、llm_client、诊断模块及 #100 的并行序列化接口未修改。`tests/test.md` 未读取、修改、提交或删除；未 push、关闭 issue 或操作其他聊天。
