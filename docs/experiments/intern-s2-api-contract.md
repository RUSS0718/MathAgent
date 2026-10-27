# Intern S2 API 接入与短探测合同

**状态：proposed；核查日期：2026-10-27；本文件的 probes 均未执行。** 依据公开官方资料和仓库源码，只提出协议，不证明服务对当前账号可用，不构成实验效果结论。

## 目标与边界

唯一推理服务固定为正式 **`intern-s2`**。优先完成主观评测需要的稳定 Demo、可解析结果、工具闭环、失败回退和脱敏证据；不以全量运行 R1–R5 为展示前提。遵循 [AGENTS](../../AGENTS.md)、[文档索引](../README.md) 和 [ADR-0001](../adr/0001-profile-separation.md)，实验仅走显式 showcase/research 入口；本提案不授权改动官方评分路径、默认预算或 accepted ADR。

## 已知事实与待探测合同

“已知”表示官方文档明确写出；账号实际行为仍须短探测。未公开的能力保持 `unknown`，不能用 S1/S1 Pro、自部署框架或第三方文章补齐。

| 项目 | 截至核查日的官方事实 | 拟议接入规则 / 待探测项 |
| --- | --- | --- |
| 模型身份 | 服务列表为 `intern-s2`，397B；`intern-latest` 当前指向它；`/models` 有 `ref_model` [S1] | 固定正式 ID，保存日期、返回模型及版本信息；服务 ID 不等于不可变权重快照；不静默回退 |
| 名称冲突 | 模型卡托管示例写 `intern-s2-397b` [S5]，服务列表写 `intern-s2` [S1] | 以服务列表为接入依据；前者是否可调用仍未知。`intern-s2-preview` 实为 35B 别名；397B Preview 将于 2026-10-31 下线 |
| Chat 接口 | `POST https://chat.intern-ai.org.cn/api/v1/chat/completions`；Bearer 鉴权；部分兼容 OpenAI SDK [S2] | SDK base URL 为 `https://chat.intern-ai.org.cn/api/v1/`；不假定完整 OpenAI 参数兼容 |
| 输入 / 输出 | 支持文本及图像消息格式，角色含 `user/assistant/system/tool`；S2 上下文 256K [S1, S2] | 图像尺寸、张数限制及 Chat 固定输出硬上限待核实；256K 不是单次输出承诺 |
| 思考与长度 | 服务字段 `thinking_mode` 为布尔值，默认开启，工具密集场景建议保持开启；Chat `max_tokens` 默认 0 会自适应最大长度 [S1, S2] | 每次显式设有限 `max_tokens`；内部 thought 是否计入该上限、是否有独立限额及其计费口径均未知 |
| 工具 / 流式 | `tools`、`tool_choice` 有文档；工具结果需对应 `tool_call_id`；tools 当前不支持流式 [S2] | 原生工具回路用非流式；先做本地确定性工具；模型返回参数不等于已经执行 |
| 结构化输出 / 内部信号 | 未找到严格 JSON Schema、`response_format`、logprobs、seed 保证的托管服务说明 [S2] | 分别探测并本地校验；JSON prompt 不等于约束解码；不把 token 熵设为必需输入 |
| 响应与计量 | Chat 文档的流式请求及响应示例展示 `stream=true`、增量 `choices` 和 `[DONE]`，但示例未展示 `usage`，参数表也未列 `include_usage`；文档化 `thinking_mode`，但未明确承诺它与流式组合的服务行为，也未说明 `reasoning_content` 计量 [S2] | 检查字段存在性；`missing usage != 0`。单次有字段也不证明完整内部 thought 已计量 |
| 超时 / 限流 | Chat 文档写明 120 秒未完成会截断；默认每用户 30 请求/分钟；错误说明涉及 RPM/TPM [S2] | 实际服务行为待核实；TPM、并发上限未知。客户端超时与服务端截断分开记录 |
| 额度 / 缓存 | 官方确认一定额度免费 API，可申请提高 [S4]；未查到固定金额单价、确切免费 token 数或托管缓存合同 | 先确认账号额度；价格留空。无缓存计量证据时，重复前缀按再次输入预算 |

另有 **Messages API**：`POST https://chat.intern-ai.org.cn/v1/messages`，使用 `x-api-key`；文档要求 `max_tokens` 为 1–32000，`system` 独立，响应可含 `thinking`，并明确非流式 `usage.input_tokens/output_tokens` [S3]。它与 Chat 不是同一请求协议，不能仅替换 URL。

