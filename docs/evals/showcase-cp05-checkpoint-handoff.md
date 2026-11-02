# CP-05 检查点公共 Job 验收与 #112 交接

**状态：** 受控 loopback / fault-injection 验收完成；provider-live 与数学能力结论仍为 `unknown`。

**日期：** 2026-11-02（Asia/Shanghai；各历史时间保留原时区）

**范围：** Issue #116–#120 / CP-01..CP-05，最终门禁冻结提交 `3eeddf1b37f2e9db1b6d66e0bead6e24cfcdb011`，源码树 `a7272be3bda6af95649b79c3064515fbf7006c76`，分支 `showcase-cp-checkpoint-integration`。后续文档提交独立于代码冻结提交。只接入 Showcase 的显式 STAR 配置；官方 `user_agent.ReasoningAgent`、`implementations/`、默认预算和 baseline 保持不变。

## 验收合同

控制版与候选版使用同一个受控公共 Job、同一个单步 toy task 和同一组脚本化回复。控制版配置为 `final_generation=true`、`final_solution_review=true`，两个 checkpoint 和 `meta_guidance` 均关闭；候选版在此基础上显式打开 `planner_checkpoints=true`、`reasoner_checkpoints=true`、`meta_guidance=true`。流式配置不由 adapter 是否具有 `stream_complete` 推断，只有 `stream_activity=true` 时才选择流式调用和活动投影。

两套配置的规范化 JSON 指纹（UTF-8、键排序、紧凑分隔符后 SHA-256）为：控制版 `ab8942a128c8ccc5fc39e91e14b53c3ddc5777b8947d450d1b59ca83cac93527`，候选版 `19cffe90fe245695acc92779ca61289136a0b690a98e95c90a90b4ef42151256`。两次运行均为本地脚本 loopback，`thinking_mode` 为 `None`，不向 provider 请求发送 thinking 开关；transport 为受控 HTTP loopback/脚本响应，禁止真实 provider 请求。

运行时指纹与请求数据绑定：`prompt_fingerprint` 是最终传给 `InternModelPort` adapter 的完整 `messages` 的规范化 JSON SHA-256；`input_fingerprint` 是构造这些 messages 时实际采用的题目（包含 `original_problem` fallback）的规范化 JSON SHA-256；`schema_fingerprint` 是本次 request 的实际 `response_schema` 的规范化 JSON SHA-256；既有 `prompt_layers_fingerprint` 仍表示旧 prompt layer 投影。新增三类审计值只写入 invocation / Evidence，不进入默认 provider context；关闭 checkpoint 协议时，旧 `prompt_fingerprint` context 字段和原 messages 保持不变。CP-05 公共回归按每个 outbound role 重算 messages、input、schema，并覆盖 `final_generator` 的真实角色事件。

Planner 与 Reasoner checkpoint protocol version 均为 `1`。实际 messages 与 schema 的逐角色指纹、控制版和候选版配置及预算见下方最终门禁记录；静态协议定义不代替运行时请求身份。

CP-05 的公共 Job 入口是 `POST /api/agent/jobs`，观察面是 Job、事件 SSE、报告和 Evidence。任务粒度为每次运行一个公开 toy task、一个 Plan、一个 step；控制版角色调用序列为 `explore → planner → reasoner → step_verifier → final_generator → whole_solution_verifier`，共 6 个 logical/HTTP 调用；候选版为 `explore → planner → planner → reasoner → meta → reasoner → step_verifier → final_generator → whole_solution_verifier`，共 9 个 logical/HTTP 调用。两版均为 0 个工具调用，测试预算上限为 12 个 logical/HTTP 调用，token 与运行时上限仍由既有 `RunBudgetLimits` 计算。角色、轮次、状态和脱敏后的摘要可复核，原题、完整 prompt、隐藏答案、Meta 任务正文、完整 checkpoint ID 和个人信息不进入公共证据。

候选版最多执行 2 个 Planner checkpoint round、2 个 Reasoner checkpoint round 和 1 次 Meta guidance；本次脚本路径实际使用 Planner `YIELD → FINAL`、Reasoner `YIELD → FINAL` 和 1 次 `retry_different_method`。控制版不创建 checkpoint。停批规则是：Job 到达 `succeeded`、`failed` 或 `canceled` 即停止；断流、未完成流、进程退出和未知远端结果进入 `needs_review`，不自动重发；取消或 deadline 后的迟到结果只允许按原 attempt 结算已知 usage，不得推进数学状态；预算、原 deadline 或协议硬失败均结束当前 Run，不换题、不扩预算。

