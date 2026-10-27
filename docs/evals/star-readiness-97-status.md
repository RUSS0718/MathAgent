# #97 非流式就绪：离线核对状态

日期：2026-10-27。状态：离线工程验收通过；#97 整体未完成，真实调用未覆盖。本记录不授权真实 provider 调用，也不替代独立实验注册。

## 续开发状态

当前集成分支为 `showcase-star-readiness-97`。另一个窗口的 retro 已结束；其发布脚本和测试改动保留在工作树中。下方原始检查记录及 766 项门禁属于历史源码，不能作为新增执行器的最终证据。

已实现独立登记适配、批次预算准入、严格 loopback 传输和一次性协调器。恢复、Skill、用量及传输聚焦组 34 项通过。取消后的报告验证来源与 Run Evidence 已统一；取消请求遇到 worker 同时进入终态时保留原结果，不能吞掉仍在运行时的取消错误。迟到结算及取消竞争连续三轮通过；包含固定镜像公共 Job 的相关聚焦组 32 项通过、无 skip，Evidence 历史另 2 项通过。早先两次聚焦命令有模块名称或模块导入方式错误，不计通过；以上数字来自纠正后的实际运行。

协调器的启动预检只消耗批次时间，Run 在准入后确定原截止。批次准入和等待使用单调时钟限制，系统时间回拨不会恢复可用时间。迟到响应只更新原 attempt 和独立 `supplemental-usage` 文件，终态归档及其 hashes 保持不变，且不再派发第二题。

独立审查发现的完整 Reference 配置缺口已修复：登记适配器 v2 显式冻结九项核心开关、工具名称、各阶段轮数、工具 timeout 和隔离镜像；启动及每次派发前比对有效配置并归档。动态 Run 额度仍由登记与 S3 策略执行，不使用 preset 的默认大额度。最终 #97 聚焦组 37 项通过、无 skip，包含真实本地 HTTP 与固定镜像公共 Job；关闭审查、工具或镜像漂移均拒绝。已派发但无法收集的 Job 保留身份，并把用量标记为不完整。

最终全仓验收使用被忽略的 `artifacts/issue-97-prereg/run_final_gate.py`，报告及原始日志写入 `artifacts/issue-97-final-20261027/`。报告包含前后源码身份、dirty 状态、门禁脚本 hash、逐命令退出码和日志 hash；只有 `passed=true` 且前后身份一致才构成本轮通过证据。该运行启用 `RUN_STAR_READINESS_DOCKER_INTEGRATION=1` 和固定镜像，执行 `scripts/check_showcase_release.py --require-reference`、测试接缝检查及六个旁路探针；没有重复执行包含相同完整测试套件的 `scripts/check.py --offline`。

本次最终报告实际为 `passed=true`：809 项测试全部通过、零 skip，`showcase_release=PASS`，测试接缝和六组旁路探针全部退出 0。报告 SHA-256 为 `87a6b9fd53d9e7f2fb3c6dc5043ef94a40703d1c081e2ade846fc2d613908309`。运行前后均为下述 `2d41434` 源码身份，dirty 状态为 true。门禁还核验官方 baseline、导入隔离、两个 help 入口和发布证据。最终文档提交之后，`delivery.json` 记录其相对验收提交仅有文档差异、源码 hash 相同；不把文档提交前后的 Git revision 称为同一身份。

最终组件矩阵由 `uv run --offline --frozen python -B artifacts/issue-97-prereg/run_component_matrix_final.py` 重新执行：58 项通过、零失败、零 skip。前后源码身份一致，为 HEAD `2d414342d959a36990e7dccd265d2444f1cdf2b1`、源码 SHA-256 `89e2799f308464169b3dea23af677df237f534e3f56a83125f536f001b18dc16`。新报告位于 `artifacts/issue-97-final-20261027/component-matrix.json`，SHA-256 为 `015527394d75fd78e3ab04f0f7ee80e952be1b230ed157ea1f2271dd9001f864`。该矩阵仍仅证明登记的 scripted、fault-injection 和 replay 场景。

交付的 `loopback-manifest.json`、`source-snapshot.zip` 及其 hash 汇总 `delivery.json` 也保存在该最终目录。manifest 重新绑定文档提交后的源码及 dirty 状态，仍为 `execution_authorized=false` 和 `provider_mode=loopback_only`。快照保留本次 Python 源码、测试、依赖、官方 baseline 和门禁脚本，包括验收时既有的未提交测试改动；它不包含题目原文、运行 raw 或 `tests/test.md`，需结合完整 Git checkout 复核。

标准审查未发现硬性违规；两种传输路径各有一次 opt-in 选择，暂不为其增加共享抽象。当前执行器只支持脚本 loopback，live 执行入口未实现，也未授权。真实 provider、自然触发和数学复核仍为 `not_covered`，#97 及旧工单保持开放。后续真实批次须先完成 live 执行入口和离线拒绝合同，再基于最终源码重新冻结登记并取得具体执行授权；本次 loopback manifest 不能直接用于付费调用。

## 源码和证据边界

核对开始时 HEAD 为 `fc6e9b4d489ae9e402fc3e97cfce0fe9e49f7762`，分支为 `fix/showcase-stream-usage-96`，工作树包含未提交修改。核对期间另一个窗口继续修改发布脚本和测试，故本记录不把工作树视为冻结源码。重新取得同一源码身份的门禁结果前，现有结果只能作为定位线索。

