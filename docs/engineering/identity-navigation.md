# 身份链导航

身份、恢复、重试或最终交付绑定相关修改，从本页开始。本文只定位当前代码与测试；适用范围是显式 Showcase/STAR 路径，不是官方 `user_agent.ReasoningAgent` 路径，也不提供 provider-live 或数学能力结论。

## 按问题定位

| 关注对象 | 源码职责 | 直接测试 |
| --- | --- | --- |
| 公开 request attempt | [`llm_response.py`](../../llm_response.py) 的 `public_attempt` 负责字段白名单、脱敏和可空计量；[`showcase/request_attempts.py`](../../showcase/request_attempts.py) 负责捕获与发布；[`showcase/run_budget.py`](../../showcase/run_budget.py) 的 `RunBudgetLedger` 负责持久预留、结算和同版本读取；[`showcase/evidence.py`](../../showcase/evidence.py) 将其投影进报告和 Evidence。 | [`tests/test_request_attempts.py`](../../tests/test_request_attempts.py)、[`tests/test_worker_death_attempt.py`](../../tests/test_worker_death_attempt.py)、[`tests/test_star_stream_late_race_98.py`](../../tests/test_star_stream_late_race_98.py) |
| 内部 call lineage | [`showcase/solver_harness/calls.py`](../../showcase/solver_harness/calls.py) 的 `retry_parent_id`、`latest_retry_id`、`dispatch` 和 `retry_call` 维护重试链；`retry_of_internal` 是新记录的内部父 ID，旧记录由 `retry_parent_id` 兼容读取。[`showcase/run_budget.py`](../../showcase/run_budget.py) 的 `public_solver_call_id` 将内部 solver call ID 投影为 Run 作用域的公开别名；[`showcase/solver_harness/storage.py`](../../showcase/solver_harness/storage.py) 的 `_PublicCallLookup` 在读取时接受公开别名。 | [`tests/test_star_product_continue_identity.py`](../../tests/test_star_product_continue_identity.py)、[`tests/test_star_product_recovery.py`](../../tests/test_star_product_recovery.py) |
| recovery projection | [`showcase/star_product_recovery.py`](../../showcase/star_product_recovery.py) 的 `recovery_projection` 从内部 calls/events 计算公开的 `unknown_calls`、`retries`、`protocol_failures` 和 `unknown_tools`；`authorize_resume` 校验公开旧 ID 与新 ID，`resume_solver` 重新进入所属阶段。 | [`tests/test_star_product_recovery.py`](../../tests/test_star_product_recovery.py)、[`tests/test_star_product_align_recovery.py`](../../tests/test_star_product_align_recovery.py)、[`tests/test_worker_death_attempt.py`](../../tests/test_worker_death_attempt.py) |
| delivery binding | [`showcase/solver_harness/final_binding.py`](../../showcase/solver_harness/final_binding.py) 的 `review_record`、`review_binding` 和 `delivery_verification` 校验整题审查来源与当前答案；[`showcase/final_evidence.py`](../../showcase/final_evidence.py) 的 `artifact_identity` 与 `bind_verification` 维护文本身份和追加历史；[`showcase/star_result_semantics.py`](../../showcase/star_result_semantics.py) 输出只读语义投影。 | [`tests/test_star_product_final_binding.py`](../../tests/test_star_product_final_binding.py)、[`tests/test_star_product_semantics.py`](../../tests/test_star_product_semantics.py)、[`tests/test_final_evidence.py`](../../tests/test_final_evidence.py) |

## 关键边界

- `request_attempts` 是物理 HTTP attempt 的公开投影；`attempt_id`、`logical_call_id` 和 `solver_call_id` 处于不同层级。缺失 provider 用量保持 `None`，公开记录不携带完整 prompt 或隐藏推理内容。
- solver call 的内部链路使用内部 `call_id` 和 `retry_of_internal`。公开 recovery 只使用 `public_solver_call_id(run_id, internal_id)` 生成的别名；需要追踪链路时先调用 `retry_parent_id`，不要直接把公开 `retry_of` 当作内部 ID。
- `recovery_projection` 把未被替换的在途/未知调用列入 `unknown_calls`；已知协议失败单独列入 `protocol_failures`。未知结果需要显式的新身份重试，不能由普通 resume 自动重发。
- delivery binding 以实际完成的 `whole_solution_verifier` 调用、Run、计划版本、attempt、候选版本和请求中的答案 artifact 共同校验。当前文本改变时返回 `artifact_changed`，不会继承旧文本的整题审查绑定。

## 相关合同与核验入口

- [RB-04 产品结果语义](star-rb04-result-semantics.md)：`whole_review`、`binding`、`transport` 和 `formal_verification` 的公开含义。
- [SP-08 安全恢复合同](star-product-sp08-contract.md)：unknown、显式新身份和恢复边界。
- [SP-10 整题审查与交付绑定合同](star-product-sp10-contract.md)：实际审查来源、文本版本和改写降级。
- [工程门禁](development-gates.md)：快速、完整和发布检查的仓库入口。

这些测试主要使用受控 HTTP、故障注入、进程退出或 replay。通过它们只能确认相应工程接缝和公开投影可达；能力、provider-live 兼容性和数学正确率仍须依据独立验收记录判断。
