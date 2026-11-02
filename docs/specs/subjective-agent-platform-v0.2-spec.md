# MathAgent Workbench v0.2 实现规格

> **状态：** `superseded by v1.1`。本文保留为历史实现合同，不作为当前开发范围；当前合同见 [GitHub Issue #32](https://github.com/RUSS0718/MathAgent/issues/32)。

**状态：** `proposed`，由 v0.2 PRD Lite 和已确认的需求共识整理而成。本文是开发任务的规格，不是已实现能力声明。

**关联文档：**

- [v0.2 PRD Lite](../prd/subjective-agent-platform-prd-v0.2.md)
- [v0.2 规划调研](../research/v0.2-planning-baseline.md)
- [ADR 0004：Flask 兼容入口与前端边界](../adr/0004-v0-2-flask-and-frontend-boundary.md)
- [ADR 0005：polynomial_check 合同](../adr/0005-v0-2-polynomial-check-contract.md)
- [ADR 0006：本地身份与持久化](../adr/0006-v0-2-local-auth-and-persistence.md)

## Problem Statement

从用户角度看，v0.1 已经有可恢复的 Run、SQLite 存储、动态执行循环、工具注册和 Evidence Pack，但工作区仍然缺少三件事：提交问题后不能立即得到可观察的 Job；刷新或断线后很难可靠地回到同一条执行记录；答案与工具检查之间的关系不够明确。

从评审和工程角度看，v0.1 的离线工程合同已经存在，真实文本和最小 PNG 请求可达，但能力报告仍记录真实工具调用链尚未通过 live 验收。Replay 只能证明回放链路，不能证明模型真的请求了工具。v0.2 需要把普通数学工作区、异步执行、可续传事件、有限的结构化数学检查和可审查证据放在同一条产品路径中，同时保持 `official` Profile 和 v0.1 Showcase 合同可追踪。

## Solution

把 CausalAgent 的完整 `chat-frontend` 作为起点搬入 MathAgent 的 Showcase 产品侧，在本仓库维护一个数学工作区。后端把现有 Showcase 入口迁移为 Flask，保留 v0.1 的旧路径和响应语义，并增加工作区所需的 AuthSession、ChatSession、Job、SSE 和 capabilities 合同。

用户进入 loopback 工作区时由后端自动创建或恢复本地单用户身份。一个 `ChatSession` 包含多轮对话；每个问题创建一个独立 Run，且 `job_id` 与 `run_id` 使用同一个不透明 ID。创建 Job 只负责持久化和入队，后台执行器继续运行；前端通过 SSE 观察已落库的公共事件，支持断线续传、resume、cancel 和幂等重试。

数学验证 P0 固定为一个严格 schema 的 `polynomial_check` 工具。工具只接受结构化的一元多项式、定义域和候选根，精确检查候选代回、重复项和定义域，不声称证明完整解集。结果分开表达 `candidate_status` 与 `coverage_status`；无法形式化或超出工具适用域时返回 `unknown`。需要工具而没有真实合法工具证据的 Run 进入 `needs-review`，不以模型文字声称替代证据。

所有产品状态、工具事件、检查限制和恢复记录都汇入 Evidence Pack。没有 live 工具闭环证据时，只能发布为工程预览、replay 或 unavailable，不能宣称 v0.2 工具能力完成或数学正确率提升。

## User Stories

1. 作为本机演示者，我希望首次打开工作区就能获得 loopback 身份，以便不需要注册流程即可进入产品。
2. 作为本机用户，我希望退出当前 Cookie 后仍能看到历史 ChatSession，以便 logout 不会误删本地工作记录。
3. 作为本机用户，我希望新建、改名、切换和删除 ChatSession，以便按任务组织数学对话。
4. 作为本机用户，我希望刷新页面或使用前进后退仍回到正确的会话地址，以便浏览器导航不会串接消息。
5. 作为数学任务使用者，我希望提交一道文本题后立即得到 Job ID，以便不必等待模型调用完成才能继续操作。
6. 作为数学任务使用者，我希望看到 queued、running、waiting_input、succeeded、failed 和 canceled 状态，以便知道任务是否仍在执行、需要补充条件或需要复核。
7. 作为数学任务使用者，我希望在 SSE 断线后从最后一个事件继续接收，以便网络波动不会导致重复答案或丢失阶段记录。
8. 作为数学任务使用者，我希望切换 ChatSession 时只看到当前会话的事件，以便不同题目的运行不会混在一起。
9. 作为数学任务使用者，我希望在任务等待输入时补充条件并 resume 原 Run，以便不必重新提交已经完成的阶段。
10. 作为数学任务使用者，我希望可以取消仍在执行的 Job，以便停止继续消耗本地预算；迟到结果不能把它重新标成成功。
11. 作为数学任务使用者，我希望使用同一个幂等键重试创建、resume 或 cancel 时不会多启动一次执行，以便网络重试是安全的。
12. 作为数学任务使用者，我希望看到答案、公开解法摘要、工具调用、候选检查和限制，以便判断“候选有效”与“完整性已证明”的区别。
13. 作为数学任务使用者，我希望公式、分式、矩阵和长公式稳定渲染，以便阅读答案时不依赖原始 Markdown 排版。
14. 作为数学任务使用者，我希望非法公式、脚本和危险链接仍以安全可读的形式展示，以便坏输入不会破坏工作区。
15. 作为数学任务使用者，我希望通过 `verification_mode=auto`、`required` 或 `off` 控制是否要求数学工具，以便普通题目和强制复核题目可以使用不同的交付规则。
16. 作为数学任务使用者，我希望 `polynomial_check` 检查每个候选的精确代回、重复项和定义域，以便快速发现候选答案中的具体冲突。
17. 作为数学任务使用者，我希望看到候选检查通过但完整解集未知的分层状态，以便不会把有限检查误解成完整证明。
18. 作为数学任务使用者，我希望工具无法形式化、定义域超出支持范围或服务不可用时看到 `unknown` 和限制说明，以便知道下一步需要人工复核。
19. 作为数学任务使用者，我希望需要工具但模型没有发出合法工具请求时进入 `needs-review`，以便系统不把缺少证据的回答标成已核验。
20. 作为数学任务使用者，我希望一次工具请求、一次 continuation 和至多一次工具重试都能出现在同一条 Evidence 中，以便检查真实工具闭环是否发生。
21. 作为数学任务使用者，我希望工具发现候选冲突时最多触发一次 Solver 修正，并保留原候选和反例，以便修正过程可追溯。
22. 作为数学任务使用者，我希望服务重启后未完成的远端调用进入 `needs-review`，而不是自动重复提交，以便避免未知副作用和重复计费。
23. 作为数学任务使用者，我希望没有 PNG 能力时上传入口被隐藏且 API 返回明确的 `capability_unavailable`，以便不可用功能不会伪装成已交付能力。
24. 作为评审者，我希望看到 `live`、`fake`、`replay`、`experimental`、`unavailable` 和 `planned` 标签，以便区分真实能力、工程预览和未来计划。
25. 作为评审者，我希望回放同一 Evidence Pack 时不重新调用模型或工具，以便演示结果可复现且不会被隐藏的网络调用改变。
26. 作为 Agent 工程师，我希望使用 Run ID 定位阶段、预算、checkpoint、工具结果和失败原因，以便复现一次具体执行。
27. 作为 Agent 工程师，我希望 request ID、幂等记录和状态事件在 SQLite 中持久保存，以便排查重试、恢复和并发冲突。
28. 作为 Agent 工程师，我希望旧 `/health`、`/api/runs`、JSON events、resume 和 Evidence 合同继续可用，以便迁移 Flask 不会破坏现有 Showcase 调用方。
29. 作为 Agent 工程师，我希望 `official` Profile 的 `user_agent.py`、调用预算、输出边界和 baseline 保持不变，以便主观产品开发不会改变客观评分路径。
30. 作为产品维护者，我希望搬入的前端保留 MIT 版权和许可证信息，以便产品侧源码的来源和再分发边界清楚。
31. 作为产品维护者，我希望前端只保留会话、消息、Job、SSE、报告和设置等通用能力，以便因果图、RAG、搜索和管理员入口不会混入数学工作区。
32. 作为产品维护者，我希望以一个端到端工作区合同覆盖主要行为，再用少量浏览器验收验证真实页面，以便减少内部模块之间的脆弱测试耦合。
33. 作为发布负责人，我希望 AC-06 的真实 Intern 工具闭环未通过时自动保留工程预览状态，以便发布说明与能力证据一致。

## Implementation Decisions

### 1. 测试 seam 与交付边界

- 最高测试 seam 是 Flask 工作区合同：请求进入应用，经过持久层和后台执行器，事件从 SSE 返回，结果从状态和 Evidence 查询得到。
- 后端验收使用临时 SQLite、确定性的假模型适配器和确定性的工具 Registry；假适配器只能证明工程链路，不得计入真实工具能力证据。
- 前端只添加少量真实浏览器验收，覆盖登录进入、会话切换、Job 时间线、SSE 恢复、公式渲染和安全渲染。内部 Store、解析函数和组件不被拆成大量实现细节测试。
- `official`、`showcase_mvp` 和 `research` Profile 保持显式边界。v0.2 的 Flask、前端、SQLite、后台执行器和工具默认只在 Showcase 入口启用。

### 2. 前端边界与依赖

- 复制完整 CausalAgent `chat-frontend` 作为基线，在 MathAgent 内维护；保留 Vue 3、TypeScript、Pinia、Zod、Job runtime、fetch + ReadableStream SSE 和会话地址规则。
- 删除因果图、RAG、搜索、管理员跳转和因果专属文案；保留普通会话、消息、Job、报告、Evidence 和设置。
- 使用 KaTeX 渲染行内和块公式。Markdown 输出只允许安全的文本、链接和公式节点；禁止 raw HTML、脚本和危险 URL。解析失败保留原文。
- P0 通过 capabilities 隐藏文件上传控件；文件兼容 API 仍提供稳定 DTO 和 `capability_unavailable`。PNG 端到端能力属于 P1。
- 搬入源码保留 MIT 许可证和版权信息，并记录来源 commit。CausalAgent 原仓库不成为 v0.2 运行时依赖。

### 3. Flask 与兼容 API

- Showcase 产品入口使用 Flask；迁移实现不改变 v0.1 旧路由的路径、状态码和响应语义。
- 旧路由继续提供健康检查、Run snapshot、JSON events、resume 和 Evidence；新合同提供 AuthSession、ChatSession、Job、SSE、capabilities 和文件兼容层。
- CausalAgent 需要的列表接口保持裸数组或元组形状，不替换成分页对象。错误响应统一包含稳定错误码、可读消息和 request ID。
- Job 创建先持久化再返回 `202`；创建响应包含 `success`、`job_id`、`status` 和 `existing`。同键同参数返回原结果，同键异参数返回 `409`。
- 所有状态变更请求都携带后端签发的 CSRF token；AuthSession Cookie 使用 HttpOnly 和 SameSite=Lax。loopback 限制不取代 CSRF 校验。

### 4. 领域 ID、状态和持久化

- `AuthSession` 是认证会话；`ChatSession` 是用户可见的聊天容器。两者不能混用。
- `session_id` 标识 ChatSession；`job_id` 和 `run_id` 共享同一个不透明 ID。一个用户问题只创建一个 Run；追问创建新 Run，等待输入的回答 resume 原 Run。
- 内部 Run 状态为 `RECEIVED`、`PLANNING`、`RUNNING`、`VERIFYING`、`NEEDS_REVIEW`、`COMPLETED`、`FAILED`、`CANCELED`。外部 Job 映射为 `queued`、`running`、`waiting_input`、`succeeded`、`failed`、`canceled`。
- `RESUMED` 是公共事件，不是新的终态。状态迁移和幂等动作必须在持久层约束，迟到结果不能修改取消或结束的 Run。
- 单服务进程后台执行器消费 SQLite 队列。默认数据库、附件和事件目录位于 `artifacts/showcase-v0.2/`，允许环境变量覆盖；历史和幂等记录保留到用户显式删除或清理。
- 进程重启时不自动重复未知的远端调用；未完成 Run 变为 `NEEDS_REVIEW`，等待人工恢复决定。恢复共享原有累计预算。

### 5. SSE、幂等和恢复

- SSE 只投影已经落库的公共事件，业务事件使用正整数 ID，提供 heartbeat、Last-Event-ID、重复去重和未知事件兼容。
- 断线恢复从请求的最后事件 ID 继续；刷新和重复订阅不得触发新的模型调用。事件顺序按持久化 ID 排列。
- Job 创建、resume 和 cancel 接受 UUID v4 `Idempotency-Key`。同一完整重试链使用同一幂等记录；同键异参数返回冲突。
- 一个 ChatSession 只能有一个活动 Job。并发创建、resume 和 cancel 的结果必须是单一有效动作，冲突返回稳定错误码。
- 逻辑 cancel 先写入终态和事件；后台迟到结果只能记录为迟到或丢弃，不能重新开放 Job。

### 6. `polynomial_check` 与验证结果

- 工具输入包含 schema 版本、单变量名、按最高次到常数项排列的有理数系数、`real` 或有理数端点 `interval` 定义域以及有理数候选根。
- P0 只支持一元 1–4 次多项式，不接受多变量、前导零、任意表达式或代码。超出范围返回 `unknown` 并保留结构化输入和限制。
- 检查输出必须包含逐候选精确残差、重复候选、定义域结果、`candidate_status`、`coverage_status`、限制和 Evidence ID。
- 候选全部通过时为 `candidate_status=pass`、`coverage_status=unknown`；冲突或重复为 `conflict`；无法适用为 `unknown`。工具不声称证明完整解集。
- `verification_mode` 支持 `auto`、`required`、`off`，默认 `auto`。`required` 且没有真实合法工具请求时进入 `needs-review`；普通不需要工具的题可以在 `auto` 下完成。
- 一次工具路径最多一次模型工具请求、一次结果 continuation 和一次工具重试。超出后进入 `needs-review`。工具文字声称、程序事后补算或静态标签都不算真实闭环。
- `conflict` 最多触发一次 Solver 修正；原候选、反例、修正候选和两次工具事件都保留。

### 7. Evidence、回放和脱敏

- Evidence Pack 是答案、公开摘要、阶段、工具请求与结果、检查状态、限制、恢复事件和版本信息的脱敏导出。
- 回放只读取 Evidence Pack，不调用模型或工具。`live`、`fake`、`replay`、`experimental`、`unavailable` 和 `planned` 是产品可见的模式标签。
- 任何 trace、导出或前端公开事件都不得包含凭证、完整 prompt、隐藏答案、隐藏推理或完整图片；原始运行产物只写忽略目录。

### 8. 预算与真实能力门槛

- 产品总预算为最多 8 次模型调用、4 次工具调用、1 次重试和 180 秒活动执行上限；resume、纠错和恢复共享累计预算。
- `PythonMathTool` 继续是显式开启的 experimental 工具，不是 P0 默认工具，也不是生产代码沙箱。
- AC-06 必须用 3 道需要计算的文本题各运行 2 次真实 Intern 任务，观察到合法工具请求、Registry 执行、continuation 和 Evidence 关联。未通过时发布状态只能是工程预览或 unavailable。

## Testing Decisions

- 测试只断言外部行为：HTTP 状态和 JSON/SSE 形状、持久化后的状态、事件顺序、可见 Evidence、前端可操作结果和官方边界；不锁定内部类层级或私有函数调用次数。
- 后端主合同使用 Flask 测试客户端和临时 SQLite，注入确定性的假模型与工具。覆盖 AuthSession/CSRF、ChatSession、Job 入队、SSE、幂等、取消、重启恢复、兼容旧 API 和 capabilities。
- SSE 测试必须覆盖 Last-Event-ID、UTF-8 分块、heartbeat、重复事件、未知事件、坏包、切换会话和刷新不重复调用。
- 恢复测试注入工具失败、checkpoint、进程重启、人工恢复和迟到结果，验证成功步骤不重复、失败事件保留、取消终态稳定。
- `polynomial_check` 用 18 个独立外部案例验收：6 个候选有效、6 个候选冲突、6 个不适用或不确定；逐项检查结果和限制必须与预期一致。
- 真实工具闭环测试独立于假模型合同测试。没有真实工具事件时，工程链路测试仍可通过，但 AC-06 和能力发布门槛必须失败。
- 前端浏览器验收覆盖登录进入、会话切换、Job 时间线、断线恢复、KaTeX/矩阵/长公式、非法公式、危险链接、390px/768px/1440px 核心操作和上传控件的 capabilities 状态。
- 前端沿用现有 CausalAgent 的类型和 API 合同测试惯例；后端沿用已有 Showcase server、持久化、工具、验证证据和回放测试的黑盒风格。
- 发布前运行仓库合同检查、官方 baseline/import 边界检查、既有 unittest、Demo 合同检查、干净环境安装，以及前端 `npm ci`、`npm run check` 和 `npm run build`。文档规格本身不改变官方代码路径。

## Out of Scope

- 注册、账号管理、公网多用户部署、管理员入口和权限体系。
- RAG、搜索、长期记忆、向量库、多 Solver、Debate、Reflection、RSI、MCP 扩展和分布式调度。
- P0 之外的 JPEG/WebP、多图、PDF/OCR、函数作图、几何编辑和通用 Vision。
- 完整解集证明、开放式自然语言解析、复杂定义域、任意表达式执行和生产代码沙箱。
- 用 replay、程序事后补算或模型文字声称替代真实工具请求与 continuation。
- 修改根 `user_agent.py`、`implementations/`、官方调用预算、baseline 哈希或官方默认入口。
- 将 CausalAgent 原仓库作为 v0.2 运行时依赖，或把未经验证的外部前端直接当成产品交付。

## Further Notes

- 开发顺序为 S0 设计与风险验证、S1 文本工作区、S2 真实工具 continuation、S3 数学复核、S4 能力与发布收尾；PNG 作为单独 P1 切片。
- 每个切片遵循 failing acceptance → 最小实现 → focused check → 相关完整套件 → diff review。未完成前一个切片的退出条件，不扩大下一个切片的范围。
- AC-06、旧 Showcase 合同、Flask 迁移、前端许可证和 CSRF 是发布前的 S0 高风险门；任一失败都应收缩实现，而不是降低证据标准。
- 实施前冻结技术设计中的模块所有权、schema 迁移、幂等保留、执行所有权、超时、前端来源和许可证；涉及 `official` 的任何改动都需要独立边界审查。
- 效果评估至少使用 20 道与开发调试分离且人工核验的公开文本题，记录题目版本、模型快照、预算、正确性、工具选择、Checker 覆盖/误报/漏报、耗时、usage 和失败率。小样本用于发现回归，不直接宣称普遍能力提升。
- 本规格完成后仍需由技术设计和任务合同把接口、迁移和验收用例拆成可独立交付的切片；`ready-for-agent` 表示可以开始任务分解，不表示所有风险已经关闭。