**2026-10-27，#96 流式接口核对：** Intern 官方 Chat Completions 文档明确提供 `stream=true` 和增量响应示例，也文档化 `intern-s2` 的 `thinking_mode`；因此不能据此称流式传输本身不可行。文档说明工具调用不支持流式，且 Chat 流式示例未给出 `usage` 或 `include_usage`；思考参数和流式参数虽都在文档中，但其组合行为没有单独承诺 [S2]。Messages API 则展示 `message_delta.usage.output_tokens`，而 `message_start` 示例没有 usage，流式事件示例没有 `input_tokens`；参数表未定义 `thinking_mode`。非流式 Messages 响应示例有 `input_tokens` 与 `output_tokens`，不能据此保证流式输入计量 [S3]。仓库的 `InternStreamAdapter` 仍基于显式选择的 Chat Completions SSE 路径；本轮不把它作为架构闭环或非流式实验的必要条件，也没有取得修复后的 provider live 证据。适配器只有在响应实际包含相应 usage 字段时才能结算；缺失字段仍须保留预算预留。流式保持可选且 #96 保持开放。若未来单独验收或比较 Messages 与 Chat 路径，须独立注册，并验证 thinking 行为及逐次 usage；不能把两种 API 的差异只归因于传输方式。离线范围与状态见 [#96 非流式主路径验收记录](../evals/star-stream-usage-96.md)。

## 最多 8 次短 probe

先确认账号可用额度与本批输入、输出、请求数上限。**以下是测试设计，不是可直接批跑的脚本或已完成记录。** 每行最多一次 HTTP 请求，串行执行；未满足依赖即标 `blocked/skipped`。总尝试数固定 1；当前 `InternChatClient.retry` 表示总尝试数，应设 1 而不是 0。认证、额度或计量失败时停止后续生成，不自动扩样。

| Probe | 操作 | `max_tokens` | 通过条件 / 要记录的结果 |
| --- | --- | ---: | --- |
| P1 | `GET https://chat.intern-ai.org.cn/api/v1/models` | — | 正式模型可见，记录 `ref_model`；不索取或打印凭证 |
| P2 | 极短文本，`thinking_mode=false` | 64 | 有可解析最终文本；记录 usage 是否存在、模型、结束原因和延迟 |
| P3 | 同一极小算术题，`thinking_mode=true` | 256 | 记录内容/思考字段的存在性与长度、截断状态；不比较数学能力 |
| P4 | 强制调用本地确定性 `add(a,b)`，thinking 开启、非流式 | 512 | 原生 `tool_calls` 名称及参数符合 schema，调用 ID 存在；只执行注册工具 |
| P5 | 回传 P4 的工具结果及对应 ID | 128 | 成功消费工具结果并自然结束；P4 失败则跳过 |
| P6 | 请求极小 JSON Schema 结果 | 64 | 区分参数拒绝、接受但不合 schema、符合 schema；HTTP 200 不足以证明严格支持 |
| P7 | 给定显式证明前缀，仅请求下一步 | 256 | 记录是否遵守分段协议、重复或改写前缀；只验证可见文本续写 |
| P8 | 无 tools、thinking 关闭的极短流式请求 | 128 | 能解析 chunk 与终态，记录 usage 是否出现；只在前面基础合同通过后执行 |

上述最多 **1 次模型查询、7 次生成**，请求中的 `max_tokens` 合计 **1408**；这是参数之和，**不是完整总 token 或内部 thought 的硬上限保证**。所有输入、工具返回输入、失败请求及可能仍在服务端运行的超时请求另计。探测若返回 `length`，记录“预算截断”，不擅自加长再跑。不要调用现有 live Demo 的默认长流程来代替本批短 probe。

## 预算与公开字段

每个请求在启动前预留完整输入估计与生成上限，分支共享一份账本；收到响应后结算。计量使用 `usage_source=provider/local_estimate/missing`，同时保留字段存在性。缺失、非法或未知值记 `null`，不能转为 0；失败请求不得当免费。服务未提供完整计量时只报告可见 token/估计，不声称精确付费成本或精确 thought 节省。

公开 trace、SSE、Evidence Pack 采用明确白名单：脱敏 `run_id/problem_id`、方法/动作/分支标签、请求与返回模型 ID、已知 `ref_model`、思考开关、采样参数、输出上限、尝试序号、状态/错误类别、结束原因、耗时、usage 来源及允许的数值计量、注册工具名称和结果状态。服务返回的未知字段默认不进入公开对象；账户标识、凭证及自由文本错误详情不透传。