独立评分只对可复核工程合同计分，不对数学答案或 provider-live 效果计分：角色序列和轮次 25%，logical/HTTP/tool/token 预算与原 deadline 20%，Job/Report/Evidence 最终字段一致性 25%，流式六类故障矩阵 20%，恢复不重复与脱敏边界 10%。每项以公共断言的 pass/fail 记录；任一硬预算、取消、deadline、unknown 或协议合同被错误改写，该项为 fail。控制版作为同题基线，候选版只报告合同差异和新增调用成本，不将差异解释为能力提升。

候选的非流式纵切顺序为：Explore 返回 `NEED_PLAN`；Planner 先交 `YIELD` 草案，再按反馈交合法 `FINAL` Plan；Reasoner 交局部成果；Verifier 审查并要求 Meta 的 `retry_different_method`；Reasoner 继续下一轮；Step Verifier 接受；Final Generator 生成最终文本；Whole Solution Verifier 完成最终审查。只有最终审查接受后 Job 才是 `succeeded`，checkpoint 局部成果不会直接成为最终答案。

## CP-01..CP-04 与 CP-05 证据映射

| 能力 | 受控证据 | 结论边界 |
| --- | --- | --- |
| CP-01：公共 Job、状态投影、脱敏 | `tests/test_cp05_public_job.py::CP05PublicJobTest.test_non_stream_checkpoint_job_covers_handoff_meta_and_final_review` | 证明公共入口可达、角色顺序和最终审查绑定；不证明数学正确率 |
| CP-02：流式活动与交接 | `tests/test_solver_harness_streaming_activity.py`、`tests/test_star_product_streaming_recovery.py` | 覆盖活动指标、片段持久化、交接和公共字段脱敏；文本正文不进入活动事件 |
| CP-03：Planner 检查点 | `tests/test_solver_harness_planner_checkpoint.py`、`tests/test_cp05_public_job.py` 与 `tests/test_star_product_recovery.py::StarRecoveryTest.test_public_planner_checkpoint_process_recovery_and_duplicate_resume` | 覆盖 `YIELD → feedback → FINAL`、新调用身份、版本/空缺口/无进展/预算拒绝、进程退出、完成检查点复用和重复 resume 去重 |
| CP-04：Reasoner 检查点与 Meta | `tests/test_cp04_public_faults.py::CP04PublicFaultTest` 的六个公共 Job 用例：`test_yield_verifier_objection_reaches_next_reasoner_before_final_review`、`test_cancel_during_reasoner_checkpoint_does_not_reach_verifier`、`test_resume_rejects_old_revision_after_reasoner_checkpoint_unknown`、`test_traceback_with_reasoner_checkpoints_excludes_invalidated_results`、`test_approved_replan_decision_dispatches_new_plan_with_reasoner_checkpoints`、`test_process_reopen_reuses_reasoner_checkpoint_and_tool_receipt_once`；辅助机制证据见 `tests/test_solver_harness_reasoner_checkpoint.py`、`tests/test_star_product_traceback.py`、`tests/test_star_product_replan_decision.py`、`tests/test_star_product_recovery.py` | 六例直接通过公共 Job 验证局部 `YIELD → Verifier` 异议 → 下一 Reasoner、checkpoint 阶段取消、旧 revision 拒绝、合法 traceback 后排除失效成果、批准 replan 后真实新 Plan/Reasoner，以及进程重开后的完成 checkpoint 与真实 tool receipt 复用；恢复例同时核对原 deadline、累计 logical/HTTP/token 账、旧 call identity 和重复 resume。旧 harness/helper 测试只作补充，不能替代这六例；最终结果仍需 whole review 接受 |
| CP-05：集成与交接 | 本记录及 `tests/test_cp05_public_job.py` | 证明受控 loopback 工程闭环，不升级 provider-live 或能力结论 |

