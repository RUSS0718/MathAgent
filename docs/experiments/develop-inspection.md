# develop 基线审计：Intern S2 数学智能体研究与主观展示

审计日期：2026-10-21（UTC）  
固定基线：`5b0e1912e1cc82d7ab1ecd3bcb8ea5ffc10933ae`（`develop`）  
状态：源码审计与建议；不是新能力验收报告，也不是实现计划。

## 1. 范围与证据口径

本次审计覆盖 Showcase 的模型适配、工具协议、预算、取消与恢复、验证、Evidence、Profile、评测脚本和对应测试。目标是为 R1 局部动作收益路由、R2 Discovery/Execution 反事实控制、R3 UNKNOWN 诊断、R4 带作用域的证明缓存、R5 最终接受风险提供真实工程落点，并优先排除影响主观展示可信度的基础缺口。

本次读取了 `AGENTS.md`、`docs/README.md`、`GLOSSARY.md` 和 ADR-0001 至 ADR-0006，以及下文引用的源码与测试。已用 `git rev-parse HEAD` 核实上述 SHA；初次检查的工作区为干净的 `develop...origin/develop`。本次未运行测试、服务、模型调用或付费 API；未读取 `.env` 或凭证。唯一新增文件为本文，不修改产品代码，不提交 Git。

证据分为四种，避免把源码存在、历史通过和当前实测混为一谈：

- **源码事实**：可在固定 SHA 的指定文件与行号直接检查。
- **静态推断**：由调用关系或数据流推导的风险，尚未通过运行复现。
- **历史证据**：仓库已有验收记录；只对记录标注的版本与环境有效。
- **建议**：下一阶段可采用的接口或验收条件；不表示已经实现。

本文所有 `路径:行号` 均相对仓库根目录，行号对应上述固定基线。后续代码变化后，应通过符号名重新定位。

### 已有约束

`AGENTS.md:9–20` 将客观路径和主观产品路径分开，要求新增工程能力默认关闭并通过显式入口开启。`AGENTS.md:52–71` 要求遵循 Matt Pocock 流程，并在产品实现前形成可审阅的 PRD、技术设计、任务合同与验收案例。`AGENTS.md:83` 要求 Python 检查使用 `uv run`。当前需求应沿此边界增加 Showcase 能力，不直接重写官方入口或官方默认预算。

本次仓库文件扫描未发现随仓库提交的 `SKILL.md`；这仅说明本仓库没有发现技能文件，不判断当前工作环境是否已安装外部 Matt Pocock 技能。

## 2. 已有能力应直接复用

| 能力 | 实际接口与位置 | 可以复用的部分 | 当前证据边界 |
|---|---|---|---|
| Intern S2 传输 | `llm_client.py:48–107`，`InternChatClient.chat(...) -> str` | 现有鉴权、端点、超时、重试、逐请求 reasoning 开关、脱敏诊断 | 源码默认模型为 `intern-s2`，不等于本次已验证线上模型行为 |
| 模型归一化 | `showcase/adapters.py:31–137`，`ToolRequest`、`ModelResponse`、`InternModelAdapter.complete` | 文本工具标记解析、工具请求归一化、结构化错误 | 当前真实客户端路径的 usage 和工具 schema 有缺口，见第 4 节 |
| 工具结果回传 | `showcase/adapters.py:50–82`，`ContinuationTransport.continue_` | 可替换的 continuation seam、已有离线合同 | 当前 `role=tool` 消息是否被 Intern 端接受未由本次验证 |
| 有状态执行图 | `showcase/graph.py:42–160`，`LoopState`、`AgentDecisionProvider.decide`、`ToolExecutor.invoke`、`LangGraphExecutionLoop` | Agent/工具/验证节点、事件、计数、checkpoint sink、review resume | 不是当前 Workspace live 的实际执行器；不是任意推理前缀恢复 |
| 当前 live 产品执行 | `showcase/live_pipeline.py:51–120`，`LiveAgentPipeline.run` | Planner、Solver、工具 continuation、Verifier、Synthesizer 的既有角色链 | 固定链；没有动作路由、反事实分支或持久化中间执行状态 |
| 工具注册与限制 | `showcase/tools.py:43–186`，`ToolRegistry.register/invoke` | 工具白名单、Profile 限制、输入上限、超时、结果归一化 | 调用计数当前属于共享 Registry 实例，见 P0-03 |
| 有界精确数学检查 | `showcase/polynomial.py:16–69`，`PolynomialChecker.check` | 有理数多项式候选代回、定义域、重复项、错误分类、输入 evidence ID | 不证明完整解集；不等于 Lean 证明 |
| 验证扩展点 | `showcase/verification.py:10–32`，`VerificationHook.verify`、`VerificationResult` | `pass/conflict/unknown` 合同和 findings | 当前实现是轻量一致性检查，无风险校准或证明语义 |
| 会话与 Job | `showcase/workspace.py:636–729`，`WorkspaceService` | 异步入队、幂等键、owner 检查、公开状态、取消终态 | 取消计算与恢复上下文的语义尚不完整 |
| 存储与事件 | `showcase/storage.py:25–188`、`showcase/workspace.py:785–837` | SQLite、append-only 事件、最新 checkpoint、artifact 索引、SSE 游标重放 | 尚无版本化 claim DAG、分支快照、作用域证书缓存 |
| 报告与回放 | `showcase/evidence.py:14–50,121–154`，`EvidencePackExporter`、`replay_evidence` | Evidence/report 版本、模式标签、公开工具关联、脱敏回放 | 报告重放不执行验证；没有最终接受对象的证书绑定 |

