# Provider-live 协议与 readiness 补充记录

日期：2026-11-03。关联 #124、#127、#128。本记录补充[实验 CLI 阶段记录](showcase-experiment-cli-124-128.md)，保留旧记录作为当时状态。

## 验收范围

用户将答案稳定性的目标明确为“正常完成并给出符合格式的非空答案”，本轮不评价数学正确性，也暂不验收 usage。现有计量记录、未知预留、硬预算、整题审查和交付绑定继续保留；usage 未返回时不填零，也不改成已核实。

直接 SSE 返回正文只能证明对应请求完成。它不证明官方 `ReasoningAgent.solve` 或公共 Job 的完整执行、角色 JSON、自然规划、工具消费和最终文本绑定。此前带目标分类或辅助引理的困难题探测也不作为独立求解证据。

## #124：已执行的真实协议探测

全部请求通过实际 `InternStreamAdapter` 发往登记的 Intern S2 endpoint，配置固定为 `thinking_mode=false`、`temperature=0.2`、每次最多 32768 输出 token、900 秒逻辑调用截止、30 秒 socket 读取空闲截止、一次初始 HTTP 尝试。批次在调用前冻结请求、schema、消息结构和哈希，遇到传输未知、schema 不符或非 `stop` 结束立即停止。

| 本地批次目录（均位于忽略的 `artifacts/`） | 探测范围 | 结果 | 登记 SHA-256 |
| --- | --- | --- | --- |
| `issue124-protocol-probe-20261103` | Explore、final_generator、whole_solution_verifier；system/user 两条消息 | 3/3 PASS | `396fffcb69209a1044b2eda0005c81be7fd0d609284ff8e8d2f453b505bd20b0` |
| `issue124-layered-probe-20261103` | 同三种 schema；使用实际 `compose_request` 的三层注入，共五条消息 | 3/3 PASS | `c574bf4549cd802941750cf8114d0bd3477a9155518d15bccddb1b6cd5f256cf` |
| `issue124-multistep-protocols-20261103` | planner、reasoner、step_verifier、meta、explore_polish、researcher；五条消息 | 6/6 PASS | `9b130fd21393cf22aeecdf1d67a19467be59a0927f359e976f4f4cc07f871523` |

这 12 次均收到 HTTP 200、完整流式结果和 `finish_reason=stop`，独立调用 `schema_error` 核对对应角色 schema。usage 未观察到；本表的 PASS 仅限协议兼容范围。规划、推理、审查各自的探测使用固定上下文，不构成一次自然多步 Run。

普通两条消息批次的首个正文时间分别为 0.843、1.560、10.898 秒，完整响应结束时间分别为 4.690、4.446、14.878 秒。该探测的 attempt 投影没有最后正文时间字段，不能把完整响应结束时间冒充最后正文时间。公共 Job 的首末正文时间另由 stream activity 事件核对。

## #127：执行准备与实现缺陷

固定 Docker 镜像 `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d` 的实际隔离预检返回 `available=true`，回执保存在 `artifacts/issue127-docker-preflight/`。隔离预检不调用模型，不等于 readiness。

本轮发现实验 CLI 的 `retry=0` 限制与实际客户端的次数语义冲突：`InternChatClient.retry` 和流式 adapter 将该值作为总尝试数，零次无法发出初始请求。修复应允许显式登记 `retry=1` 的单次请求，继续拒绝大于一次的配置，并保留未知结果后不自动重发的规则。此项属于实现缺陷，不属于模型未通过数学题。

公共 CLI 简单题和自然多步 readiness 尚待下方追加真实结果；不得用上述角色探测代替。

