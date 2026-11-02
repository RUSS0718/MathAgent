# #97 v5 非流式批次执行合同（已消费）

本文保留 v5 已消费合同及其历史记录。末尾的 v7 小节是独立的本地提案，不改写 v5 或 v6 历史。

状态：用户授权后已执行并消费 v5。简单题在一次成功隔离计算后耗尽登记的工具预算，控制器停止，多步题未派发；具体结果见[核对状态](../evals/star-readiness-97-status.md)。本合同只扩大 wall-clock 和单请求等待时间，其他限额保留冻结值；没有修改远程 GitHub issue。此前两份已消费 manifest 与结果也维持不变，三批均不得续跑或重试。原待审阅预览为 `artifacts/issue-97-prereg/manifest-v5-reviewed-20261028.json`；独立已授权 manifest 为 `artifacts/issue-97-prereg/live-manifest-v5.json`，SHA-256 为 `c664754f9fdaa57fcd3b9a01d2cb35fef76df19d633ab54585e33b97cc376e64`。

本轮已加入 v5 登记校验、provider adapter timeout、协调器全批 wall-clock 读取和独立一次性消费键，并新增独立 v5 回归文件。调用前完整发布门禁 873 项通过、零失败、零跳过；测试接缝及六个旁路探针通过。门禁通过不代表真实批次通过。下文保留本次冻结时的规则，不允许借冻结或授权流程重新生成、复用已消费的 v5。

## 登记与身份

v5 使用一次性登记和独立归档目录，顺序为简单题 `simple-05`（Project Euler Problem 5）后多步题 `multi-04`（IMO 2025 Problem 4）。题面、来源、规范化 UTF-8 输入及 hash 见[登记草案](../experiments/star-readiness-97-preregistration-draft.md)。此前把 IMO 候选说成 Problem 1 是错误的；草案使用已核实的 Problem 4。两题均至多派发一次，且不得为触发某条模型路径而改题或改写提示。

冻结登记必须绑定 Intern S2、非流式请求、`star_reference`、`verification_mode=auto`、请求参数及完整 Reference 配置、精确题面与 hash、源码 Git revision/hash 和 dirty 状态、各级硬限及停止条件。完整题面只保存在忽略目录，执行源码仅保存题源与 hash，测试使用合成题。现有配置中只拟调整单请求 timeout；模型输出上限、客户端 retry、thinking、temperature、审查、工具及隔离设置保持原值。缺项、题面或配置漂移、身份不符、上限超额、关闭审查或隔离时拒绝启动。最终 manifest 必须在实现与离线验收完成后生成，以绑定实际源码身份。

## 执行与预算

全批最多 2 个 Run，按登记顺序各执行至多一次。每次派发前校验 token、logical call、HTTP attempt、题目工具和剩余墙钟额度；不足时停止，不降低门槛、不突破任一上限。每个 Run 通过预算准入后确定绝对截止，恢复不重置截止；题目准入预检计入对应 Run 时间。启动环境预检计入全批时间。

| 上限 | 简单题 Run | 多步题 Run | 全批 |
| --- | ---: | ---: | ---: |
| Run 数 | 1 | 1 | 2 |
| logical calls | 6 | 12 | 18 |
| HTTP attempts | 8 | 16 | 24 |
| 题目工具调用 | 1 | 3 | 4 |
| charged / reserved tokens | 32768 | 65536 | 98304 |
| wall-clock | 900 秒 | 3600 秒 | 4800 秒 |
| 单请求 timeout | 600 秒 | 600 秒 | 600 秒 |