### 两条执行路径必须区分

**旧 Run 路径**：`create_live_service` 在 `showcase/server.py:158–170` 创建 `InternAgentAdapter + ToolRegistry + LangGraphExecutionLoop + RunService`。`RunService.resume_run` 从 SQLite 最新 checkpoint 交给执行图恢复（`showcase/run_service.py:231–252`）。

**当前 Workspace live 路径**：`create_live_pipeline` 在 `showcase/server.py:173–189` 创建 `LiveAgentPipeline`；`WorkspaceService._execute` 直接调用它（`showcase/workspace.py:746–756`）。这条链不经过上述 LangGraph 执行器。

ADR-0002 在 `docs/adr/0002-langgraph-deepagents-boundary.md:9–25` 指定由 LangGraph 管理 Run、checkpoint、interrupt、resume 和预算。**源码事实是两套执行器并存；静态判断是新研究控制层需要先明确归属。**建议在新 ADR 中说明保留、统一或适配两条路径的选择，避免第三套执行循环，也不要把旧图的恢复能力直接标在当前 Workspace live 上。

## 3. Intern S2 API 的已知接口与尚未核验能力

### 源码已支持

`llm_client.py:15–18` 定义当前默认端点与 `intern-s2`；`chat` 已接收 `reasoning_mode="inherit"|"off"|"on"`、`thinking_mode`、`timeout_seconds`（`98–107`）。客户端已有 `finish_reasons`、`completion_tokens`、`response_metadata`、`latencies` 和 `request_diagnostics`（`76–96`），并记录 prompt/completion/total tokens、请求耗时及 reasoning content 是否存在和长度（`184–224,259–274`）。

因此，不需要新建 Intern HTTP 客户端。R1/R2 可以先设计围绕同一客户端的逐请求选项进行实验，但“开关被发送”与“线上模型提供稳定、可比的不同计算模式”必须分开验收。

### 尚未建立的能力

当前公开 `chat` 返回普通 content 字符串，不返回隐藏 reasoning 文本；也未提供 token logprobs、熵、provider seed、流式前缀中断或隐藏推理恢复接口（`llm_client.py:98–107,196–224`）。不能据此宣称已具备对模型隐藏 CoT 的原位 Discovery/Execution 干预。

建议 R2 的最小可检验对象为**公开计划摘要、显式数学步骤或结构化候选状态**。不同动作从同一个公开状态发起新调用；其成本包括上下文重发。若后续要使用更细的 provider 控制能力，应先独立做能力 spike。

另，`llm_client.py:21–36` 在模块导入时读取仓库 `.env` 并写入进程环境。本次仅查看源文件，未导入该模块。后续离线测试应使用注入 seam，避免为了检查接口而无意加载凭证或调用提供方。

## 4. P0 缺口：先使执行和证据可信