困难样题采用 [IMO 2025 英文官方题面第 6 题](https://www.imo-official.com/assets/documents/problems/2025/2025_eng.pdf)的矩形覆盖问题，只提供题面；简单题为一次方程，中等题为四次方程。难度标签是选题判断，不是统计测得的模型难度。题面和运行输出仅保存在忽略的运行目录。

## #128：尚未实现的执行路径

目前 `run_pair` 仍只登记 `NOT_RUN`；公共 Job 没有接通单因素组件配置、baseline/variant 派发和逐臂独立核验。缺少该执行路径时不能报告配对失败或成功。#127 的自然多步 readiness 也仍是前置条件。

全功能 reference preset 要求 `skills` 和 `reexplore_after_replan` 等核心功能开启；直接关闭它们会被 admission 拒绝。实际配对接线需要明确实验入口、冻结并绑定两臂实际配置，同时保留审查、工具安全和交付约束，不能把受限模式或直接 Harness 测试冒充同配置公共 Job 对照。

## 公共 CLI 真实执行结果

以下是同日后续检查点，替代上文“尚待追加”的执行准备状态，不改写各旧批次本身。

| Run | 实际结果 | 判定 |
| --- | --- | --- |
| `issue127-simple-20261103-public-01` | 已返回答案并获整题 LLM 审查接受；`verification_mode=required` 仍要求更强的验证，Job 进入需要复核 | 配置与工程 readiness 目标不匹配；保留失败记录 |
| `issue127-simple-20261103-public-02` | 改用新冻结的 `auto` 模式；Job succeeded，157 字答案，整题审查和同文本绑定成立 | 原严格 usage 停止规则使批次 stopped，不冒充整批通过 |
| `issue127-medium-20261103-public-02` | 自然产生 5 步计划与逐步审查；总 Run 的 900 秒截止触发 `run_deadline_exhausted`，最终生成响应有返回但没有完成整题审查和交付 | 已执行、完整交付未通过；不作为数学错误或 NOT_RUN |
| `issue127-simple-20261103-public-03` | `auto`，显式 `usage_policy=observe_only`；批次 completed 1/1，192 字答案 | 独立 task/transport/coverage 均 PASS；usage UNKNOWN，不纳入用户本轮答案验收 |
| `issue127-hard-20261103-public-03` | 自然 Explore→planner→reasoner→step_verifier，四次 HTTP 均 200/stop；后续 researcher 调用在派发前被拒绝 | 完整多步未通过；77 字终止提示不算数学答案 |
| `issue127-medium-20261103-public-03` | 前一困难题停止后不继续派发 | NOT_RUN，不计为失败或成功 |

第二轮并没有在原 Run 内放宽验证方式。第三轮也没有修改旧 Run 的 deadline：新 manifest 将每次模型调用的逻辑上限保持为 900 秒、socket 空闲上限保持为 30 秒，将整条多步 Run 的预算设为 3600 秒。

简单题第三轮从首次调用派发开始，首个正文片段为 **0.938 秒**，最后正文片段为 **12.677 秒**，最后完整流响应为 **12.846 秒**。这些是包含本地审计开销的公共 Job 观测，不是纯 provider 吞吐测量。困难题第三轮对应 0.754、79.871、80.219 秒；最后一个片段属于步骤审查回复，不是最终数学答案。

困难题的真实停止原因是 `researcher` 的 `action=counterexample_check`，schema 指纹为 `9806bf844a1871e77a826e802027f93929767e99a7bd3bc1366318abf4be7590`。它不在当前 12 项登记中，运行时以 `provider_profile_unverified` 拒绝，`new_run_required=true`。恢复记录无未知调用、无未知工具；因此 CLI 的 `unknown_transport` 停止摘要不能解释成这次有未知 HTTP 结果。独立核验给出 task FAIL，transport/coverage UNKNOWN，保留原值。

当前 manifest 按角色只登记一个 profile，而普通 researcher 与 counterexample_check 的 schema 不同。这是接下来需要补齐的登记表达和实际兼容证据；提高输出 token 或 Run 时间不会解除这次派发前拒绝。#127 的完整多步 readiness 保持未通过，#128 保持未实现并受该前置阻塞。没有继续派发新的 provider 批次。

## 本轮代码与工程验证

本轮修复均位于显式 Showcase / 实验入口：

- `0de6d66`：允许真实客户端一次初始尝试的 `retry=1`，未知结果不重发。
- `595aa06`：只登记已探测的 12 个 schema/message-shape 组合。
- `c59b382`：保留账本已脱敏调用 ID，修复 Job 与报告/Evidence 之间再次哈希导致的身份不一致。
- `93413ee`：新冻结 manifest 可显式暂缓成功请求的 usage 验收；默认仍严格停止，未决请求和未知工具仍停止，最大预留与硬预算不变。
- `95f8e28`：只读核验理解真实 producer 的 `llm_whole_review_accept` 历史标签，保留已有 `accepted` 兼容和其余来源/审查/文本绑定要求。

这些切片已合入集成提交 `69315f1`。身份修复相关 22 项、usage 策略及实验回归 49 项、审查核验与公共 API 37 项聚焦检查通过；最后一次合并后另有 8 项新增测试通过。各组有重叠，不相加作为总测试数。Ruff 与空白检查通过，官方 `user_agent.py` 和 `implementations/` 与最新 `origin/develop` 比对无差异。

六阶段最终门禁仍在后台核验。首轮 `provider-followup-20261103-r3` 漏传 `MATHAGENT_TEST_PYTHON_IMAGE`，有 Docker 用例被跳过，不能作为严格最终通过。唯一后继进程 `follow_final_gate.ps1` 等待该轮退出后运行 `provider-followup-20261103-r4`；后者显式固定上述镜像 ID、启用 Docker 集成用例并要求 Reference 实际执行。结果由 30 分钟临时检查接管，完成或失败后追加本记录并删除检查；当前不声称最终门禁 PASS。

运行证据仍保存在 managed worktree `issue127-provider-readiness` 的忽略目录：冻结输入在 `.review/issue127-public-live-20261103*`，公共 Job、独立核验与脱敏证据在 `artifacts/experiments/`，诊断、首末流时间和服务 SQLite 在 `artifacts/issue127-public-live-20261103/`。原始输出、题面、数据库和凭证均未提交。

已有 [draft PR #129](https://github.com/RUSS0718/MathAgent/pull/129) 继续指向 `develop`；#124/#127/#128 尚未提前关闭，不声称数学能力提升。