流式边界沿用已有公共 Job 证据：正常活动、调用完成、静默、无正文、缺 usage、断流、取消和迟到结果分别保持完成、空正文失败、usage 未知、unknown、canceled 或忽略迟到响应的原合同；断流和进程退出保留 unknown 与预留，不自动重发。活动投影保留固定字段集合；未观测的时间点、计数、usage 状态和终态统一公开为 `unavailable`，不把缺失观测误报为成功。恢复测试还核对已完成检查点、已接受成果和工具回执复用，不重复模型或工具调用，累计 logical / HTTP / tool / token 计数与原 deadline 不被重置。

## #112 实验交接

本交接保留 #112 的原批次身份、原始 `5/15` 标识、10 项 `not_run` 项、Planner `unknown` 身份、`deadline=unknown` 的原登记和预算预留。旧 raw、state、ledger 不改写；#112 仍按原登记保持 `unknown/not_run`，CP-05 的 loopback 结果不能替代或覆盖它。

这里的 `deadline=unknown` 仅指原登记，不能泛化到后续 TH02 Planner attempt。该 attempt 为 `909ebf8665914c66b786c914d9153d0e`，logical call 为 `be9386836ef948288e21060e6e36e265`；request 为 `2026-10-31T09:10:55.967707Z`，300 秒推导截止为 `2026-10-31T09:15:55.967707Z`，阶段截止为 `2026-10-31T10:23:16.114062Z`。这些已知时间不把 Planner unknown 结算为成功，也不授权重发。原 5/15 中 4 次完成、3 次 schema 与语义均有效，Explore 为 invalid_json，Planner 为 unknown；已知 13787 tokens、未知预留 20825 tokens、计入额度 34612 tokens。

交接只增加本 CP-05 的可复核脱敏记录：

- 控制版：checkpoint 开关关闭，旧公共合同和调用计数作为基线。
- 候选版：Planner / Reasoner checkpoint、Meta 指导和最终审查显式开启。
- 输入、角色、schema 版本和配置使用规范化摘要或指纹定位；公共文件不保存原题、完整 prompt 或敏感正文。
- 预算、checkpoint 轮数和停批规则沿用既有 Run 账本；`unknown`、`not_run`、迟到和取消分别保留原身份。
- 评分只记录工程可达性、事件/状态合同、恢复不重复和脱敏边界；不把 Demo 可运行、结构测试通过或 replay 一致误报为数学能力提升。

## loopback、replay 与 provider-live 边界

本次 CP-05 只使用本地脚本响应和故障注入，没有真实模型请求、没有新增付费探测。loopback 证据证明状态机、公共 Job、事件投影和预算/恢复合同可复核；replay 只重放已持久化状态与事件，不调用模型、Verifier 或工具，也不增加数学证据。

provider-live 仍是独立门槛：需要单独授权、独立批次身份、固定输入与 prompt/schema 指纹、真实 usage/finish reason、原 deadline、成本和失败处置记录。当前没有 provider-live 结果，不能据此关闭 #112、宣称能力提升或推断数学正确率。

## 本次修复验证边界

本修复 worker 未启动全量测试；父线程保存的历史全量结果为 `1030 tests, errors=1, skipped=42`，唯一错误是 deadline 竞态用例的分类不稳定，单独诊断和重跑均通过，不能写成全量通过。新增 CP04 公共验收单独运行命令 `uv run python -m unittest tests.test_cp04_public_faults`，结果为 `6 tests, 0 errors, 0 skipped`。与既有 Reasoner/traceback/replan/recovery 聚焦模块联合运行结果为 `53 tests, 0 errors, skipped=1`；唯一 skip 是未设置已验证 Docker reference image 的参考预置测试。其余 CP-05、共享事务与非阻塞 settlement、deadline、流式矩阵、实际指纹、关闭协议和 Reference loader 检查属于父线程既有聚焦证据；本记录不把跳过视为通过。Docker 参考验收仍由最终门禁按 `MATHAGENT_TEST_PYTHON_IMAGE` 和 `--require-reference` 单独执行。


2026-11-01 后续审查记录：父线程在 `60a4ac8` 的 146 项聚焦检查结果为 `3 failures, 1 error`，不能记为通过。两锁阻塞已由既有公共用例复现后修复：账本门独立于 Workspace 门，写连接与事务仍共享；同步 timeout 同时非阻塞检查两个门，迟到重试只在实际事务内取得共享连接门，并限制门等待与 SQLite 忙等待。UTC 截止现在直接采用原账本/phase/batch 的绝对值，不经低分辨率 monotonic 转换；回拨立即 fail-closed，耗时指标仍使用 `perf_counter`，原预算与默认未计量路径不扩展。两个迟到测试夹具仅将分片改为 64 字，避免 SQLite 逐事件持久化先耗尽目标阶段预算，保留预算和原断言。

