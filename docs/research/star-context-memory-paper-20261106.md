# STAR 的上下文与记忆机制（2026-11-06）

**结论：** 去重只能减少重复内容，不能阻止独有信息继续增长。论文描述了跨会话状态保存、角色状态注入和选择性重置，可缓解记忆碎片；在论文与固定 commit README 中未找到明确的自动 token compaction 算法或上下文大小保证。

- **同一步上下文与回溯：** 论文 §3.4 保持 Reasoner/Verifier 的挑战辩论上下文；Trace-Back 会归档被放弃步骤及辩论记录、重置 Reasoner session，并救回已验证的中间结果。这是会话生命周期管理，不等同于压缩 token 历史。[论文 §3.4](https://arxiv.org/html/2605.19338v1)
- **跨 session 状态注入：** 论文 Appendix B.3 说明 Copilot CLI 的 sessionStart hook（包括 resume）读取当前 `PROBLEM_STATE.md`，按角色提取相关状态再注入新会话。它提供文件化的连续性；论文没有称其为自动摘要或 token compaction。[论文 Appendix B.3](https://arxiv.org/html/2605.19338v1)
- **持久文件与累积账本：** Appendix B.5 将 `PROBLEM_STATE.md`（已验证结果、确认失败、探索发现等）与 `state.json` 作为每题双层状态，并归档旧计划/步骤；失败记录跨重规划保留并注入后续 Reasoner。材料没有给这些历史或注入内容规定长度上限或滚动压缩机制，因此仍可能增长。[论文 Appendix B.5](https://arxiv.org/html/2605.19338v1)
- **多角色 session 范围：** Appendix A 的 Agent Session Policy 与 B.4 规定：Reasoner 在一次 plan attempt 内跨步骤复用、回溯/重规划后换 session；Verifier 每步新建但在 challenge loop 内持续；Meta-Strategist 在单题整个生命周期持续。这里的跨尝试记忆是单题内 Meta session 的连续性，不是论文承诺的跨题持久记忆；对持续 session 的 token 上限/压缩未作说明。[论文 Appendix A（Table 5）及 B.4](https://arxiv.org/html/2605.19338v1)
- **固定版本 README 与 CLI 边界：** 上游 commit `5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d` 的 README 说明每题会生成 `scratch/<problem_id>/`，保存状态、步骤报告、辩论记录和 archive；README 未描述 compaction，也未列 `memory.md` 或 `CLAUDE.md` 作为本机制文件。[固定 commit README](https://github.com/Julius-Woo/STAR-PolyaMath/blob/5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d/README.md#L203-L229) GitHub Copilot CLI 官方文档另行说明 CLI 的自动 context compaction 与 `/compact`；主线程已核对本项目 Intern 直连调用不经过 CLI，故不能继承该 CLI 能力。此处不推断固定 Copilot CLI v1.0.40 的具体阈值。[GitHub CLI context management](https://docs.github.com/en/copilot/concepts/prompting-and-context/context-management)
- **本项目源码对照的归属：** 以下仅记录主线程已核对结论，本文不重复源码审查：Verifier Verified Results 摘要优先、缺失时回退完整报告（`state.py:955-991`）；Reasoner 续 session 使用短 prompt（`agents/agents_reasoner.py:200-208`）；每次 sessionStart 注入 `PROBLEM_STATE.md`（`hooks/inject_problem_context.py`）；角色 session 范围见 `.github/copilot-instructions.md:42-50`。这说明有摘要/注入与 session 控制，但不构成 Intern 直连路径具备自动 token compaction 的证据。

## 本项目框架支持与实际接入

主线程在冻结 revision `0eba346d5227babf86b662922e553cb102e2fb81` 下只读核对 `pyproject.toml`、`uv.lock` 和安装分发元数据：DeepAgents 0.7.25、LangGraph 1.2.15、LangChain 1.4.6、langchain-core 1.6.11。锁定与安装版本一致，未升级依赖。

- **DeepAgents 支持。** 安装源码 `deepagents/graph.py:830,912` 的默认构建栈包含 `create_summarization_middleware`。`deepagents/middleware/summarization.py:1780-1818` 说明旧消息外存、摘要与原消息状态分离、模型 profile 阈值及缺 profile 时的回退。当前官方文档也说明摘要和文件引用机制，但其中 `summarizer=` 扩展要求 >=0.7.26，不能将它当作本项目 0.7.25 已有能力。[官方上下文工程](https://docs.langchain.com/oss/python/deepagents/context-engineering)
- **LangChain 支持。** 安装源码 `langchain/agents/middleware/summarization.py:262` 有 `SummarizationMiddleware`，`langchain_core/messages/utils.py:1146` 有 `trim_messages`。前者由模型生成摘要，后者裁剪消息，两者不能混称无损压缩。按窗口比例触发需要可信模型 profile。[官方摘要中间件](https://docs.langchain.com/oss/python/langchain/middleware/built-in#summarization)
- **LangGraph 提供接入方式，但 checkpoint 本身不压缩。** 官方示例将摘要作为模型调用前的独立节点，或者裁剪 outgoing messages。[官方记忆管理](https://docs.langchain.com/oss/python/langgraph/add-memory#summarize-messages)
- **当前 STAR 真实路径没有接入上述摘要。** `showcase/star_product_pipeline.py:164` 直接构建 `InternModelPort`；`:284-289` 的单节点 `star_projection` 在 `solve()` 返回后执行。`showcase/adapters.py:896-927` 虽定义 `DeepAgentsAdapter` 并调用 `create_deep_agent`，本批 STAR 不经过该适配器。
- **不能只挂一个中间件就认定解决。** `showcase/solver_harness/intern_port.py:437-448` 将 request（含 history、当前草稿和状态）整体 JSON 编码进一条 user message。通用旧消息摘要不能保证缩小这条当前消息里的独有大字段；还需要在出站输入构建处控制投影。现有前缀去重减少副本，未实现按容量滚动摘要。

建议先在现有出站接缝评估复用摘要能力，保留完整持久记录、当前步骤及相关异议和回执引用，不迁移整个调度框架。摘要存在信息损失；新增摘要调用、自动溢出重试及文件回读都必须接入现有身份、预算和权限合同，不能直接继承框架默认行为。Intern 的可信单次输入上限尚未确认，总 Run token 预算不代表单请求窗口。

本轮仅新增研究文档、读取源码和官方资料，未修改运行代码、发起模型调用或运行测试。readiness-30 保持冻结。
