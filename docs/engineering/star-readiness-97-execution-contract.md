# #97 v5 非流式批次执行合同（拟议）

状态：v5 执行合同草案，`draft_not_dispatchable`。用户最新指示拟议将原 Issue #97 合同中的“不得提高现有预算”调整为仅扩大 wall-clock 和单请求等待时间；这里记录的是本地提议，不修改远程 GitHub issue。2026-10-28 的两份已消费 manifest 和真实批次结果维持不变；不得对其续跑或重试。v5 未获 live API 授权，也未执行。源码绑定的待审阅预览为 `artifacts/issue-97-prereg/manifest-v5-reviewed-20261028.json`，交付身份及 hash 记录在 `artifacts/issue-97-v5-offline-20261028-r2/delivery.json`。

本轮已加入 v5 登记校验、provider adapter timeout、协调器全批 wall-clock 读取和独立一次性消费键，并新增独立 v5 回归文件。最终完整发布门禁 873 项通过、零失败、零跳过；测试接缝及六个旁路探针通过。具体源码身份、报告 hash 和覆盖限制见[核对状态](../evals/star-readiness-97-status.md)。冻结预览仍不可派发，必须针对该份具体登记取得授权。

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