本轮定向证据为：新增回归及原四故障点/共享事务组 `15 tests, OK`；流式迟到/解析/SQLite contention 组 `22 tests, OK`；修正 stream assembly 目标夹具后相关七项 `7 tests, OK`；时钟回拨与 coordinator 组 `38 tests, OK (skipped=1)`。这些运行有重叠，不相加为独立总数。中途聚焦曾出现迟到事务提交 busy 和 stream assembly 阶段未到达；诊断记录与修复结果在仓库外 `review-fix-followup-report.md`，不以单跑通过替代组合证据。首前三轮最终门禁失败记录与本轮 `cp-final-05` 完整通过结果分开保留；#112 原登记、raw/state/ledger、`5/15`、`10 not_run`、Planner unknown 和 deadline unknown 不变。

## 最终集成门禁与冻结来源

冻结代码提交：`3eeddf1b37f2e9db1b6d66e0bead6e24cfcdb011`。Git tree：`a7272be3bda6af95649b79c3064515fbf7006c76`。
集成分支：`showcase-cp-checkpoint-integration`。后续交接文档提交独立于代码冻结提交，避免自引用。
本节取代前文早期切片冻结指针和静态 schema 数字，最终结果以该代码身份及运行时指纹为准。

| 阶段 | 退出码 | unittest suite 项数 | 跳过 | 秒 |
| --- | ---: | --- | ---: | ---: |
| source-integrity | 0 | 不适用 | 0 | 0.562 |
| disabled-wire-contract | 0 | 不适用 | 0 | 2.61 |
| runtime-fingerprints | 0 | 1 | 0 | 6.5 |
| focused | 0 | 151 | 0 | 266.593 |
| release | 0 | 41 | 0 | 146.266 |
| official-default-demo | 0 | 11 | 0 | 3.125 |
| offline | 0 | 1052 | 0 | 1665.406 |

执行命令保存在本地 `final-validation-05.log` 的各个 COMMAND 行。产品门禁为 `uv run python scripts/check_showcase_release.py --require-reference`；全仓门禁为 `uv run python scripts/check.py --offline`，含测试接缝检查、六个 mutation probes 和两个 CLI smoke。
Docker 固定镜像：`sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d`。进程局部启用 `MATHAGENT_TEST_PYTHON_IMAGE` 与 `RUN_STAR_READINESS_DOCKER_INTEGRATION=1`，未改变产品默认配置。
官方 baseline 的 11 项字节校验均一致，官方源码与受保护历史文档无差异。关闭检查点后的七角色消息与 schema 与前置基线 `1ecc96c593443785316e7af7154dea79cda5afab` 一致。

先前失败记录仍保留：旧全仓门禁 1030 项、1 error、42 skipped，截止竞争错误并未因单项重跑通过而抹除。旧聚焦批次 53 项中 1 failure 的迟到流案例也保留在独立日志。最终门禁结果与这些历史尝试分别记录。

第一轮最终门禁也保留为失败：冻结提交 `60a4ac8a82b96aad3cf2852f652d23087d8c61be`，聚焦 146 项、3 failures、1 error、0 skipped，耗时 274.198 秒，发布与完整离线阶段未运行。失败涉及账本 gate 阻塞控制、迟到结算等待、Windows 截止时钟相位差和七字符流式夹具的持久化负载。修复后以独立运行身份重新验收，不把这轮失败改写为通过。

### 实际公共请求的指纹

输入、完整 messages 和 schema 均以键排序、`ensure_ascii=false`、紧凑 JSON 分隔符的 UTF-8 字节计算 SHA-256。`prompt_fingerprint` 是实际 messages 指纹；`prompt_layers_fingerprint` 继续使用既有层组合 JSON 序列化合同。审计字段未改变关闭新协议时的 provider 请求。下面只记录摘要，不记录 prompt 或正文。