[既有 #96 记录](star-stream-usage-96.md)报告了脚本化简单题、多步 Reference 公共 Job、隔离回执消费和同 Job 恢复。它还报告当时的离线与发布门禁结果；这些是历史记录，不是本次重新验收。运行清单及九个 Reference 配置项对应的测试索引见[组件合同提案](../experiments/star-architecture-robustness-plan.md#按配置项逐一映射)。测试存在不等于本次执行通过。

前一轮启动的离线合同检查未完成：第一次缺少 Docker 权限和镜像配置，出现失败后中断；第二次使用固定镜像 `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d`，执行期间出现错误和失败，且工作树发生并行变化，随后中断。两次均不计 PASS，失败用例与原因尚未取得完整输出。

本次另执行 `uv run --offline --frozen python -B -m unittest tests.test_llm_late_settlement tests.test_run_budget tests.test_request_transport_late_callback`，25 项通过。这是当前未冻结工作树上的聚焦结果，只覆盖用量、预算和迟到回调测试，不替代公共 Job、逐组件矩阵或完整门禁。

随后以固定镜像执行 `uv run --offline --frozen python -B -m unittest discover -s tests -p 'test_*.py' -f` 定位首个失败：运行 440 项后，`ExperimentPublicJobTest.test_e2_mathematical_reject_is_honest_unsolved_not_transport_failure` 期望 `e2_gate_failed`，实际为 `source_changed`，因此失败。并行源码修改期间触发了源码身份检查；仅凭此结果不能判定数学拒绝处理本身有缺陷。此运行也不是固定源码身份的完整门禁。

随后在同一镜像下单独运行 `uv run --offline --frozen python -B -m unittest tests.test_star_experiment.ExperimentPublicJobTest.test_e2_mathematical_reject_is_honest_unsolved_not_transport_failure`，1 项通过。这只说明该次聚焦复测通过，不能推断其他失败或整套门禁已解决。

## 尚未覆盖

- `reexplore_after_replan`：早期测试要求恢复后新增 Explore 请求，但正常路径将研究发现交给 replacement Planner，不要求单独的 Explore 调用；该旧断言不能证明产品缺陷。修正后的公共 Job 测试检查 Planner 的新动作、研究结果及裁决消费，相关聚焦组 4 项通过。在隔离副本中将 `planning.py` 换成 HEAD 原版后，该测试连续三次因恢复后计划版本为 3 而非 2 失败；当前工作树聚焦测试通过。
- `skills`：新增公共 Job 测试覆盖进程恢复后角色 Skill ID / 版本及后续 Run 的上下文隔离，聚焦测试 1 项通过；完整 Reference 配置下的该专门恢复场景仍需独立核验。
- 九项配置的具名测试结果见下方组件矩阵；它们只证明被登记的受控场景，不能推断每种故障和恢复窗口都已覆盖。
- 真实非流式样本、自然触发的非快通道、完整 provider 用量及数学复核均未在本次执行，记 `not_covered`。受控 Job 不能代替 live。
- 新批次的题目来源及 hash、源码身份、manifest、预算和停止条件尚未共同冻结。当前 `showcase.star_experiment_registration` 只接受旧的含流式十次安排；不能把新 readiness 条件当作旧批次的续跑或通过。

独立两题候选登记草案保存在被忽略的 `artifacts/issue-97-prereg/draft-v1.json`，文件 SHA-256 为 `12aa94729102caa10c6cb2ec2bcf7d95943d6edfc75f39df6f768cc23e8bcd14`。题源分别为 [Project Euler 第 1 题](https://projecteuler.net/problem=1)和[第 10 题](https://projecteuler.net/problem=10)，各安排一次非流式尝试。草案列出题文 hash、模型条件、单 Run 与整批硬限和停止条件；它没有冻结源码身份，也没有对应的预算执行器，状态为 `draft_not_dispatchable`，不能视为完成预登记或执行授权。该两题不承诺自然触发快通道或受控计算；未触发时按 `not_covered` 记录。

续版 `artifacts/issue-97-prereg/draft-v2.json` 增加了下述组件矩阵的源码身份和 dirty 状态，SHA-256 为 `cfc091faf41865c87ad5b196cd48183f2f1ebf874224dc22581ef16d0bed6f34`。[两题登记草案](../experiments/star-readiness-97-preregistration-draft.md)列出样本、模型、预算和停止条件。用户已确认其中单 Run 和整批预算映射；该草案保持创建时的不可派发状态，执行器仍需实现和验收，真实调用需独立授权。

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
| [#80](https://github.com/RUSS0718/MathAgent/issues/80) | 自然非快通道的同一真实公共 Job 可供 ALIGN-AC-18 复核。 | 真实计算回执、审查、S4 和用量均须对账；来源映射、旁路与发布门禁仍需独立复核。 |
| [#70](https://github.com/RUSS0718/MathAgent/issues/70) | #80 的复核可为其真实闭环条件提供证据。 | 全部适用 ALIGN 验收及发布判断仍分别成立；不自动关闭。 |
| [#87](https://github.com/RUSS0718/MathAgent/issues/87) | 可参考非流式组件和公共 Job 证据。 | 原实验合同及对应 ROB 验收仍有效；新批次不能替代原流式对照。 |
| [#95](https://github.com/RUSS0718/MathAgent/issues/95) | 可供检查同类工程合同和故障行为。 | 原 E1 为 2/4，E2 未执行；旧注册、门禁和阻塞关系未改变，不把新运行补入旧批次。 |
| [#96](https://github.com/RUSS0718/MathAgent/issues/96) | 非流式用量与故障证据可用于区分计量和传输状态。 | 流式 usage 请求、解析与 provider 兼容仍须按该票独立验收。 |

旧 E1/E2 的废弃或替代尚无决定，不能据本表移除其依赖或改写失败历史。任何新真实调用均须先独立冻结注册与预算，并获得具体执行授权。