以下优先级为**审计建议**，面向可复现研究和可靠展示；这些尚不是已运行复现的缺陷报告。

### P0-01：真实客户端未收到完整工具协议

**源码事实。** `InternChatClient.chat` 无 `tools` 参数（`llm_client.py:98–107`）；`InternModelAdapter.complete` 仅当客户端接受该关键字时才转发 tools（`showcase/adapters.py:120–125`），没有降级为提示中的 schema。`ToolRegistry.describe` 只返回名称、capabilities、Profile、超时和 experimental 标志，没有参数 JSON Schema（`showcase/tools.py:117–129`）。Solver 却被要求使用“registered schema”（`showcase/live_pipeline.py:279–295`）。

`ModelContinuationTransport` 将一个 `role="tool"` 的 JSON 消息直接接在原 messages 后，没有构造对应的 assistant native tool call 与 tool_call_id（`showcase/adapters.py:72–82`）。

**静态推断。** Fake 中预写的合法工具请求不能证明真实 Intern 能稳定生成合法参数，也不能证明提供方接受当前 continuation 消息序列。不能断言线上一定拒绝，但目前没有闭环证据。

**建议落点。** 在现有 `ToolSpec/InternModelAdapter/ContinuationTransport` 边界明确一种可实际支持的协议：版本化文本 JSON action 协议或经验证的 native tools 协议；工具参数 schema 只维护一份。先覆盖请求合法性、解析失败、错误工具、结果回传及请求关联，再做 3 题 × 2 次真实闭环能力验收。

### P0-02：usage 丢失，逐请求选项与动作元数据未贯通

**源码事实。** 当前客户端返回 `str`（`llm_client.py:224`），而 `_extract_response` 对字符串返回空 usage（`showcase/adapters.py:338–344`）。`complete` 只向当前客户端传递 temperature/max_tokens；`metadata` 没有使用，也没有转发客户端已支持的 reasoning_mode 或逐请求剩余超时（`showcase/adapters.py:105–137`）。Pipeline 传入的角色 metadata 因此未进入该调用记录（`showcase/live_pipeline.py:455–469`）。

**静态推断。** 不能用当前 `ModelResponse.usage` 可靠比较动作成本、计算 token 预算或构造单位成本收益标签。单纯在共享客户端上读取 `last_response_metadata`，还需要解决并发任务的对应关系，不能默认最后一次响应属于当前 Job。

**建议落点。** 复用客户端已有诊断，增加请求作用域的响应 envelope 或安全桥接，使逻辑调用、实际重试、Run/Job、角色、动作、usage 和模型标识有稳定关联。显式记录 usage 缺失而非填作零成本。沿适配器透传 reasoning_mode 与剩余 deadline；保持官方默认路径不变。

### P0-03：Registry 工具计数跨 Run 共享

**源码事实。** `ToolRegistry` 默认 `max_calls=8`，`_call_count` 保存在实例上（`showcase/tools.py:57–68`），`invoke` 直接累计该计数，未按 Run 分桶（`149–151`）。`create_live_pipeline` 创建一个 Registry（`showcase/server.py:173–189`）；Workspace 持有同一个 pipeline，使用两个 worker（`showcase/workspace.py:648–658`）。

**静态推断。** 不同 Job 会共享这一生命周期内的 8 次上限；并行调用的计数也没有显式锁保护。这会污染预算对比，并使连续演示在此前任务已消耗次数后出现工具预算耗尽。

**建议落点。** 将工具声明与每 Run 的消耗账本分离，或通过工厂创建 Run 作用域的执行上下文。不要靠运行前重置共享 `_call_count`，那会产生任务间竞态。验收至少覆盖两个不同 Run 的额度隔离与并行消耗。

### P0-04：预算只覆盖部分调用，未形成统一成本与 deadline 合同

**源码事实。** `PipelineBudget` 只有逻辑 model calls、tool calls 与运行秒数（`showcase/live_pipeline.py:32–38`）；每次 `_complete` 递增一个逻辑调用（`455–469`）。Factory 分别配置每请求 max_tokens、timeout 和 retry（`showcase/server.py:179–187`）。Pipeline 没有累计 token 字段，也没有将客户端重试归入实际请求上限。

