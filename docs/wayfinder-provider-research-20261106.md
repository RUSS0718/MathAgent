# Intern-S2 流式活性、截止与上下文容量边界

**核查日期：** 2026-11-06（Asia/Shanghai）  
**任务：** [GitHub Issue #132](https://github.com/RUSS0718/MathAgent/issues/132)  
**源码基线：** `b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6`  
**范围：** 官方托管 Chat Completions 文档、仓库当前出站请求与截止链、已有 readiness-30/31 记录。本文不发真实 provider 请求、不读取凭证或本地 `.env`，也不安装依赖。

## 结论

Intern 官方文档证明托管 Chat Completions 有 SSE 示例、`choices[].delta` 和 `[DONE]`，并列出 Intern-S2 的 256K 上下文窗口；它没有公开保证 1200 秒持续流、首次输出期限、30 秒内容闲置规则、Chat 流式 usage 完整性或 JSON body 字节上限。相反，Chat 文档写明模型在 120 秒仍未完成时服务端会中断并返回当前结果，但没有说明中断响应是否包含 `[DONE]`。这条文档口径与 readiness-30 的单次历史观察冲突：该请求有正文增量持续至本地 1200 秒截止，且无 finish reason 或 completion。故不能把 120 秒当成已验证的绝对线上上限，也不能把 1200 秒软提示写成 provider 保证；需保留为冲突证据并由受控后续核验解决。

仓库目前也没有 issue 所问的 30 秒有效增量闲置 watchdog 或按角色首响应 watchdog。显式 SSE adapter 有本地绝对 deadline，受 client timeout 与 Run/phase/batch deadline 中最早者约束；默认 live pipeline 仍创建非流式 adapter。上下文方面，最终出站请求按 UTF-8 JSON 字节长度预留本地预算，但没有用 Intern-S2 tokenizer 计算输入 token、没有 provider API body 字节限制准入，也没有接入自动上下文压缩。单请求容量与整题累计预算必须分开判断。

**重要区分：** 收到正文或 reasoning 字段增量只证明有传输活动，不证明数学上取得进展；未收到完整终止证据的请求仍是结果未知，不自动重发。

## 已确认事实

### Intern 官方接口

- 官方 Chat Completions 页面给出的托管地址为 `https://chat.intern-ai.org.cn/api/v1/chat/completions`，示例使用 `stream=true`，并展示增量响应和 `data: [DONE]`。页面明确说明启用 tools 时不支持 stream。它没有把任意 Chat 参数组合都承诺为兼容接口。[官方 Chat Completions API](https://internlm.intern-ai.org.cn/doc/docs/Chat/)，核查日期 2026-11-06。
- 官方模型列表将服务模型标识为 `intern-s2`，窗口列为 256K。这个数值是模型目录事实，不等于该托管 endpoint 已公开输入 token 计算器、输入与输出合计规则、最大 HTTP body 字节数或在特定账号上的准入边界。[官方模型列表](https://internlm.intern-ai.org.cn/doc/docs/%E6%A8%A1%E5%9E%8B%E5%88%97%E8%A1%A8/)，核查日期 2026-11-06。模型卡中的评测配置或自部署配置不替代托管 API 合同。
- Chat 文档写明模型在 120 秒仍未完成生成时服务端会中断并返回当前结果。文档没有定义该中断对应的 SSE 终止事件、finish reason、是否完整计量或服务端是否取消生成。[官方 Chat Completions API](https://internlm.intern-ai.org.cn/doc/docs/Chat/)，核查日期 2026-11-06。
- 同一文档的 Chat 流式示例没有给出 usage 事件；参数表没有记载 `include_usage` 或 `stream_options`。页面把 `thinking_mode` 列为可用参数，但未承诺它与流式、`reasoning_content` 增量的联合行为。因而缺 usage 不能解释为零，邻近 Messages API 的 usage schema 也不能套用到 Chat Completions。
- 文档所列每用户 30 RPM 是请求频率限制，不是并发上限或模型响应时限。[官方 Chat Completions API](https://internlm.intern-ai.org.cn/doc/docs/Chat/)，核查日期 2026-11-06。

### 仓库出站链（固定源码基线）

- `showcase/server.py` 的默认 live factory 构造 `InternModelAdapter`，默认 client timeout 为 180 秒、输出 `max_tokens` 为 16,384；默认路径不是 SSE。需要显式注入 `InternStreamAdapter` 并通过 transport policy/profile 才会选择流式路径。[server.py#L174-L190](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/server.py#L174-L190)；[adapters.py#L274-L299](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/adapters.py#L274-L299)。
- 显式 `InternStreamAdapter` 序列化的 body 含 `model`、`messages`、`stream=true`、`temperature`、`max_tokens`；仅在值非空时附加 `thinking_mode`。此流式 body 不加 `tools`、`tool_choice`、`include_usage` 或 `stream_options`。鉴权在 `Authorization` header，不属于 body。[adapters.py#L283-L300](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/adapters.py#L283-L300)。
- `InternModelPort._messages` 把系统指令与一条 user message 发出；user message 的 content 是 JSON 序列化的角色请求，可能包含原题、角色、当前目标、状态/历史投影、工具 schema、回执及响应协议。历史量因此会进入同一个最终 provider request，不只是独立 `messages` 数量。[intern_port.py#L397-L448](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/intern_port.py#L397-L448)。
- SSE parser 读取 `delta.content` 与 `delta.reasoning_content`；正文增量会交给上游并计字节，reasoning 只记录字符数和时间，不将字段文本放入公开 activity observer。parser 可读取实际出现的 usage，但这只是兼容代码，不是官方字段保证。[adapters.py#L460-L532](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/adapters.py#L460-L532)；[stream_activity.py#L1-L17](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/stream_activity.py#L1-L17)。严格完成路径要求完整响应、`[DONE]`，并要求非空 `finish_reason`；未完整流或缺少终止标志不会变成成功结果。[adapters.py#L577-L590](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/adapters.py#L577-L590)。
- `response_events` 在后台 reader thread 做阻塞 Requests I/O，以 16 项有界队列传事件；前台每次最多 50ms 轮询队列，并以单调/受保护时钟执行绝对 deadline。队列轮询不是内容闲置 watchdog，且该链没有根据“最后一段有效正文时间”自行取消的 30 秒逻辑。[request_transport.py#L82-L114](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/request_transport.py#L82-L114)；[request_transport.py#L140-L185](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/request_transport.py#L140-L185)；[request_transport.py#L226-L257](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/request_transport.py#L226-L257)。
- SSE adapter 的当前绝对调用截止取配置 timeout 与剩余调用/Run deadline 的较早者；request transport 收到的 `timeout` 同时作为 Requests connect/read timeout。Requests 文档将 read timeout 定义为等待服务端两字节之间的时间，connect/read timeout 都不是总墙钟时限；本仓库另行设置的 `response_events` absolute deadline 才是本地墙钟截止。[adapters.py#L328-L373](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/adapters.py#L328-L373)；[Requests timeout 文档](https://requests.readthedocs.io/en/latest/user/advanced/#timeouts)，核查日期 2026-11-06。
- `RunBudgetLimits` 同时有 Run 总时长、逻辑调用、HTTP attempt、token 预留；`phase_deadline_at` 与 `batch_deadline_at` 可再压低有效 deadline。研究子任务另由 `bounded_research` 的 `Future.result(timeout=...)` 限制；这是 researcher task 的边界，不是 SSE provider stream 的独立 watchdog。[run_budget.py#L33-L74](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/run_budget.py#L33-L74)；[research.py#L1-L19](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/research.py#L1-L19)。
- 当前本地输入预留取最终 JSON body 的 UTF-8 字节数，并把来源标为 `local_utf8_bytes`；它不是 tokenizer token count。`max_tokens` 是输出上限参数，不能作为输入容量测量。当前源码没有 provider input cap 或最终 payload byte cap 的准入函数。[adapters.py#L293-L300](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/adapters.py#L293-L300)；[run_budget.py#L155-L209](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/run_budget.py#L155-L209)；[run_budget.py#L390-L405](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/run_budget.py#L390-L405)。
- 技术设计中的 ContextPack、自动压缩和容量准入是目标设计，不是当前实现；现有角色上下文投影、历史筛选或去重也不能证明 tokenizer 计量/压缩已接通。[star-context-memory-paper-20261106.md](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/docs/research/star-context-memory-paper-20261106.md)。

## 未确认、建议与反证

| 主题 | 已确认 | 未确认 / 不应外推 | 反证或边界 |
| --- | --- | --- | --- |
| 流式活性 | 文档展示 SSE delta；parser 可处理实际到达的 content/reasoning 字段 | S2 是否在全部 thinking 配置下持续发事件；delta 速率、心跳频率、reasoning 是否总以独立字段发出 | activity 事件只证明接收过内容；不证明新数学结论或进度 |
| 终止 | 文档展示 `[DONE]`；仓库 strict path 要 `[DONE]` 与非空 finish reason | 服务端 120 秒中断时的 wire terminal；usage 尾事件是否稳定返回 | EOF、timeout、断连、无 `[DONE]` 都不能当完整成功；unknown 不自动重发 |
| 1200 秒 | PRD 把 1200 秒定义为仍活跃请求的 UI 软提示目标 | 托管 API 是否允许相同单次请求持续至 1200 秒以上 | 官方 Chat 文档写 120 秒未完成会中断；历史 readiness-30 又观察到活动持续至本地 1200 秒截止。两者冲突，均不能单独确定通用服务行为 |
| 首响应 / 30 秒 idle | ZIP 技术设计提出 Meta/Explanation 60 秒、Explore/Planner/Researcher/Step Verifier 120 秒、Reasoner/Whole Verifier/Final Generator 180 秒的首有效增量初值；提出有效增量后 30 秒 idle | Provider 是否支持这些角色阈值；Reasoning delta 是否可当作有效活性；socket read timeout 与内容闲置阈值的协调 | 上述值是设计初值。当前源码未实现首响应/内容 idle 计时器；默认 180 秒 absolute deadline 会先于 1200 秒到期，除非特定 Run 显式覆盖 |
| 上下文 | 官方模型目录列 256K；仓库可复现最终 JSON body 字节数 | Hosted endpoint 的实际 tokenization、输入/输出合计口径、图像计量、硬 body size、账号级有效窗口 | readiness-29 记录过 `INPUT_LENGTH_ERROR`；readiness-30 在去重后仍未触发同类错误。错误不能给出边界，单次未报错也不能证明容量上限 |
| Usage | parser 保留实际响应中出现的 usage 字段 | Chat SSE 是否保证 usage、思考 token 是否完整计量 | 没有 usage 是 metering unknown，不是零；整题总预算也不是单次 context window |

### 历史 provider 证据（只作一次观察）

- readiness-30（2026-11-06）记录自然题 step 12 的 SSE：首正文在请求后约 16 秒出现，最后正文在接近第 1200 秒时仍有记录；累计 396 个事件、3,222 正文字节。客户端按本地 1200 秒 deadline 结束时没有 finish/completion，记录为 `unknown_outcome/timeout`。这是与官方 120 秒说明相冲突的单次实际观察，不证明 provider 承诺支持 1200 秒，也不证明流中的内容有数学进展。[readiness-30](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/docs/evals/provider-live-natural-20261106-readiness-30.md)。
- readiness-31（2026-11-06）记录另一请求在约 170 秒时因 connectivity 异常结束，包含正文增量但无完成标记；底层断连原因未确认。它同样反驳“每次请求必在 120 秒整齐完整结束”的强说法，但不能证明长流可靠。[readiness-31](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/docs/evals/provider-live-natural-20261106-readiness-31.md)。
- 历史报告描述的是其冻结配置和已运行请求；本任务未复跑或向 provider 查询。源码默认 180 秒与历史配置 1200 秒必须分别陈述，不能互相替代。

## 建议的无付费风险实验

以下建议只用虚拟时钟、合成 SSE、loopback HTTP 或注入的假 transport；无需真实等待 1,300 秒、访问 provider 或安装工具链。记录均应断言公开状态和计数，不保存凭证、完整 prompt、reasoning 原文或隐藏答案。

| 用例 | 驱动 | 通过条件 |
| --- | --- | --- |
| 长流软提示 | 虚拟单调时钟推进到 1,199、1,200、1,300 秒；在间隔内持续送入合法非空 delta | 1,200 秒只发一次 slow 提示；仍有有效 delta 时不由软提示终止；完整结尾仍依 `[DONE]` 与 strict finish reason 判定 |
| 有效闲置 | 先送非空 content，再仅送 SSE 注释、空 delta、role、headers、usage 和重复事件，虚拟推进 30 秒 | 这些无效活动不刷新 `last_meaningful_delta_at`；到阈值后只结束当前调用并保留 partial/unknown 预留 |
| 首响应与 reasoning | 从实际 dispatch 时刻启动各 role 配置；分别注入空事件、非空 content、非空 reasoning | 排队时长不计首响应；每个 profile 按显式配置判定。reasoning 计活性的规则先作为可配置实验值，不默认为 provider 合同 |
| 终止矩阵 | 覆盖 `[DONE]`+finish、`[DONE]` 无 finish、finish 无 `[DONE]`、EOF、断连、timeout、空 content、usage-only tail | 每个状态可区分 complete、已知协议失败与 unknown；没有完整证据时不自动重发 |
| Deadline 竞争 | 注入 Run、phase、batch、调用 deadline；在边界前后送持续 delta，并让 researcher Future 超时 | 最早硬 deadline 生效；Future 只约束其 researcher 子任务；queue 50ms 轮询和本地处理线程不能延后/伪造 provider 活性 |
| 容量准入 | 构造长 history、巨大当前字段、中文 UTF-8 和工具回执；捕获最终 JSON body | 先冻结并比较 UTF-8 body 字节数、规范化 messages、输出预留和 tokenizer 估计各自字段；不把字节直接命名为 token。超出注入的测试 cap 时 provider dispatch 为零，固定层丢失时返回明确容量错误 |

测试中 60/120/180 秒、30 秒与 1,200 秒可用虚拟时间验证状态边界，但不据此批准生产配置。最终 `input_cap`、安全余量、容量触发/压缩比例和角色 timeout 仍待项目用户决定与独立标定；单个本地测试不提供这些数值。

## 后续 provider 标定设计（当前未授权执行）

应先取得账号额度/预算决定，并向服务方确认官方文档的 120 秒行为与 readiness-30 的 1,200 秒观察为何不同。用户决定前，最大请求数、输出 token、墙钟、额度/金额全部保持 **TBD**；不以免费额度公告推断当前账号有可用余额。

如后续获准，只登记精确 profile：官方 Chat endpoint、`model=intern-s2`、显式 `thinking_mode`、显式有限 `max_tokens`、`stream=true`、无 provider tools、固定 temperature 和最小公开输入。每次 run 冻结请求 JSON 的 SHA-256 与 UTF-8 字节数，凭证只在进程环境中，不写日志。

采集且只采集：HTTP 状态、返回 model/ref_model（若提供）、首 byte/首 event/首 content 与 reasoning 的相对时间、事件和非空增量计数、最大有效增量间隔、`finish_reason`、`[DONE]`、usage 字段存在性、总耗时、错误类别及请求哈希。不要记录 reasoning 原文。

通过条件分项判定：收到合法 HTTP/SSE 与非空增量只证明该 profile 的流式可达；`[DONE]` 加非空 finish reason 才证明该次完整；usage 字段只证明字段在该次出现。要支持“1200 秒后仍活跃”，必须看到跨过该阈值的有效增量并最终收到完整终止，而且需要服务方解释与 120 秒文档的矛盾；未跨阈值、无终止、只收到心跳/usage 或触发本地 deadline 一律不通过该结论。要得到 API 容量边界，必须由服务方给出合同或经用户批准的递增 payload 实验；一次成功请求不得外推为 hard cap。

无论 provider 标定结果如何，unknown attempt 保留原身份、未知预留和原 deadline；明确用户决策后才允许以新 call ID 重试。若 120 秒文档行为未澄清，优先把单次请求保持在产品硬预算内并报告未标定，不自动用更长超时掩盖服务端截断。

## 影响切片与资料

- **S01 超时、错误与幂等：** 补显式 CallPolicy、首响应/有效 idle/软提示字段、真实 hard deadline 来源、strict SSE 终止和未知请求展示；确保 parser、队列与本地处理之间没有另一条未标注硬截止。
- **S02 上下文：** 对最终完整 body 做容量准入，记录 tokenizer 版本与字节数分开的字段，并覆盖固定原题、当前工作和工具回执；只有在 tokenizer/API cap 有可信来源后才启用压缩阈值。
- **S05 UI：** 将 transport activity 与已验证数学进展分别呈现；slow 提示不得表示任务必然完成或数学有效。
- Issue #132 的 PRD/技术设计副本来自用户提供资料解压目录：`artifacts/wayfinder-20261106/MathAgent_PRD_20261106.md`、`artifacts/wayfinder-20261106/MathAgent_Technical_Design_20261106.md`。以 ZIP 对应的 PRD/技术设计作为需求背景；PDF 提取文本 `artifacts/wayfinder-20261106/report.txt` 仅作目标背景，不作接口或实现证据。
- 仓库既有协议审计：[docs/research/intern-sse-123.md](research/intern-sse-123.md)，核查日期 2026-11-02；其 loopback/scripted 覆盖不等于 provider-live 验证。
- 本报告源码链接固定在 `b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6`，而不是会移动的分支名。ZIP 文档提出的 60/120/180 秒首响应值、1,200 秒提示、30 秒 idle、70% 触发和压缩比例均为需求或待标定建议，不是已实现能力。

**本次验证范围：** 外部官方文档和公开 Issue 只读核对；本地源码与历史记录只读核对。未运行 provider 请求、未读 `tests/test.md`、未安装依赖、未修改产品代码或测试。
