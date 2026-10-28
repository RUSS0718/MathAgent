# #97 非流式就绪：离线与真实批次核对状态

更新日期：2026-10-28。状态：离线工程门禁通过，已执行两次独立冻结的真实批次。首批完整结束，但多步题没有进入登记要求的非快通道。r8 批次完成简单题后，多步 Job 的第二次 Explore 请求超时，协调器以 `unknown_transport` 停止并保留一个未决 attempt。自然非快通道、步骤证明和数学核验条件仍未满足，#97 保持开放。真实运行证据与数学判定分开记录。

## v5 拟议登记状态

当前状态：`draft_not_dispatchable`。按用户最新指示形成 v5 草案，最终待审阅预览为 `artifacts/issue-97-prereg/manifest-v5-reviewed-20261028.json`；冻结不代表 live API 授权，本轮没有 v5 API 执行。本地文档拟议将[远程 Issue #97](https://github.com/RUSS0718/MathAgent/issues/97)原合同中的“不得提高现有预算”调整为更长的等待预算；本轮不修改该 GitHub issue。已消费的 v2/v4 登记和 2026-10-28 两次真实批次不变。

v5 候选为 Project Euler Problem 5 与 IMO 2025 Problem 4。此前把 IMO 多步候选称为 Problem 1 是错误的；IMO 官方[题目页](https://www.imo-official.org/problems/2025/)确认其为 Day 2 Problem 4（亦见[官方 PDF](https://www.imo-official.org/assets/documents/problems/2025/2025_eng.pdf)）。按用户允许提高预算的最新指示，拟议单请求 timeout 为 600 秒；简单题 Run 900 秒、多步题 Run 3600 秒、全批 4800 秒。token、logical calls、HTTP attempts、题目工具调用、Run 数和预检次数保持既有上限。候选输入、SHA-256 及估算依据见[v5 登记草案](../experiments/star-readiness-97-preregistration-draft.md)，执行边界见[v5 执行合同](../engineering/star-readiness-97-execution-contract.md)。

较长 wall-clock 只会给慢请求更多等待时间，不能保证模型自然选择非快通道，也不能保证产生步骤证明或数学正确结果。未自然触发的能力仍记为 `not_covered`。本轮已实现 v5 登记、timeout、批次 deadline 和独立消费合同，聚焦测试及完整发布门禁通过；具体登记仍需单独取得明确授权，之后才可调用 live API。

此前普通 sandbox 检查的失败已定位到运行环境：Git 的 `dubious ownership` 检查导致 setup 返回 `artifact_path_invalid`，无 Docker daemon 权限时实验 Job admission 返回 `503 star_prerequisites_unverified`。独立 HEAD 副本的 setup 6 项通过，实验前置失败也可在原 HEAD 复现；未据此修改产品行为或放宽测试。首轮 v5 全仓检查使用无 `.env`、固定 Docker 镜像的隔离副本，但审查补充测试后源码身份变化，该次检查已中止，不计 PASS。最终证据以修订后的固定源码门禁报告为准。

v5 实现提交为 `16885e7476ad67cb13bc8d1a63453297118b0d04`。聚焦组运行 77 项，76 项通过，1 项因未启用 Docker 集成而跳过；Ruff 与差异检查通过。这些检查覆盖 600 秒配置传入服务器、配置漂移拒绝、登记耗时计入全批、实际本地 HTTP 等待被 Run 或批次 deadline 截断、未知请求不重发、恢复保留原截止、迟到用量结算，以及冻结预览与按精确 hash 授权两个独立操作。真实题面已移出执行源码和测试。聚焦组中的 skip 不计为 Docker 覆盖；后续最终门禁已启用固定镜像和 Docker 集成，结果如下。

独立审查的规范轴未发现硬性违规；两道题的调用限额断言缺口已补齐。版本分支重复属于启发式建议，本轮保留现有版本选择方式。规格轴发现的授权时序和题面入库两项，均已在提交 `16885e7` 上独立复核关闭；复核未运行测试或修改源码。

最终门禁在不含 `.env`、移除 `INTERN_*` 环境变量的隔离副本中执行，固定镜像为 `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d`。`scripts/check_showcase_release.py --require-reference` 的 873 项测试全部通过，零失败、零跳过，`showcase_release=PASS`；测试接缝和六个旁路探针全部退出 0。该命令包含仓库合同、官方 baseline 与导入边界、两个 help 入口及 Solver 发布检查；没有重复运行含相同完整套件的 `scripts/check.py --offline`，首轮中断命令不计 PASS。

报告位于 `artifacts/issue-97-v5-offline-20261028-r2/gate-report.json`，SHA-256 为 `e17c5fb0da10bec8fdf3b15871b128d94b470d352f5581f4b0d42998ce255650`。运行前后及隔离副本的身份一致：revision `16885e7476ad67cb13bc8d1a63453297118b0d04`、源码 SHA-256 `37a9f1994019c582593cb807247ade9d59d72e3f28a2fd7c550ffc562e629b64`、dirty 状态为 true。组件映射从同一完整套件的发现列表与零失败、零跳过结果中核对得到 58 个测试，无单独重跑；结果为 `component-matrix-from-suite.json`，SHA-256 为 `75e3a3d4e2ca6bd30e79d09688ab0de373d9ac6494a012e172ec125bf6f84fc6`。这些证据仅为 scripted、fault-injection 或 replay，不是 provider-live 或数学能力证据。

文档交付提交后的 `delivery.json` 分别记录验收身份、交付身份及仅文档差异，并验证源码 hash 不变；不把两个 Git revision 称为同一身份。待审阅预览使用交付时的实际身份，仍为 `execution_authorized=false`；对应 hash 见同名 `.sha256` 文件。没有创建已授权的 v5 live manifest，也未消费 v5 批次。

## 2026-10-28 r8 真实批次结果

真实调用前，固定 Docker 镜像下的干净克隆通过发布门禁：865 项测试通过，零失败、零跳过；`showcase_release=PASS`。测试接缝检查和六个旁路探针均通过。门禁报告位于 `artifacts/issue-97-v4-final-20261028-r8/gate-report.json`。冻结源码 revision 为 `6bf499446fdc5172aca0b6359fb17a5c105302e6`，源码 SHA-256 为 `90d65722be39255bd5168c3e7218ccfa5af4bec6279d2ff3c529573d64b8905d`。

r8 live manifest 位于 `artifacts/issue-97-prereg/live-manifest-r8.json`，SHA-256 为 `13f9eb8d82d86c881fb4a2d07bdf55f99d4445ac6cb4841fd368943569efca1d`。登记固定 Intern S2、非流式 `star_reference`、`simple-03` 与 `multi-03`、请求参数、源码身份和原定预算。两题各派发一次，没有操作员重发。15 个脱敏归档文件的 SHA-256 均通过核验，归档位于 `artifacts/issue-97-v4-final-20261028-r8-live/`。

| 样本 | 公共 Job | 实际路径与工程结果 | 预算与用量 | 验收判定 |
| --- | --- | --- | --- | --- |
| `simple-03` | `run_bd1651388a4e491572a1bcc1b8cb6d1f` | 3 次非流式请求成功；Job `succeeded`；整题审查 `accepted`，绑定 `same_artifact`。归档分类为 `fastpath_no_step_proofs`。 | 3 logical calls、3 HTTP attempts、0 题目工具调用、7,682 已计费且已知 tokens；0 reserved、unknown 或 unresolved。 | 简单快通道有 live 工程证据；数学核验状态为 `unknown`。 |
| `multi-03` | `run_069306098d1b107288131a0337c5861c` | 首次 Explore 请求在 117.789 秒后收到 HTTP 200 和用量。第二次 Explore 请求等待 180.022 秒后超时，没有响应头或 provider usage。Job 以 `star_needs_review` 失败；协调器未能收集完成的 Run，并保留 SQLite 运行库。 | 2 logical calls、2 HTTP attempts、0 题目工具调用、7,355 已知 tokens、16,701 reserved tokens、1 unknown 和 1 unresolved attempt。 | 协调器以 `unknown_transport` 停止。Planner、Reasoner、步骤审查及题目工具均未覆盖；不重试该 Job。 |

批次汇总为 `stop_reason=unknown_transport`、2 个已派发 Job、1 个已收集 Run、3 次环境预检、5 logical calls、5 HTTP attempts、0 题目工具调用、31,738 charged tokens、15,037 provider-known tokens、16,701 reserved tokens、1 unknown 和 1 unresolved attempt。墙钟为 377.125 秒，实际费用未知，记 `null`。运行库保留在 `artifacts/issue-97-runtime/star-readiness-97-96a39w_x/`，保留原因为 `job_archive_incomplete`。检查时没有迟到用量补记文件。客户端记录只能证明第二次 Explore 请求在 180 秒截止前没有收到响应头，不能确认 provider 是否收到或处理了请求。请求传输与账本聚焦复核有 79 项通过、3 项因 Docker 环境缺失而跳过；未发现本地缺陷，未修改运行时代码或测试。该 manifest 与归档目录均已一次性消费；不得续跑、重试或替换样本。任何后续 live 请求都需要新登记和针对该登记的授权。

## 2026-10-28 首批冻结批次结果

真实调用前，在固定 Docker 镜像和移除 provider 凭证的测试环境中运行 `uv run --offline --frozen --no-sync python -B scripts/check_showcase_release.py --require-reference`：828 项测试通过、零失败、零跳过，`showcase_release=PASS`。冻结后的源码身份为 revision `40fb59bde44e3ce0c899a3d541b442201c3d8497`、源码 SHA-256 `813145e762009aee87983e436d6f7c9af33a8e8f4baf63696d66809c26fd2fcc`、`dirty_status=true`；工作树中的 retro 改动已纳入该源码身份检查。

一次性 live manifest 位于 `artifacts/issue-97-final-20261028/live-manifest.json`，canonical SHA-256 为 `0077b2884129f860169962cb31f9aa6e9da0a23e6440af1a5954b2c8c8c81bb0`，授权日期为 2026-10-28。它固定 Intern S2、非流式、完整 `star_reference` 配置、两道登记题面及其 hash、源码身份和原定单题/整批预算。执行归档位于 `artifacts/issue-97-final-20261028/live-run/`；16 个归档文件的 SHA-256 均通过核验，结果与运行记录相符。

| 样本 | 公共 Job | 实际路径与工程结果 | 预算与用量 | 验收判定 |
| --- | --- | --- | --- | --- |
| `simple-01` | `run_f2443b9f76c89ef48f403d7570023aaa` | 3 次非流式调用均成功；Job `succeeded`；整题审查 `accepted`，绑定 `same_artifact`。归档分类为 `fastpath_no_step_proofs`。 | 3 logical calls、3 HTTP attempts、0 题目工具调用、7,907 charged/known tokens；0 reserved、unknown 或 unresolved。 | 简单快通道工程路径有 live 证据；内置数学核验为 `unknown`。 |
| `multi-01` | `run_3e788d73f10a19aedefe8f1b46c124fc` | 5 次非流式调用均成功；两次固定镜像 `python_math` 隔离执行成功；Job `succeeded`；整题审查 `accepted`，绑定 `same_artifact`。实际角色没有 Planner、Reasoner 或步骤审查，归档分类仍为 `fastpath_no_step_proofs`，`nonfastpath=false`。 | 5 logical calls、5 HTTP attempts、2 题目工具调用、16,159 charged/known tokens；0 reserved、unknown 或 unresolved。 | 登记要求的自然非快通道、多步计划/步骤证据未触发，记 `not_covered`；不以成功执行工具代替该验收条件。 |

两题最终响应的数值均与独立计算结果匹配；然而公共 Job 的内置核验状态均为 `unknown`，这项数值核对不等同于形式证明。归档不含答案正文，只保留身份 hash、脱敏阶段/用量摘要和绑定信息。批次汇总为 `stop_reason=completed`、2/2 Run、3 次环境预检、8 logical calls、8 HTTP attempts、2 题目工具调用、24,066 charged/known tokens、0 reserved/unknown/unresolved，墙钟 166.282 秒；实际费用未知，记 `null`。没有追加、重试或替换样本。

协调器报告的临时运行库清理状态是 `deferred`。逐项确认两个 Run 的 8 个 HTTP ledger action 均为 `success` 且没有未决 action 后，已清理首批专属的临时 SQLite/响应目录；脱敏归档保留。这段清理状态只描述首批运行，不包含 r8 保留的运行库。

## 2026-10-27 历史研发记录

下列开发回合、组件矩阵和发布检查属于 2026-10-27 前置记录；其中“待完成”“未覆盖”只描述当时状态。2026-10-28 两次真实批次结果和当前总判定以上方为准。集成分支为 `showcase-star-readiness-97`；retro 改动作为 dirty source 纳入后续源码身份检查。

已实现独立登记适配、批次预算准入、严格 loopback 传输和一次性协调器。恢复、Skill、用量及传输聚焦组 34 项通过。取消后的报告验证来源与 Run Evidence 已统一；取消请求遇到 worker 同时进入终态时保留原结果，不能吞掉仍在运行时的取消错误。迟到结算及取消竞争连续三轮通过；包含固定镜像公共 Job 的相关聚焦组 32 项通过、无 skip，Evidence 历史另 2 项通过。早先两次聚焦命令有模块名称或模块导入方式错误，不计通过；以上数字来自纠正后的实际运行。

协调器的启动预检只消耗批次时间，Run 在准入后确定原截止。批次准入和等待使用单调时钟限制，系统时间回拨不会恢复可用时间。迟到响应只更新原 attempt 和独立 `supplemental-usage` 文件，终态归档及其 hashes 保持不变，且不再派发第二题。

独立审查发现的完整 Reference 配置缺口已修复：登记适配器 v2 显式冻结九项核心开关、工具名称、各阶段轮数、工具 timeout 和隔离镜像；启动及每次派发前比对有效配置并归档。动态 Run 额度仍由登记与 S3 策略执行，不使用 preset 的默认大额度。最终 #97 聚焦组 37 项通过、无 skip，包含真实本地 HTTP 与固定镜像公共 Job；关闭审查、工具或镜像漂移均拒绝。已派发但无法收集的 Job 保留身份，并把用量标记为不完整。

最终全仓验收使用被忽略的 `artifacts/issue-97-prereg/run_final_gate.py`，报告及原始日志写入 `artifacts/issue-97-final-20261027/`。报告包含前后源码身份、dirty 状态、门禁脚本 hash、逐命令退出码和日志 hash；只有 `passed=true` 且前后身份一致才构成本轮通过证据。该运行启用 `RUN_STAR_READINESS_DOCKER_INTEGRATION=1` 和固定镜像，执行 `scripts/check_showcase_release.py --require-reference`、测试接缝检查及六个旁路探针；没有重复执行包含相同完整测试套件的 `scripts/check.py --offline`。

本次最终报告实际为 `passed=true`：809 项测试全部通过、零 skip，`showcase_release=PASS`，测试接缝和六组旁路探针全部退出 0。报告 SHA-256 为 `87a6b9fd53d9e7f2fb3c6dc5043ef94a40703d1c081e2ade846fc2d613908309`。运行前后均为下述 `2d41434` 源码身份，dirty 状态为 true。门禁还核验官方 baseline、导入隔离、两个 help 入口和发布证据。最终文档提交之后，`delivery.json` 记录其相对验收提交仅有文档差异、源码 hash 相同；不把文档提交前后的 Git revision 称为同一身份。

最终组件矩阵由 `uv run --offline --frozen python -B artifacts/issue-97-prereg/run_component_matrix_final.py` 重新执行：58 项通过、零失败、零 skip。前后源码身份一致，为 HEAD `2d414342d959a36990e7dccd265d2444f1cdf2b1`、源码 SHA-256 `89e2799f308464169b3dea23af677df237f534e3f56a83125f536f001b18dc16`。新报告位于 `artifacts/issue-97-final-20261027/component-matrix.json`，SHA-256 为 `015527394d75fd78e3ab04f0f7ee80e952be1b230ed157ea1f2271dd9001f864`。该矩阵仍仅证明登记的 scripted、fault-injection 和 replay 场景。

交付的 `loopback-manifest.json`、`source-snapshot.zip` 及其 hash 汇总 `delivery.json` 也保存在该最终目录。manifest 重新绑定文档提交后的源码及 dirty 状态，仍为 `execution_authorized=false` 和 `provider_mode=loopback_only`。快照保留本次 Python 源码、测试、依赖、官方 baseline 和门禁脚本，包括验收时既有的未提交测试改动；它不包含题目原文、运行 raw 或 `tests/test.md`，需结合完整 Git checkout 复核。

截至该历史审查时，未发现硬性违规；两种传输路径各有一次 opt-in 选择，暂不为其增加共享抽象。当时执行器只支持脚本 loopback，live 执行入口尚未实现或授权。2026-10-28 后续完成了单独 live 入口和一次性批次；自然多步路径仍未覆盖，详情见本文顶部。旧工单状态不随 #97 证据自动改变。

## 历史源码和证据边界

核对开始时 HEAD 为 `fc6e9b4d489ae9e402fc3e97cfce0fe9e49f7762`，分支为 `fix/showcase-stream-usage-96`，工作树包含未提交修改。核对期间另一个窗口继续修改发布脚本和测试，故本记录不把工作树视为冻结源码。重新取得同一源码身份的门禁结果前，现有结果只能作为定位线索。

[既有 #96 记录](star-stream-usage-96.md)报告了脚本化简单题、多步 Reference 公共 Job、隔离回执消费和同 Job 恢复。它还报告当时的离线与发布门禁结果；这些是历史记录，不是本次重新验收。运行清单及九个 Reference 配置项对应的测试索引见[组件合同提案](../experiments/star-architecture-robustness-plan.md#按配置项逐一映射)。测试存在不等于本次执行通过。

前一轮启动的离线合同检查未完成：第一次缺少 Docker 权限和镜像配置，出现失败后中断；第二次使用固定镜像 `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d`，执行期间出现错误和失败，且工作树发生并行变化，随后中断。两次均不计 PASS，失败用例与原因尚未取得完整输出。

本次另执行 `uv run --offline --frozen python -B -m unittest tests.test_llm_late_settlement tests.test_run_budget tests.test_request_transport_late_callback`，25 项通过。这是当前未冻结工作树上的聚焦结果，只覆盖用量、预算和迟到回调测试，不替代公共 Job、逐组件矩阵或完整门禁。

随后以固定镜像执行 `uv run --offline --frozen python -B -m unittest discover -s tests -p 'test_*.py' -f` 定位首个失败：运行 440 项后，`ExperimentPublicJobTest.test_e2_mathematical_reject_is_honest_unsolved_not_transport_failure` 期望 `e2_gate_failed`，实际为 `source_changed`，因此失败。并行源码修改期间触发了源码身份检查；仅凭此结果不能判定数学拒绝处理本身有缺陷。此运行也不是固定源码身份的完整门禁。

随后在同一镜像下单独运行 `uv run --offline --frozen python -B -m unittest tests.test_star_experiment.ExperimentPublicJobTest.test_e2_mathematical_reject_is_honest_unsolved_not_transport_failure`，1 项通过。这只说明该次聚焦复测通过，不能推断其他失败或整套门禁已解决。

## 历史阶段尚未覆盖项

- `reexplore_after_replan`：早期测试要求恢复后新增 Explore 请求，但正常路径将研究发现交给 replacement Planner，不要求单独的 Explore 调用；该旧断言不能证明产品缺陷。修正后的公共 Job 测试检查 Planner 的新动作、研究结果及裁决消费，相关聚焦组 4 项通过。在隔离副本中将 `planning.py` 换成 HEAD 原版后，该测试连续三次因恢复后计划版本为 3 而非 2 失败；当前工作树聚焦测试通过。
- `skills`：新增公共 Job 测试覆盖进程恢复后角色 Skill ID / 版本及后续 Run 的上下文隔离，聚焦测试 1 项通过；完整 Reference 配置下的该专门恢复场景仍需独立核验。
- 九项配置的具名测试结果见下方组件矩阵；它们只证明被登记的受控场景，不能推断每种故障和恢复窗口都已覆盖。
- 截至下列前置阶段，真实非流式样本、自然触发的非快通道、完整 provider 用量及数学复核尚未执行，记 `not_covered`；后续 live 批次结果见本文顶部。
- 在该前置阶段，新批次的题目来源及 hash、源码身份、manifest、预算和停止条件尚未共同冻结。当前 `showcase.star_experiment_registration` 只接受旧的含流式十次安排；不能把新 readiness 条件当作旧批次的续跑或通过。正式 live manifest 与批次结果见本文顶部。

独立两题候选登记草案保存在被忽略的 `artifacts/issue-97-prereg/draft-v1.json`，文件 SHA-256 为 `12aa94729102caa10c6cb2ec2bcf7d95943d6edfc75f39df6f768cc23e8bcd14`。题源分别为 [Project Euler 第 1 题](https://projecteuler.net/problem=1)和[第 10 题](https://projecteuler.net/problem=10)，各安排一次非流式尝试。草案列出题文 hash、模型条件、单 Run 与整批硬限和停止条件；它没有冻结源码身份，也没有对应的预算执行器，状态为 `draft_not_dispatchable`，不能视为完成预登记或执行授权。该两题不承诺自然触发快通道或受控计算；未触发时按 `not_covered` 记录。

在该前置阶段，续版 `artifacts/issue-97-prereg/draft-v2.json` 增加了组件矩阵的源码身份和 dirty 状态，SHA-256 为 `cfc091faf41865c87ad5b196cd48183f2f1ebf874224dc22581ef16d0bed6f34`。[两题登记草案](../experiments/star-readiness-97-preregistration-draft.md)列出样本、模型、预算和停止条件。用户已确认其中单 Run 和整批预算映射；正式 live 登记、执行器和结果见本文顶部。

本次继续实现新增了登记校验、批次准入和默认关闭的严格 loopback 传输，相关聚焦回归 29 项通过；登记使用固定题面 hash，测试题面为合成数据。严格传输拒绝非 `127.0.0.1`、重定向和显式代理，忽略环境代理。真实草案的登记适配检查通过，但新代码改变了源码身份，之前的 manifest 与下文历史矩阵不能作为新源码的最终验收。独立批次协调器、公共 Job 故障验收和同源码最终门禁仍在进行；未授权或执行真实 provider 请求。

独立协调器已添加；设置 `RUN_STAR_READINESS_DOCKER_INTEGRATION=1` 并在具备固定镜像访问权限的环境运行 `uv run --offline --frozen python -B -m unittest tests.test_star_readiness_coordinator -v`，12 项通过、无 skip。该组包含本地 HTTP、认证公共 Job、真实 Docker 隔离工具的合成题执行，以及受控状态和调度故障用例。脚本执行不构成真实 provider 验收；部分停止场景使用测试替身，不能视为所有故障都已在真实公共 Job 复现。新实现仍待独立审查及同源码全量门禁。

## 历史逐组件离线矩阵

运行 `uv run --offline --frozen python -B artifacts/issue-97-prereg/run_component_matrix.py`，设置固定本地 Docker 镜像 `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d`。登记的 58 项测试全部通过，0 失败、0 skip；证据类型为 scripted、fault-injection 或 replay，并非 live。运行前后 `source_identity` 一致：HEAD `fc6e9b4d489ae9e402fc3e97cfce0fe9e49f7762`，源码 SHA-256 `5ad75b4d6def323e179a15679669ed5ebb5f936423c372bdf98fe1cfc57b136e`；工作树为 dirty。逐测试结果保存在被忽略的 `artifacts/issue-97-prereg/component-matrix.json`，SHA-256 为 `01dcf266895423e4ff1d24d84cb2f1f626a0951bbaadfafd2bd41272140ee995`。该报告不包含原始题目、提示或凭证。

同一源码身份的 Python 实现、测试、依赖配置及官方 baseline 文件保存在被忽略的 `artifacts/issue-97-prereg/source-snapshot.zip`，SHA-256 为 `cd4f2406ac695fd48c8f2c486fa156d2c6d3ae89719673a00a98fda724d6b4d6`；快照内的逐文件 hash 可重算上述源码身份。快照不包含用户保留的 `tests/test.md`，也不包含实验题库或运行 raw。它不替代 Git 提交，也不包含完整前端源码。

| 核心配置项 | 本次受控证据 | 限制 |
| --- | --- | --- |
| `star_routing` | 快通道、合法和非法计划、CONTINUE 恢复及 Reference 重规划分支通过。 | 自然模型路由仍为 `not_covered`。 |
| `persistent_sessions` | 角色历史恢复、身份冲突拒绝及进程退出恢复通过。 | 并非每个持久化边界都有独立故障用例。 |
| `stream_recovery` | 回执后同 Job 恢复、未知请求拒绝自动重发及 deadline 保留通过。 | 指持久恢复合同，不代表真实流式 provider 已验收。 |
| `final_generation` | 生成、证明传递、预算拒绝及审查失败保守处理通过。 | 不证明生成内容的数学正确性。 |
| `final_solution_review` | 整题审查绑定、拒绝、改写及伪造来源反例通过。 | LLM 接受不等于数学证明。 |
| `local_code_tool` | 固定镜像隔离执行、回执消费、策略拒绝及恢复不重放通过。 | 自然提出工具调用的 live 场景仍为 `not_covered`。 |
| `meta_guidance` | Guidance、独立 ReplanDecision、旧裁决旁路及恢复消费通过。 | 自然触发仍为 `not_covered`。 |
| `reexplore_after_replan` | 研究与预算测试及新增恢复后 Planner 消费测试通过。 | 独立自然重探索与 live 触发仍为 `not_covered`。 |
| `skills` | 角色注入、禁用、跨 Run 隔离及新增进程恢复测试通过。 | 新增恢复用例采用受限模式，完整 Reference 的该专门恢复场景仍为 `not_covered`。 |

各项的具体正向、拒绝和恢复测试 ID 见[组件映射表](../experiments/star-architecture-robustness-plan.md#按配置项逐一映射)及上述逐测试报告；三个共同配置准入用例也包含在本次 58 项中。未在报告登记的场景仍为 `not_covered`。

## 历史发布与差异检查

同一源码身份下执行 `uv run --offline --frozen python -B scripts/check_showcase_release.py --require-reference`：766 项测试通过、无 skip，`showcase_release=PASS`。该入口还检查官方 baseline 文件哈希、导入边界、两个 help 入口、发布证据合同和脱敏 replay。`uv run --offline --frozen python -B scripts/check_test_seams.py` 与 `git diff --check` 通过；`scripts/check.py` 中列出的六个旁路探针模块逐一执行并通过。没有再次运行包含相同完整测试套件的 `scripts/check.py --offline`，因此不将其命令本身标记为执行通过。

独立规格审查未确认恢复实现缺陷。标准审查指出非 `star_routing` 的恢复路径遇到非法替换计划时会沿用 `invalid_initial_plan` 原因；当前公共 Job 的受限和完整配置不能到达该分支，未为其增加产品行为改动。恢复和正常路径分别组装 Planner 请求，未来更改该合同需同时检查两条路径。完整 Reference 下的 Skill 专门恢复、真实非流式样本及新批次执行器仍未覆盖；这些结果不能升级为 live 或数学能力结论。

## 旧工单映射

| 工单 | #97 证据的用途 | 仍需独立满足的条件 |
| --- | --- | --- |
| [#80](https://github.com/RUSS0718/MathAgent/issues/80) | 本次 `multi-01` 没有自然进入非快通道，不能满足 ALIGN-AC-18 的真实路径证据。 | 仍需取得符合 #80 原合同的非快通道公共 Job，并独立复核计算回执、审查、S4、用量、来源映射、旁路与发布门禁。 |
| [#70](https://github.com/RUSS0718/MathAgent/issues/70) | #80 的复核可为其真实闭环条件提供证据。 | 全部适用 ALIGN 验收及发布判断仍分别成立；不自动关闭。 |
| [#87](https://github.com/RUSS0718/MathAgent/issues/87) | 可参考非流式组件和公共 Job 证据。 | 原实验合同及对应 ROB 验收仍有效；新批次不能替代原流式对照。 |
| [#95](https://github.com/RUSS0718/MathAgent/issues/95) | 可供检查同类工程合同和故障行为。 | 原 E1 为 2/4，E2 未执行；旧注册、门禁和阻塞关系未改变，不把新运行补入旧批次。 |
| [#96](https://github.com/RUSS0718/MathAgent/issues/96) | 非流式用量与故障证据可用于区分计量和传输状态。 | 流式 usage 请求、解析与 provider 兼容仍须按该票独立验收。 |

旧 E1/E2 的废弃或替代尚无决定，不能据本表移除其依赖或改写失败历史。#97 后续任何新增真实调用都须另行冻结注册与预算，并取得针对新登记的具体执行授权；已完成的两题不续跑、不重试。
