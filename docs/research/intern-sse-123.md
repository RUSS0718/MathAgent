# #123 Intern Chat SSE 契约与故障覆盖

**核查日期：** 2026-11-02（Asia/Shanghai）
**证据类型：** 官方文档核对、仓库源码审查、loopback/scripted 自动测试
**Provider-live：** 未执行；本报告不授权或要求真实 API 请求。

## 结论

Intern 托管 Chat Completions 文档展示 `POST /api/v1/chat/completions` 流式增量和 `[DONE]`；这是文档层接口支持，不是 provider-live 验证。文档明确规定启用 tools 功能时不支持 stream，因此启用 provider-native tools 的调用必须走非流式。文档把 Intern-S2 的 `thinking_mode` 默认/示例值列为 `True`，但未定义其与 SSE 的联合行为；仓库本地的 `None` 只会省略请求字段，不能解释成关闭 thinking。当前没有验证过的 provider-live profile，故自动 SSE 默认关闭。该限制仅针对同一请求同时使用 tools 与 stream，不表示所有 Intern 调用都不支持 native tools。[Intern Chat Completions 官方文档](https://internlm.intern-ai.org.cn/doc/docs/Chat/)

官方页面没有给出 Chat Completions 流式 usage 事件合同，也没有记录 `include_usage` 参数。流式响应示例展示增量 `choices[].delta` 与结束标记，但不保证 usage 一定出现。故缺 usage 只能记为计量未知，不能改写成零，也不能据此将已完整结束的传输判为网络 unknown。

该结论只适用于旧 Chat Completions endpoint。官方另有 Claude-like Messages API（`POST https://chat.intern-ai.org.cn/v1/messages`），其认证、payload、SSE 事件和 usage schema 均不同；该 API 的 usage 事件不得用于推定 Chat Completions 的用量合同。[官方 Messages API 文档](https://internlm.intern-ai.org.cn/doc/docs/API_DOCUMENTATION_ZH/)

旧 #96 的两次 provider 运行共四个 HTTP 请求正常结束但没有 provider usage；预算预留阻止后续整题审查。这证明的是当时该批次有用量缺口，不证明 SSE 不可用、缺 usage 必然导致 task 失败，也不证明新增某个参数可以修复用量。旧批次及身份保持不变。

## #124 可消费的 endpoint / payload 规则

以下规则采用 fail-closed 解释，不把文档分别列出的参数推断成已验证的组合。官方流式示例展示 `stream=true`、`choices[].delta` 和 `[DONE]`；详细参数表给 `thinking_mode` 的示例/默认值为 `True`，并建议 Intern-S2 agent 默认保持开启。文档没有定义省略该字段时托管服务的实际取值，也没有说明 `thinking_mode` 与 SSE 的联合行为。因此省略字段绝不代表关闭 thinking；当前没有 provider-live 验证档案，自动 SSE 默认关闭。只有未来某个独立预登记并经 provider-live 验证的精确档案，才可启用匹配它的 endpoint/model/thinking/payload 组合。[Intern Chat Completions 官方文档](https://internlm.intern-ai.org.cn/doc/docs/Chat/)

```json
{
  "rule_id": "intern-chat-completions-sse",
  "rule_version": 2,
  "method": "POST",
  "endpoint": "https://chat.intern-ai.org.cn/api/v1/chat/completions",
  "model": "intern-s2",
  "valid_as_of": "2026-11-02",
  "expires_no_later_than": "2027-01-26",
  "evidence": {
    "documentation": {
      "chat_completions_sse": "documented",
      "thinking_mode_default_for_intern_s2": true,
      "thinking_mode_with_stream": "not_documented_as_a_combination",
      "provider_native_tools_with_stream": "unsupported",
      "chat_stream_usage": "not_documented",
      "include_usage": "not_documented",
      "stream_options": "not_documented"
    },
    "loopback": {
      "status": "passed",
      "scope": "synthetic_request_serialization_sse_parsing_and_attempt_accounting",
      "provider_compatibility": "not_tested"
    },
    "provider_live": {
      "status": "not_verified",
      "request_count": 0,
      "verified_profiles": []
    }
  },
  "current_defaults": {
    "transport": "nonstream",
    "automatic_streaming_enabled": false,
    "repository_thinking_mode_setting": "None_means_omit_payload_field",
    "documented_provider_default_when_omitted": true,
    "omission_means_thinking_disabled": false
  },
  "automatic_streaming": {
    "enable_only_with_matching_profile_status": "provider_live_verified",
    "profile_source": "evidence.provider_live.verified_profiles",
    "profile_match_semantics": "EXISTS profile satisfying every verified_profile predicate",
    "predicate_combiner": "AND",
    "predicate_operator_semantics": {
      "absent": "key is missing; explicit null does not match",
      "equals_set": "the JSON array values are equal regardless of order",
      "satisfies_profile_schema": "value passes the recorded JSON Schema or predicate from the matching provider-live profile",
      "equals_profile_value": "key must be present, non-null, and equal the explicit value in the matching verified profile"
    },
    "eligible_all": [
      {
        "path": "request.method",
        "op": "eq",
        "value": "POST"
      },
      {
        "path": "request.endpoint",
        "op": "eq",
        "value": "https://chat.intern-ai.org.cn/api/v1/chat/completions"
      },
      {
        "path": "request.payload.model",
        "op": "eq",
        "value": "intern-s2"
      },
      {
        "path": "request.payload.thinking_mode",
        "op": "equals_profile_value",
        "profile_field": "thinking_mode"
      },
      {
        "path": "request.payload.temperature",
        "op": "equals_profile_value",
        "profile_field": "temperature"
      },
      {
        "path": "request.payload.max_tokens",
        "op": "equals_profile_value",
        "profile_field": "max_tokens"
      },
      {
        "path": "request.payload.messages",
        "op": "satisfies_profile_schema",
        "profile_field": "messages_schema"
      },
      {
        "path": "request.payload.tools",
        "op": "absent"
      },
      {
        "path": "request.payload.tool_choice",
        "op": "absent"
      },
      {
        "path": "request.payload.keys",
        "op": "equals_set",
        "value": [
          "model",
          "messages",
          "temperature",
          "max_tokens",
          "thinking_mode"
        ]
      },
      {
        "path": "verified_profile.status",
        "op": "eq",
        "value": "provider_live_verified"
      },
      {
        "path": "verified_profile.method",
        "op": "eq",
        "value_from": "request.method"
      },
      {
        "path": "verified_profile.endpoint",
        "op": "eq",
        "value_from": "request.endpoint"
      },
      {
        "path": "verified_profile.model",
        "op": "eq",
        "value_from": "request.payload.model"
      }
    ],
    "action_if_eligible": {
      "set": "request.payload.stream",
      "value": true,
      "before_dispatch": true
    },
    "action_if_tools_present": "select_nonstream_or_reject_before_dispatch_and_record_capability_reason",
    "action_if_no_matching_verified_profile": "keep_nonstream_default_or_reject_explicit_stream_before_dispatch",
    "same_run_transport_switch_after_dispatch": false
  },
  "stream_contract": {
    "request_field": "stream",
    "request_value": true,
    "response_content": "choices[].delta",
    "terminal_marker": "data: [DONE]",
    "provider_native_tools": "not_supported_with_stream"
  },
  "usage_contract": {
    "documented_stream_usage": false,
    "documented_include_usage_parameter": false,
    "documented_stream_options_parameter": false,
    "missing_usage_value": null,
    "missing_usage_meaning": "metering_unknown"
  },
  "unknown_payload_keys": "ineligible_for_automatic_streaming"
}
```

该 JSON 是 #124 可消费的路由合同：当前 `verified_profiles` 为空，所以所有请求均保持非流式；显式要求 SSE 但不匹配已验证档案时，在 provider dispatch 前拒绝。profile 必须绑定已预登记的 provider-live 请求，并记录 `thinking_mode` 布尔值、temperature、max_tokens、messages schema 和 SSE 完成条件；请求值逐项匹配，不允许字段缺省或 `null` 代替已验证值。缺省 `thinking_mode` 永远不匹配，不能借 omission 冒充非-thinking。该规则不表示 Intern 拒绝其它合法 Chat Completions 参数；`top_p`、`n` 或新字段须由对应档案显式验证后才能进入自动 SSE。STAR JSON 工具协议由本地 controller 处理；它不表示其它调用中不存在 provider-native tools。

官方文档还说明服务端在模型 120 秒仍未完成输出时会打断并返回当前结果；这是服务行为说明，不等同于完整 SSE terminal。仓库应依据收到的 HTTP/SSE 证据记录调用状态，并把缺少 `[DONE]` 或中途断流作为未完成/结果未知处理。[官方参数与结束说明](https://internlm.intern-ai.org.cn/doc/docs/Chat/)

### Endpoint 迁移日期

截至本报告核查日 **2026-11-02**，官方迁移公告说明：**2026-11-09** 起旧 Chat/API 入口只保留 `Intern-S2`；**2027-01-26** 起旧入口停用，API 服务迁移到 InternLM Discovery 的 Scientific Models。当前仓库默认 model 已是 `intern-s2`，但 endpoint 仍是旧 Chat Completions URL。#124/#125 的 manifest 必须冻结 endpoint 与 model；不得把未来新入口视作此处 SSE 合同的同一 endpoint，也不得越过 2027-01-26 继续宣称该旧 URL 可用。迁移到新入口需单独核对认证、payload 与 SSE 合同。[官方服务迁移公告](https://internlm.intern-ai.org.cn/doc/docs/%E6%9C%8D%E5%8A%A1%E8%BF%81%E7%A7%BB%E8%AF%B4%E6%98%8E/)

## 当前实现与默认值

| 范围 | 当前值或行为 |
| --- | --- |
| Chat endpoint / model | `llm_client.DEFAULT_API_BASE` 为官方 Chat Completions endpoint；`DEFAULT_MODEL` 为 `intern-s2`。环境变量 `INTERN_API_BASE`、`INTERN_MODEL` 可覆盖。 |
| `InternChatClient` 默认 | timeout 30 秒、retry 1 次总尝试；thinking mode 默认读取 `INTERN_THINKING_MODE`，未设置时本地为 `None` 且请求体省略该字段；官方列明 Intern-S2 的 provider 默认值为 `True`，所以 omission 不能解释为关闭。此默认组合的实际托管行为未经 provider-live 验证。每次 `chat()` 默认 `temperature=0.2`、`max_tokens=4096`。 |
| `InternModelAdapter` 默认 | `temperature=0.2`、`max_tokens=16384`；`client_timeout`、`client_retry`、`thinking_mode` 均默认为 `None`。 |
| STAR pipeline 默认 | 构造默认 adapter 时覆写为 `client_timeout=180`、`client_retry=3`；adapter 仍是非流式 `InternModelAdapter`。若采用流式，当前需注入 `InternStreamAdapter` 并启用现有 streaming 分支。180 秒本地 timeout 高于官方文档所述 120 秒服务端中断点。 |
| 当前 SSE body | `model`、`messages`、`stream=true`、`temperature`、`max_tokens`；`thinking_mode` 仅当非 `None` 时发送。当前实现不发送 `tools`、`tool_choice`、`include_usage` 或 `stream_options`。 |
| STAR 的工具协议 | `InternModelPort` 把角色请求编码为 JSON 回复协议，再由本地 Registry/控制器处理工具提议；它不是 provider-native `tools` 请求。这不能代表 `InternChatClient.chat(tools=...)` 或 `InternModelAdapter.complete(..., tools=...)` 的其它调用形态。客户端可传 `tools` 并捕获返回 `tool_calls`；它当前没有 `tool_choice` 参数。 |

以上是仓库源码默认和可选配置的静态核对，不读取 `.env`，不代表任何本地覆盖值或当前账号行为。官方参数总览提到的 OpenAI SDK 兼容范围有限；逐项参数以该页面的 Chat 请求参数表为准。

## 状态分层

报告和测试按三个互不替代的维度解释：

| 维度 | 可复核状态 | 规则 |
| --- | --- | --- |
| Transport | `complete`、`unknown`、`error` | HTTP 成功且 SSE 有 `[DONE]` 才能作为完整传输证据；strict-completion 调用还要求非空 `finish_reason`。timeout/断流/无终止标记保持 unknown。完整响应的结构错误单独记录 error。迟到完整响应只更新原 attempt 的证据，不复活已结束的 Job/task。 |
| Usage | `known`、`missing/unknown` | 有效 usage 字段才可计量；缺失为 `null`、`usage_source=missing`、`metering_status=unknown`。保留预留规则不因传输完成或任务成功而改变。 |
| Task | `success`、`protocol_failed`、`unknown/interrupted` 等 | 由完整文本是否非空、JSON/schema 是否有效及 STAR 状态机结果决定。完整传输可有空内容并导致 `empty_response`；这是已知 task/protocol 失败，不是网络 unknown。完整传输且 usage 缺失仍可能通过 task，但预算预留可能限制后续调用。 |

`InternStreamAdapter` 负责解析增量、终止、usage 和 request attempt；`InternModelPort._complete_stream` 才负责空答案及 JSON/schema 校验。`KNOWN_PROTOCOL_FAILURES` 保留完整响应的已知协议失败；断流产生的 `AdapterError` 仍按未知远端结果处理。外层 Job 的最终状态、整题审查和交付绑定仍须独立查看。

## 故障覆盖映射

所有新增和引用的测试均为 loopback/scripted，不进行 provider HTTP 请求。

| 场景 | 公开接缝 / 测试 | 断言重点 |
| --- | --- | --- |
| 正常终止、无 usage | `tests.test_intern_sse_123.InternSSEContractTest.test_complete_without_usage_is_transport_success_with_unknown_metering` | 返回完整 envelope 和 `success` attempt；usage 为 `null` / missing。 |
| 完成后末尾 usage-only 事件 | `tests.test_intern_sse_123.InternSSEContractTest.test_usage_only_tail_after_finish_is_preserved` | 保留末尾 usage，不将 `choices: []` 误读为额外答案文本。此为适配器解析覆盖，不是 Intern provider 对该事件形态的承诺。 |
| 空文本但传输完成 | `tests.test_intern_sse_123.InternSSEContractTest.test_empty_content_can_complete_transport_without_proving_task_success`；`tests.test_cp05_public_job.CP05StreamingMatrixTest.test_public_stream_matrix` 的 `empty_body` 子场景 | adapter 可以 transport success；STAR public Job 将其标为 `empty_response` protocol failure。 |
| 畸形 SSE JSON | `tests.test_intern_sse_123.InternSSEContractTest.test_malformed_event_is_sanitized_and_has_no_result` | 不构造完成 envelope，错误只暴露安全类别。 |
| 空 `finish_reason` 加 `[DONE]` | `tests.test_intern_sse_123.InternSSEContractTest.test_empty_finish_reason_with_done_is_not_strict_completion` | 官方文档把空字符串解释为尚未完整返回；严格模式现在拒绝它并保留 unresolved reservation。 |
| 中途断流 / timeout | `tests.test_intern_sse_123.InternSSEContractTest.test_disconnect_and_timeout_never_return_a_complete_envelope`；`tests.test_star_product_streaming_recovery.StarStreamingRecoveryTest.test_mid_stream_timeout_keeps_unknown_reservation_and_requires_explicit_retry`；CP-05 `disconnect` 子场景 | 没有完整 envelope；attempt 保留未知用量，Job 要求显式新身份重试。 |
| `[DONE]` 但缺 `finish_reason`、缺 `[DONE]` | `tests.test_star_deadline_98.DeadlineContractTest.test_stream_done_without_finish_reason_is_unknown`、`test_stream_eof_without_done_has_distinct_unknown_category` | strict completion 下记录不同终止缺口，保留预留，不把有部分 usage 当作 task 完成。 |
| timeout 后收到完整迟到响应 | `tests.test_star_stream_late_race_98.StreamLateRaceTest.test_timeout_does_not_overwrite_inflight_late_success`；CP-05 `late` 子场景 | 迟到 usage 结算到原 attempt；已失败的 Job/task 不复活。 |
| 迟到但仍不完整 | `tests.test_star_stream_late_race_98.StreamLateRaceTest.test_partial_late_usage_before_timeout_keeps_unknown_reservation`、`test_invalid_incomplete_late_stream_remains_unknown_after_timeout` | 已观测 usage 可留作已知部分；task/transport 仍未知，reservation 不释放。 |
| 完整多次调用但 usage 缺失 | `tests.test_cp05_public_job.CP05StreamingMatrixTest.test_public_stream_matrix` 的 `missing_usage` 子场景 | 在预算尚足时 Job/task 可成功，同时每个 attempt 的 usage 仍为 null / unknown。 |

## #124 最小集成指针

1. `showcase/star_product_runtime.py` 的 `SHOWCASE_STAR_ADAPTER` 注入和 `showcase/star_product_pipeline.py::StarProductPipeline.run` 是 STAR 适配器与 transport 配置的组装边界。为 #124 增加单独的 provider transport 选择项；不要复用 `stream_activity` 作为传输开关，因为 pipeline 目前用该活动/观测 feature 决定 `InternModelPort(streaming=...)`。
2. `showcase/solver_harness/intern_port.py::InternModelPort.complete` 是精确的 per-call dispatch seam：现有 `streaming` 分支选择 `stream_complete`，否则走 `adapter.complete`。在这里或一个独立的小型纯策略模块执行 endpoint + 当前请求能力判定；STAR JSON 协议请求明确不带 provider-native tools。
3. `showcase/adapters.py::InternStreamAdapter.stream_complete` 已实现 SSE 发送、断流、完成 envelope 和 attempt 记账；本票只收紧了严格模式对空 `finish_reason` 的校验。`showcase/request_transport.py::INTERN_S2_LIVE_ENDPOINT` 是已有 endpoint 常量。#124 可在这些 seam 周围小幅接线，不需要把策略、兼容表或配置扩展堆进大型 `adapters.py`。
4. 保留一般 adapter 的 native-tool 路径：`InternModelAdapter.complete(..., tools=...)` 会在注入 client 支持时转发 `tools`，`InternChatClient.chat(..., tools=...)` 负责发送/捕获 provider tool call；这类请求按上方规则选非流式。增加流式优先逻辑时不得因为 STAR 本轮仅使用 JSON 工具协议而隐藏或破坏此调用路径。

测试 transport selector 时可注入 loopback/scripted client，断言真实序列化 payload 的 endpoint、`stream`、`tools` 和 thinking 字段；任务/schema 的验收继续走 `InternModelPort` / public Job，不在 adapter 单测复刻业务协议。

## 尚未验证与执行边界

- `thinking_mode` 与 `stream=true` 的托管服务联合行为、当前账号/模型白名单、实际终止事件、usage 是否可返回及 usage 是否完整，均未通过 provider-live 验证。
- 文档没有证明 `include_usage` 或 `stream_options` 可用；当前代码不发送这些字段。未经新的独立登记和授权，不对这些字段发探测请求。
- 不将本地 scripted 通过写成 Intern provider 兼容、数学能力提升、完整 tool loop 或普遍可靠性证据。
- 任何真实 provider 请求都必须先建立针对该批次的独立预登记，冻结请求与 token/时间预算、停止条件和 unknown 后处理规则，并取得本批次执行授权。本文没有授权此类请求。
- `docs/evals/star-stream-usage-96.md`、旧 #96 batches 和其运行身份保持原样。

## 本轮验证

离线聚焦集合共 **19 项通过**：新增 8 项（7 项 adapter seam 行为与 1 项报告规则合同）、CP-05 public stream matrix 1 项、既有 `StarStreamingRecoveryTest` 7 项、严格终止合同 2 项、迟到完整响应 1 项。TDD 先复现了空 `finish_reason` 被接受的失败，再以流式适配器的非空检查修复。执行时设置 `PYTHON_DOTENV_DISABLED=1`；所有测试使用合成数据和 loopback/scripted transport，没有真实 provider 请求或凭证读取。