| 版本 | 次序 | 角色 | messages SHA-256 | schema SHA-256 |
| --- | ---: | --- | --- | --- |
| control | 1 | explore | `a1e53a1832b39dca8f4604a054956260049a3350c35d4dbae3f0d6e6783dd30b` | `89fbfab654098a2025a0b69375f8dc8a7d8000391507639243712ca85a3a1473` |
| control | 2 | planner | `a615c2a69423f1204ce9c3ef5d3a18489373d0fef7f7b480a40824f59ce9e66b` | `47d696ba141a0df8916096620b35e322e402c59c41a80fca7b268a4c2ee2efee` |
| control | 3 | reasoner | `f65f322d82013b1590aeffcdf591768de6167bd81a3801786901a505cc1204ff` | `8836d710fac9532e05ef506e19a3da7fee87bb4a96b588396dd9842e83d986ef` |
| control | 4 | step_verifier | `5eb5a9608ea00c6db02fc29f45c525a632a1dce3cdc4db2e91467ba4252a6f79` | `f45df661a9c9ae45dee4ed363ed244c934a60b951d5cd4eeb2464b3fd2606eb7` |
| control | 5 | final_generator | `7edec7d1120bd57a9795298b7601c193370608e5daaf667d969c6c4a5ba5caa9` | `54ac692b082da9544bf9ee6ebc6c71cbf38396b8863aeb2e9d932de7f2cb6c10` |
| control | 6 | whole_solution_verifier | `ec419efe1c250699a230d440257bf60a9ed05cb8db21075409d9d84961ef5f06` | `edaea8b9ad088955e19001ef3b3bc6479028b604003ddf6dee7feeef56507aec` |
| candidate | 1 | explore | `ce22db06f6dbcc9936c870a54d278377d5465ea7bd49d9a4fd6c07a32c784761` | `89fbfab654098a2025a0b69375f8dc8a7d8000391507639243712ca85a3a1473` |
| candidate | 2 | planner | `f7730bc3d4bd982c24056c289e4342ce7d2b9ca578dbd238b633c7d8df0cc21a` | `0d6e42360a078e98bb2afc68599d74cec10f430942d3acdee6fe01b4ce45d89d` |
| candidate | 3 | planner | `a1d44463f0862d37d494237f5f1af85909eb828d8d9518e4609990cff8a044a6` | `0d6e42360a078e98bb2afc68599d74cec10f430942d3acdee6fe01b4ce45d89d` |
| candidate | 4 | reasoner | `c0851c3204a6e06bad4cfad54d64605a543ad48669c6900e3aa158ba3c7e2fe1` | `8170e8838f48e6f5ddc5d00cbe6e2aa0f3297a90d3bf713579916aed85348f77` |
| candidate | 5 | meta | `b963ddafe64879879ae3caa6e738e6b3594be14b6b3b8d12649838c0b71842f6` | `23bf67cd7744409fcc57990fcef50a23dcb190dd0cecbb2584678401f8e1efd3` |
| candidate | 6 | reasoner | `35a81706db89600eaa2e00442ce84082091c3f7ac30a37992b67640aaa0a2276` | `8170e8838f48e6f5ddc5d00cbe6e2aa0f3297a90d3bf713579916aed85348f77` |
| candidate | 7 | step_verifier | `e581dfe8a27fae76dcf549af215a3bc3e7ae36a6f6bec9a113aa4c75d9c5292b` | `f45df661a9c9ae45dee4ed363ed244c934a60b951d5cd4eeb2464b3fd2606eb7` |
| candidate | 8 | final_generator | `e032b35d9937a427f69b78ca53c15b8ea47cf4b455f6942fcf49d6da29c4abda` | `54ac692b082da9544bf9ee6ebc6c71cbf38396b8863aeb2e9d932de7f2cb6c10` |
| candidate | 9 | whole_solution_verifier | `6176578487815f32251469a3d6dc48227d66e6c3c50f927a03759f98d8b70ad5` | `edaea8b9ad088955e19001ef3b3bc6479028b604003ddf6dee7feeef56507aec` |

### Issue 验收定位