运行时限在部分节点入口检查（`showcase/live_pipeline.py:244,277,346,395,421,471–473`），没有把剩余总时限交给当前请求；工具之后的 continuation 也没有独立的 `_ensure_runtime` 检查（`308–322`）。最后一次模型调用结束后不再检查总 deadline（`119–139`）。

**静态推断。** 单个同步请求或其重试可能越过总时限；仅统计逻辑调用无法给出物理请求次数和总 token 上限。当前 `max_tool_calls=2` 也不代表支持两次顺序工具操作：continuation 再请求工具会直接 review（`323–328`）。旧图同样在成功工具之后拒绝第二个工具请求（`showcase/graph.py:258–264`）。

**建议落点。** 定义 Run 级账本，区分逻辑动作、provider attempts、已知 tokens、工具调用与 wall time；请求前检查、请求后结算；失败、重试、取消均保留消耗。研究若需要多次局部动作，应显式修改既有“一次工具 + 一次 continuation”的合同，而非仅调大 budget 配置。

### P0-05：取消是公开状态终止，不是计算停止

**源码事实。** `cancel_job` 仅调用存储层控制（`showcase/workspace.py:723–729`）；存储层设置 canceled 并保留幂等终态（`344–386`）。迟到事件与完成结果会被忽略（`421–435,460–465`）。但 live `pipeline.run` 没有 cancellation 参数；Workspace 未在它内部或后续模型请求前检查取消状态（`746–756`；`showcase/live_pipeline.py:67–74,455–469`）。

**静态推断。** 用户看到 canceled 后，已运行的 provider 请求以及流水线后续模型调用仍可能继续消耗预算。现有终态保护本身应保留。

**建议落点。** 在共享执行上下文提供取消信号，至少保证取消后不发起新模型/工具动作；对已在途请求明确记录“不可撤回/结果忽略”的语义。是否能真正中断提供方请求需要 API 能力证据，不能仅以 Future.cancel 或 UI canceled 宣称实现。

### P0-06：恢复不是任意 live checkpoint 续算

**源码事实。** Workspace resume 只允许 waiting_input（`showcase/workspace.py:344–386`）；传入的 answer 仅参与请求 digest，没有保存为后续模型输入（`710–720`）。当前等待输入分支位于 fake 路径，live 分支提前返回（`746–769`）。重启时 queued/running/waiting_input 都改为 failed/needs_review（`388–399`）。SSE 游标恢复只读取已持久化事件（`798–837`）。

旧 `LangGraphExecutionLoop.resume` 则把 `next_node` 重置为 agent 并保留原状态（`showcase/graph.py:186–201`）；落盘 checkpoint 会移除 pending tool arguments（`413–419`），工具记录不含完整返回值（`315–329`）。最新 checkpoint 为替换式保存（`showcase/storage.py:142–170`）。

**静态推断。** 当前不能宣称 Workspace live 已支持反事实分叉、精确局部回滚或进程重启后从工具前安全恢复。持久化的 `time.monotonic()` 数值（`showcase/graph.py:171,489–491`）还需明确定义跨宿主/重启后的预算语义，不能假定它是可迁移的绝对时间。

**建议落点。** 在现有 Store/Run 状态模型上定义可恢复的公开任务状态、已结算动作 ID、剩余预算、用户补充信息与版本。区分事件重放、人工 review 后重跑、公开前缀续算和精确恢复。远端动作是否已发生不明确时，保留待复核语义，避免不受控重放。

### P0-07：最终答案没有与验证对象、证据 hash 绑定

**源码事实。** Verifier 检查的是 Solver candidate（`showcase/live_pipeline.py:99–108,386–408`），随后 Synthesizer 发起新的模型调用生成最终文本（`410–453`）。最终状态接受仍使用前面的 verification（`119–127`）。没有对最终文本再验证，也没有输出对象 hash 或“只允许格式化且数学内容不变”的强合同。

`PolynomialChecker` 的 evidence ID 是结构化检查输入的 hash（`showcase/polynomial.py:160–162`），并非最终答案 hash。轻量 verifier 在拿到 polynomial 结果后直接采用其 candidate_status（`showcase/verification.py:41–65`），没有把被检查候选与最终声明逐一绑定。