**隐藏推理不导出。** 不导出 `reasoning_content`、`thinking` 块、完整 prompt、原始响应、题库答案、原始图片或工具参数值。只保留思考字段是否存在/字符数等允许的诊断。`content` 若混有思考标记，须经过既有边界检查，不拼接隐藏推理为最终答案。展示使用独立生成或既有脱敏的步骤摘要；最终答案沿用现有可解析结果合同。公开白名单也适用于失败和取消路径。

## 复用当前客户端与 adapter 的差距

本节是对核查日源码的只读结论，不表示修复已完成；只阅读源码，未导入会加载本地配置的模块。

| 已有入口 | 可复用部分 | R1–R5 / 短 probe 前需补齐的合同 |
| --- | --- | --- |
| [`llm_client.py`](../../llm_client.py) 的 `InternChatClient` | 已默认 `intern-s2`、正确 Chat 地址；支持逐请求 reasoning 开关、有限输出、脱敏尝试诊断 | `chat()` 只返回 content，无 `tools/tool_choice` 参数；缺失 usage 当前可能记 0。研究侧需完整响应/计量桥，不能用现有零值证明免费或节省 |
| [`showcase/adapters.py`](../../showcase/adapters.py) 的 `InternModelAdapter` | 现有注入式客户端边界、错误规范化、文本工具标记解析 | 内置客户端不接收原生 tools；字符串返回使 `ModelResponse.usage` 为空。适配层需保留真实 tool calls、usage 的缺失状态与请求级参数 |
| 同文件的 continuation / 消息规范化 | 已有继续调用 seam 和工具结果传输位置 | 当前规范化只保留 role/content，continuation 未携带原生 `tool_call_id`；不能视为原生两轮工具协议已打通 |
| 同文件的 `InternChatModel` | 现有 DeepAgents/LangChain 接口 | `bound_tools` 的存储不证明向服务发送；当前文本 marker 路径须与原生调用分别验收 |
| [`scripts/run_capability_probe.py`](../../scripts/run_capability_probe.py) | 现有 fake/live 验收入口、脱敏输出风格 | 当前脚本是产品 Run probe，不能保证本表的逐请求上限；adapter 默认 16,384 输出也不适用于短探测 |

后续实现应沿现有注入边界补研究侧能力，复用鉴权、配置和诊断，不再建立一套无法统一计费的网络路径；默认不启用，不增加 official 调用。本文件不修改上述代码，也不更改比赛基线。仓库 [v0.1 能力记录](../evals/v0.1-capability-baseline.md) 已有文本/最小图文可达证据，同时明确真实工具选择未获稳定性证明；不能将本次 proposed 合同改写为“未曾接通过”或“工具能力已验证”。

## 必须保持的概念区分

- 256K 上下文、单次输出上限、内部 thought 限额和整题多调用预算分别计量。
- 30 RPM 是请求频率，不是并发数；延长客户端 timeout 不保证突破服务端截断。
- 分段可见证明续写、Job/checkpoint 恢复与模型内部 KV/隐藏思考恢复不同；本批只探测可见文本续写，Job 恢复另走仓库合同。
- 文本 JSON 工具标记、原生 function call、严格 JSON Schema 输出分别验收。
- 同一 S2 担任多个角色不构成独立模型验证；符号工具通过与完整证明正确性也分别报告。
- 工程 probe 通过证明接入可达；比赛展示、数学正确率提升和 R1–R5 的创新性需要各自证据。

## 官方资料

- [S1 模型列表](https://internlm.intern-ai.org.cn/doc/docs/%E6%A8%A1%E5%9E%8B%E5%88%97%E8%A1%A8/)
- [S2 Chat Completions API](https://internlm.intern-ai.org.cn/doc/docs/Chat/)
- [S3 Messages API](https://internlm.intern-ai.org.cn/doc/docs/API_DOCUMENTATION_ZH/)
- [S4 上海人工智能实验室 S2 发布及免费额度公告](https://www.shlab.org.cn/news/5444298)
- [S5 正式 S2 模型卡](https://huggingface.co/internlm/Intern-S2-397B)
- [S6 Claude Code 接入说明](https://internlm.intern-ai.org.cn/doc/docs/%E6%8E%A5%E5%85%A5ClaudeCode/)
- [S7 S2 自部署指南](https://github.com/InternLM/Intern-S1/blob/main/docs/interns2_397b_user_guide.md)：其中长上下文和 prefix caching 配置不代表托管 API 合同。
- [S8 官方额度申请页面](https://internlm.intern-ai.org.cn/api/strategy)：本次未读取账号额度。
