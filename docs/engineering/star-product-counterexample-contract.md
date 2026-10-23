# SP-13 主动反证协议修复合同

状态：已实施并通过公共受控验收；这是独立上游复核发现的修复切片，不关闭 SP-13，不解锁完整模式。

归属：#69 的上游一致性修复前置，补充 SC-014/SC-037 与 SP-AC-25 的按需协议行为。实际结果见[验收记录](../evals/star-product-counterexample.md)。

## 来源和范围

固定来源为 [原 STAR 的 Verifier 协议](https://github.com/Julius-Woo/STAR-PolyaMath/blob/5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d/.github/skills/verifier-review-protocol/SKILL.md#L62) 的
`Adversarial sub-check for sharpness/optimality claims`。答案承载、最值、最优性或充要条件断言缺少双向证明时，Verifier 必须先委派独立非代码反证任务；未找到反例不能把未证方向提升为 Lemma。

本项目采用结构化 Verifier 声明，不添加数学关键词检测器，也不声称控制器能判断任意证明的充分性。Verifier 可提交 `answer_claim`：
`claim_index` 指向当前 StepReport 的实际 claim，`both_directions_proved` 标识证明是否完整，
`assumptions` 和 `approach` 描述假设与原方法。协议要求适用时声明；控制器核验类型、索引和非空上下文，不能接受模型指定其他 Run、工具或任务身份。

## 执行与状态

1. 当 `both_directions_proved=false` 时，不论原裁决是否 ACCEPT，都在决定步骤接受前执行独立 `researcher` 调用，携带原题、准确 claim、假设、原方法和已有 Conjecture。每次任务独立会话、空工具白名单，经现有 Intern Adapter、S3 和调用审计。
2. 任务结构化返回 `FOUND_COUNTEREXAMPLE` 或 `NOT_FOUND`、反例、假设核查、被违反结论和搜索范围。返回执行工具或跨题访问指令不符合 schema，不能触发 Registry。未知远端结果保留现有中断语义，不自动重试。
3. 控制器在同一步持久记录来源 Verifier call、研究 call、目标 claim、结果及定性范围。只有持久完成的对应调用才能作为已执行研究；缺少记录、非法响应或无剩余预算不得推进步骤。
4. FOUND 导致 CHALLENGE/Logic FAIL，提供具体反例供双方继续核查。NOT_FOUND 仍为 CHALLENGE/Goal PARTIAL，保留未证明方向的 Conjecture 身份，不把有限搜索当证明。后续补齐证明的新报告才可按正常双 Gate 通过。
5. 公共事件仅投影阶段、角色、结果枚举和状态，不泄露研究完整 prompt、原报告或私有 step ID。已有官方路径和完整模式拒绝不变。

## 验收接缝与计划

接缝已由 #56 和本次任务指定：认证 `POST /api/agent/jobs`，同 Job 的 report、SSE 和实际出站 HTTP 请求。使用有限 scripted HTTP、临时 SQLite，不直接造 Harness 状态或查询私有 SQL。

- 先增加公共 Job 的 FOUND 用例，确认未实现时失败；最小实现后验证独立研究、上下文、工具白名单、同 S3 计费和 CHALLENGE。
- 增加 NOT_FOUND、非法目标/越权响应、无剩余额度及刻意跳过研究的反例，验证缺失证明不能被 ACCEPT。
- 聚焦测试、相关 STAR/端口回归、Ruff 和 diff 检查；合入最新集成后重跑相关回归并提交中文规范主题。

反旁路测试允许显式替换最小研究调度点；其目的仅为证明公共验收能识别被跳过动作，不把替换路径当产品实现。所有证据标为 scripted/fault-injection，不作数学能力提升或完整发布声明。