**静态推断。** 即使工具正确，也不能据此认定 Synthesizer 最后输出的所有数学结论都被该证据支持。这是 R5 最终接受风险研究前必须先固定的对象定义。

**建议落点。** 定义最终 artifact/claim 的规范化表示与 hash，把 certificate、适用范围、checker 版本和 acceptance decision 绑定到该对象。若合成改变数学对象，应重查或降级为未验证。先建立确定性绑定，再研究统计风险阈值；不能用对中间候选的检查替代最终接受标签。

### P0-08：工具证据只经摘要传递；手动检查会覆盖 Job 结果

**源码事实。** Live 工具记录保留截断至 1000 字符的 result_summary，没有完整结构化 value（`showcase/live_pipeline.py:360–384`）；Verifier 从记录中读取结果（`397–398`）。`LightweightVerificationHook` 支持从 summary 解析 JSON（`showcase/verification.py:41–59`）。

手动 `record_verification` 用 `{checker, result}` 替换整个 `workspace_jobs.result_json`（`showcase/workspace.py:505–513`）。Job report 则从同一结果字段读取 final_response、tool_results 和 verification（`showcase/flask_app.py:549–581`）。

**静态推断。** 长结果的 JSON 摘要可能被截断，不能当作持久化证书。手动检查后，原最终答案和完整工具关联不再位于 report 预期字段；报告可能丢失这些信息。

**建议落点。** 持久化有界、结构化、脱敏的 certificate 或 artifact 引用，摘要只负责展示；追加检查结果时合并/版本化，不覆盖原答案。用“完成 Job → 手动检查 → 报告仍有原答案与新证书”作为公开 API 验收案例。

### P0-09：节点耗时是常量，不能用作研究成本证据

**源码事实。** 所有 `node_end` 的 `duration` 固定为 `0.0`（`showcase/live_pipeline.py:475–499`）。工具执行另有 duration_seconds；客户端也已有逐请求耗时，但未在 Pipeline 中聚合。

**静态推断。** 目前图节点耗时只能当占位字段，无法用来解释实际动作收益、延迟或预算分配。

**建议落点。** 用真实单调计时记录节点开始/结束，区分排队、模型尝试、工具、总 wall time，保留运行边界与重试关联；字段无法测量时标注缺失，不填零。

## 5. 验证能力和 Profile 的真实边界

### 多项式 checker 可以作为 R3 的第一个受限域

`showcase/polynomial.py:72–132` 约束 schema version、变量、1–4 次多项式、有理数字符串、候选和定义域。结果分别给出 `candidate_status` 与 `coverage_status`。候选全部代回通过时，coverage 仍可为 unknown（`16–69`）；这一点已有测试名明确体现（`tests/test_polynomial.py:16–23`）。

`LightweightVerificationHook` 的一般 pass 还可能只表示答案形状及工具结果一致（`showcase/verification.py:67–80`）。因此不能把 pass 统一翻译成“数学证明完成”。当前 required 检查只看 verification.status，而非 coverage（`showcase/live_pipeline.py:121–125`）；提示中的“complete pass”比实际保证更强。`verification_mode="off"` 目前也仍会进入 verifier，主要差异仅是 required 的拦截条件（`91–125`）。这两个模式语义建议在规格中先统一。

本次已读模块与依赖声明中未发现 Lean/mathlib 执行器、自然语言 formalizer、证明搜索、作用域推理或校准器。不能将 polynomial 的 schema/domain unknown 直接命名为“Lean 翻译失败”或“证明预算不足”。可先做有来源的 UNKNOWN 分类，再扩展新的检查后端。

### Profile 只有已实现合同才能宣称可运行

`showcase/profile.py:5–23` 只有 `official` 和 `showcase_mvp` 常量，`ensure_showcase_profile` 仅接受后者。`GLOSSARY.md:5` 的 research profile 属于术语描述，不能据此认为已有可运行研究 Profile。建议沿现有分离机制明确实验配置入口与默认关闭策略，不重建一套与产品隔离规则无关的入口。

## 6. 五个研究方向的最小工程落点

下表是建议，未新增任何组件。研究需要共享可靠请求账本、公开状态和证据对象，避免每个方向独立实现一套工具/模型/事件系统。