| Issue | 最终受控证据 |
| --- | --- |
| #116 | `test_star_job_parse_deadline_98`、`test_star_sqlite_timeout_contention_98`、`test_star_stream_late_race_98`、`test_star_ledger_lock_deadline_98`、`test_workspace_jobs`：传输与控制分层、唯一账本及事务回滚、迟到 settlement 与终态栅栏 |
| #117 | `test_cp05_public_job.CP05StreamingMatrixTest`、`test_star_product_streaming_recovery`、`test_solver_harness_streaming_activity`、`test_star_product_full_modes`：loopback 故障矩阵、unavailable、显式配置与脱敏 |
| #118 | `test_solver_harness_planner_checkpoint`、`test_cp05_public_job`、`test_star_product_recovery`：YIELD/FINAL、无进展与预算拒绝、真实进程重开及重复 resume |
| #119 | `test_cp04_public_faults` 六例、`test_solver_harness_reasoner_checkpoint`、CP05 公共纵切：Verifier 异议、Meta 指导、取消、旧 revision、依赖失效、审批 replan、真实回执和累计账本恢复 |
| #120 | 本节冻结来源、两版逐次实际指纹、严格 Reference、完整离线门禁、唯一实验文档追加归档及正式依赖图 |

表中模块均在最终门禁的聚焦或完整 discovery 中实际执行。六个 mutation probes 为故意绕过机制的负向验证，内部预期失败必须被捕获；最终探针命令退出码均为 0 才算通过。

本地完整逐项验收映射保存在 `requirements-proof-map.md`，最终日志与 JSON 状态保存在同一私有收尾证据目录。公开文档只记录脱敏摘要。

control 的输入指纹为 `092e01eab5073b10d01ca2de0d2464614c984f648e342da1de4228eb5127772e`，配置指纹为 `ab8942a128c8ccc5fc39e91e14b53c3ddc5777b8947d450d1b59ca83cac93527`。实际预算摘要：`{"charged_tokens":60,"http_attempts":6,"limits":{"max_http_attempts":12,"max_model_calls":12,"max_runtime_seconds":1100.0,"max_tokens":262144,"max_tool_calls":0},"logical_calls":6,"provider_known":{"completion_tokens":18,"prompt_tokens":42,"total_tokens":60},"provider_unknown_fields":{"completion_tokens":0,"prompt_tokens":0,"total_tokens":0},"reserved_tokens":0,"tool_calls":0}`。
candidate 的输入指纹为 `092e01eab5073b10d01ca2de0d2464614c984f648e342da1de4228eb5127772e`，配置指纹为 `19cffe90fe245695acc92779ca61289136a0b690a98e95c90a90b4ef42151256`。实际预算摘要：`{"charged_tokens":90,"http_attempts":9,"limits":{"max_http_attempts":12,"max_model_calls":12,"max_runtime_seconds":1100.0,"max_tokens":262144,"max_tool_calls":0},"logical_calls":9,"provider_known":{"completion_tokens":27,"prompt_tokens":63,"total_tokens":90},"provider_unknown_fields":{"completion_tokens":0,"prompt_tokens":0,"total_tokens":0},"reserved_tokens":0,"tool_calls":0}`。

逐次重算结果与公共 Evidence timeline 一致。两版实际 thinking 均未指定，传输为脚本化非流式 HTTP 响应。流式矩阵另用真实本地 loopback HTTP；两类证据均不属于 provider-live。

正式依赖已复核：`#116 → #117`、`#116 → #118 → #119`；`#117/#119 → #120 → #112 → #113 → #114 → #115 → #108 → #109`。`#110` 只在 `#109` 实际通过后开展，`#108` 还保留 `#106` 前置。本轮只关闭 #116–#120。

#112、#96、#97 和父规格保持开放。#112 原 `5/15`、10 项 `not_run`、unknown 身份与预留、原 deadline 和 Planner 3600 秒补充臂保持原样；本轮不消费登记、不恢复派发、不增加真实请求或预算。

### 唯一实验文档归档

既有唯一实验文档 `docs/experiments/star-timeout-thinking-on-plan.md` 的追加归档提交为 `ec0978dad96ae12bb142ffba6d5afa1ad22b0567`，分支 `docs/cp05-experiment-archive`，父提交 `42e36a76d6aff394578697daf80d10e89988ad56`。历史原文逐字节保留为前缀；原文 SHA-256 为 `1af38d13e8f9e394d32ed26ea560b199a26cb686e515467020aae36e819e5df2`，追加后 SHA-256 为 `89ba9beabab5179f00a81dcb4f240fd6e40d68b5692b198d017a4c579451363a`。该独立归档只改这一文档，未移动文档所属分支、写入原工作树或 D 盘；集成分支通过此提交与路径定位结果，不带入历史实验文档。私有 raw、state、ledger 保持原样。两个本地分支均未推送，未合并 main。