环境预检最多 3 次，计入批次总时间；含预检的工具调用合计不超过 7 次。单请求最大输出仍为 8192 tokens，客户端 `retry=3`，其余模型与 Reference 参数保持登记草案所列原值。4800 秒全批 wall-clock 从服务启动前开始，包含环境预检、运行、等待和退避。请求 timeout 与 Run / 批次 deadline 同时生效，先到者结束本地等待并停止新增派发；本地截止不能证明 provider 已取消处理。后台迟到读取只用于原 attempt 对账，不恢复求解或覆盖终态。此处增加 wall-clock 仅为慢请求提供更多等待时间，**不能保证模型自然进入非快通道或产生步骤证明**。未触发目标记为 `not_covered`。等待额度的观测依据与估算见[登记草案](../experiments/star-readiness-97-preregistration-draft.md#模型条件与拟议预算)。

缺失的 provider usage 不得视作零；保留预留并停止。charged 已包含 reserved，不重复相加；实际费用未知时记 `null`。传输未知不得自动重发。完整但协议非法的响应与传输未知分别记录。任何未知、失败、取消、硬限、源码或配置漂移、账本或交付绑定缺陷发生后停止新增派发，保留已发生 attempt 与证据。迟到用量只补记原 attempt，不得让迟到文本覆盖终态；不得续跑、换题、提升上限或复用归档目录。

## 冻结前验收与授权

冻结 v5 前，用离线与本地 HTTP 替身验证预算准入、timeout、Run / 全批 deadline 传播、恢复不重置、超限停止以及失败后不再派发。对同一源码身份运行适用的聚焦测试和仓库发布门禁，并记录可复核结果。脚本 provider 或故障注入结果只证明受控工程路径，不得称为真实 provider 验收或能力提升。

完成上述实现及验收后，重新生成并审阅精确 v5 manifest，状态仍为不可派发，直到用户针对冻结后的具体登记再次明确授权 live API。获得该授权后才可执行登记中的一次性样本；执行结果分别记录阶段、调用来源、provider usage、预留、停止原因、审查与交付绑定，以及数学判定。内部 LLM 审查不等同数学证明。旧合同与旧结果不回写；任何与原 Issue #97 的冲突仅作为本地 v5 拟议调整保留，远程 issue 未变更。

冻结和授权是两个独立操作：`freeze-live` 仅写出不可派发的预览 manifest 及其 hash；`authorize-live` 必须接收该预览的精确 hash 和显式确认，核对源码身份后另写已授权 manifest，不覆盖预览。`run-live` 仍须接收已授权 manifest 的精确 hash 和执行确认。不得在冻结命令内预先登记授权日期或把草案标记为已授权。

## #97 v7 本地提案（不可派发）

本节记录 2026-10-28 更新后的本地目标。它不替换 GitHub Issue #97 的原始要求。本次只更新本地文档，不对 GitHub issue 执行修改或关闭操作。

### 原始要求与本地目标

GitHub [Issue #97](https://github.com/RUSS0718/MathAgent/issues/97) 的原始合同要求完整 `star_reference` 配置，并禁止提高已登记预算。v7 提案与原预算边界不同，必须作为独立的新版本审阅。已消费的 v5 与 v6 登记、授权和结果保持原样。

更新后的本地目标是用一次多步 Run 验证原 STAR 架构能完成运行并返回答案。保留 `solver_mode="star_reference"` 和完整 `STAR_REFERENCE_CONFIGURATION`。九项核心功能继续开启：`final_generation`、`final_solution_review`、`local_code_tool`、`meta_guidance`、`persistent_sessions`、`reexplore_after_replan`、`skills`、`star_routing` 和 `stream_recovery`。`candidate_registry` 与 `best_effort` 继续排除。

### v7 候选预算

下表是新版本提案的硬上限。它们不保证每次请求都会用满预算，也不保证模型产生正确答案。

| 范围 | 限额 | v7 候选值 |
| --- | --- | ---: |
| 单次请求 | `max_output_tokens` | 16,384 tokens |
| 单次请求 | `request_timeout_seconds` | 900 秒 |
| 单个 Run | `logical_calls` | 24 |
| 单个 Run | `http_attempts` | 72 |
| 单个 Run | `problem_tool_calls` | 8 |
| 单个 Run | `charged_tokens` | 524,288 tokens |
| 单个 Run | `wall_seconds` | 7,200 秒 |
| 单 Run 批次 | `runs` | 1 |
| 单 Run 批次 | `environment_preflights` | 3 |
| 单 Run 批次 | `tools_including_environment` | 11 |
| 单 Run 批次 | `wall_seconds` | 7,500 秒 |

单 Run 批次还沿用单 Run 的 24 次逻辑调用、72 次 HTTP 尝试、8 次题目工具调用和 524,288 charged tokens 上限。环境预检最多 3 次。题目工具与环境工具合计最多 11 次。

### v7 已消费状态与验收结果

v7 已依据本聊天用户既有授权完成源码冻结、精确 hash 核对和一次真实执行；不能再次派发。上述预算是实际执行上限，历史 v5/v6 不改写。两套同源码门禁各 920 项通过、零失败、零跳过，六组旁路探针通过。实际单请求输出上限 16384、timeout 900 秒均已核验。

多步 Run 的第一次 Explore 成功，第二次 Explore 等待 900 秒后 timeout，终态 `unknown_transport`；保留 24342 reserved tokens 和一个 unknown / unresolved attempt，未自动重发。没有完整数学答案、整题审查或交付绑定，不能认定真实闭环通过。精确源码、manifest hash、用量及证据路径见[核对状态](../evals/star-readiness-97-status.md)。

公开输出入口 `run-live --answer-output` 将正文保存到 `artifacts/issue-97-answers/` 的独立文件，脱敏归档不保存正文。写入失败先保留已观测用量与交付证据，再停止。此次文件只有失败提示，不是数学答案。当前需要诊断 provider 等待超时；不得续跑已消费的 v7。