| 方向 | 优先复用的 seam | 最小新增合同 | 当前不能宣称已具备 |
|---|---|---|---|
| R1 局部动作收益路由 | `InternModelAdapter.complete`；`AgentDecisionProvider.decide`；`ToolRegistry.invoke`；已有 Evidence | 对同一公开前缀定义少量离散动作、动作前可见特征、剩余预算、实际成本与后续结果；错误风险/影响范围只能是前缀预测值，真实影响只作标签 | 固定 Planner→Solver 链不是收益路由；缺少配对动作收益、探索概率和学习路由器 |
| R2 DE 反事实控制 | 现有客户端逐请求 reasoning_mode；公开 plan/candidate；Store 和 graph checkpoint seam | 公开状态 ID、parent/fork ID、独立动作调用、同预算比较、完整上下文重发计费；明确动作与状态标签来自何时 | 不支持隐藏 CoT 的原位暂停/续算；当前两条执行器均无反事实分支合同 |
| R3 UNKNOWN 诊断 | `VerificationHook`、`PolynomialChecker`、Registry 和结构化 findings | UNKNOWN 来源枚举、适用域、诊断动作、后续修复是否成功及成本；先从 schema/域外/证据不足开始 | 没有 Lean 翻译/证明搜索时，不能使用相应失败类别作实测标签 |
| R4 带作用域的证明缓存 | SQLite artifact 索引、已有 polynomial 输入 hash、VerificationHook | claim 与依赖 ID、假设作用域、规范化输入、checker 环境版本、certificate、失效/重检规则 | 当前 hash 只标识检查输入；最新 checkpoint 和报告回放不是可验证证明缓存 |
| R5 最终接受风险 | 最终输出阶段、VerificationHook、Evidence exporter、既有报告 API | 最终接受对象 hash、风险模型/阈值版本、校准集来源、accept/abstain、随机审计和选择概率；区分错误标签与 unknown | 没有最终输出证书绑定和校准协议；中间 candidate pass 不提供最终接受风险保证 |

**工程判断。** 首个可展示切片可复用已有 UI、SSE、工具和报告，将少量明确动作、成本、证据及最终接受状态贯通。R3 可先在受限多项式域完成真实诊断。R4 如要研究正式证明而非一般缓存，需另行安装并固定 Lean/mathlib/checker 环境。R5 的最终对象绑定是基础正确性工作；其后的统计保证需要独立数据和选择后评估。五个方向的论文价值与最终实施顺序仍应由研究协议和成本证据决定，不能根据组件数量排序。

## 7. 现有测试和评测可以证明什么

### 源码中已有的测试 seam

| 测试文件 | 已有覆盖主题 | 对新工作的边界 |
|---|---|---|
| `tests/test_adapters.py:16–70` | 注入 FakeClient、文本工具标记、结构化错误、DeepAgents 接口 | 不验证实际 Intern tools 参数或 continuation 协议 |
| `tests/test_live_pipeline.py:13–76` | ScriptedModel、角色节点、配置预算、工具 continuation 与脱敏 | 不验证 usage 聚合、真实耗时、取消后停止发起请求或最终重写绑定 |
| `tests/test_live_tool_continuation.py:9–74` | 合法 polynomial 请求、结果关联、required 无工具、第二次工具请求被拒 | 合同明确只有一次工具闭环；真实生成仍待能力验收 |
| `tests/test_graph_service.py:29–60` | SQLite checkpoint 与 review resume | 覆盖旧 Run 图，不等于当前 Workspace live 精确恢复 |
| `tests/test_job_control.py:32–112` | 幂等、取消终态、waiting_input resume、重启 needs_review | 主要是本地状态合同；不证明 provider 取消、用户 answer 生效或 live 分支续算 |
| `tests/test_polynomial.py:16–91` | 候选 pass/conflict/unknown、schema、域、外部案例矩阵 | 明确不证明完整解集 |
| `tests/test_reports.py:29–75` | 稳定报告、回放不调用提供方、Job 报告来源 | 没有发现“手动校验不覆盖原最终结果”的对应测试 |

本次**没有执行上述测试**；表格说明代码中存在的测试意图，不表示它们在当前 SHA 已通过。对“未发现覆盖”的判断限定于本次审阅文件和相关符号搜索，后续实现者应复查完整套件。

`scripts/check_test_seams.py:14–22` 禁止产品合同测试直接依赖 `_execute`、`store`、`start_job`、`complete_job`、`mark_waiting_input` 等内部属性。新增测试宜通过已有注入接口、公开 API 和受控 fake 达到边界情况，不依赖私有 worker 操作。

### 历史验收证据与脚本限制

`docs/evals/v0.2-release-evidence.md:3–11` 记录的是 2026-10-17、集成提交 `ee5c00b` 的 engineering-preview，不能当作本次基线的重新实测。该记录写明 AC-06 真实 Intern 工具闭环 unavailable；其 92 项测试通过是历史结果（`27,41`）。

AC-06 要求 3 道需计算文本题各执行 2 次真实 Intern 任务，同时观察合法工具请求、Registry 执行、continuation 和 Evidence 关联（`9,22`）。`scripts/run_capability_probe.py:16–31` 调用的是旧 `create_live_service`，并未覆盖当前 Workspace live pipeline。因此后续能力验收必须指明实际产品路径，不能仅运行旧 probe 即证明新展示链可用。

`scripts/check_showcase_release.py:66–78` 还把 release 状态限制为 preview/unavailable，把 AC-06 限制为 unavailable/blocked，把 math_eval 限制为 planned/unavailable。这是当前防止夸大能力的门禁。获得新证据后，应在新版本合同下更新门禁与证据，而不是绕过检查或直接把状态改成 pass。

独立数学评测仍是计划：至少 20 道与开发分离、人工核验的公开文本题，记录源/hash/模型/预算/正确性/工具/检查覆盖/误报漏报/耗时/usage（`docs/evals/v0.2-release-evidence.md:52`）。该文明确没有数字结果。本文不据工程测试推断数学正确率或研究收益。

## 8. 已观察到的 setup 边界

- Python 合同为 `>=3.11,<3.13`；基础数学库为 SymPy 1.13.3、mpmath 1.3.0；Showcase 已声明 Flask、LangGraph 1.2.15、DeepAgents 0.7.25（`pyproject.toml:5–28`）。复用现有依赖与安装流程，不为同一功能再引入执行框架。
- Live factory 已提供 Showcase 独立 max_tokens、timeout、retry、model/tool call 与 runtime 配置（`showcase/server.py:179–187`）。这些配置尚不等于统一 token/deadline 账本，也不是逐动作实验配置。
- Intern 凭证是否可用、指定 reasoning 模式在线是否有效、本机依赖是否已完整安装、提供方如何接受工具消息，本次均未实测。仅在受权能力 spike 中核验，不在文档中填作已完成。
- 正式证明相关环境、作用域证书格式、离线研究数据版本、训练/校准/测试按题隔离、随机审计与实验日志字段尚需单独设计。当前仓库已有工程数据存放与脱敏边界，应沿用 `artifacts/<run_id>/` 等既有约定；不可把原始提示、隐藏推理或凭证塞入公开 SSE/Evidence。
- 当前最值得保留的是现有前端、会话、幂等 Job、SSE、错误状态、工具、报告和回放。这些已提供主观展示载体。新增研究切片应补齐动作与证据语义，而非重造 UI 或传输层。

## 9. 交给下一阶段设计的审计结论

已有组件足以承载一个小而完整的研究展示，但当前能力不能直接标成“可恢复、按成本路由、带证明缓存和最终风险保证”的数学智能体。

建议在 PRD/ADR/规格阶段先冻结以下可审阅决定：执行状态由哪条既有路径负责；真实 Intern 工具/action 协议；请求与 Run 账本；取消及恢复的精确定义；公开中间状态；最终 artifact 与验证证据的绑定；Profile 与实验开关；哪些结论需要真实能力验收而非 fake 测试。

这些决定能够将 R1–R5 接到同一套已有组件上。完成决定后，以最小公开合同测试逐项验证 P0 缺口，再将真实提供方闭环、成本对比和研究效应分别作为独立证据提交。本文到此为止，不执行 setup，不修改实现，不宣称任何新增实验已经通过。
