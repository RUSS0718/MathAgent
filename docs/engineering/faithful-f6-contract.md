# F6 证据驱动讲解与独立输出合同

状态：实施中；本文件保存要求，实际结果见 [F6 验收记录](../evals/faithful-f6-20261111.md)。

## 来源与实施边界

需求为 [#152](https://github.com/RUSS0718/MathAgent/issues/152)，对应 Faithful AC19、AC20、AC26 的交付部分；依赖图见 [#146](https://github.com/RUSS0718/MathAgent/issues/146)。接受规格位于 `docs/wayfinder-chat-output-prototype-20261106` 分支的 `docs/specs/mathagent-faithful-implement-spec-20261107.md`，审计基线为 `b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6`。

本次从集成分支 `mathagent-faithful` 的 `b02f8b4824b9cb23c6e1906f29bb47e09f732291` 开始。S06 提供独立表达及旧 Evidence 绑定；F1/S07、F3/S09 已提供图和形式化生产者。前置证据分别见 [S06/S08 退出记录](../evals/faithful-s06-s08-exit-20261108.md)、[S05/S07 退出记录](../evals/faithful-s05-s07-exit-20261108.md)、[S09 记录](../evals/faithful-s09-20261109.md)。S10 的已提交状态以起点 SHA 为准，旧记录中的“尚未提交”仅描述当时快照。

本切片延伸现有 `POST /api/agent/jobs/<job_id>/<mode>`，不新增求解入口。`mode` 为 `solve`、`teach` 或 `report`；POST 的报告表达与已有 GET report 查询分开。官方 baseline 保持字节稳定，默认关闭与 Run 冻结策略延续 S06；旧 Run 不迁移成新的证据策略。

## 验收合同

| 编号 | 公共可见行为 | 失败判据 |
| --- | --- | --- |
| F6-01 | 关键数学段落保留 claim refs、来源版本及限定等级；可展开并定位 Proposition、Inference 和 VerificationRecord | 无关证据被用于断言，链接无目标，或公开私有证明、完整 prompt |
| F6-02 | 无充分来源的断言标待验证；新数学内容取得独立 proposed ProofAttempt，不能进入 Verified Claims | 改写沿用原文审查，或由表达成功自动升级证据 |
| F6-03 | 图、规格或验证来源变化使对应历史表达需重审，保留旧 artifact；形式目标 L2 与原题 L3 分开 | 失效证据仍显示当前有效，L2 自动称原题已证 |
| F6-04 | 输出具有独立请求身份；整理失败、超时或断流时保留原答案并可切回；原 Run 到期不续算、不延长 deadline | 整理覆盖答案，触发隐藏求解或重试，迟到响应串 Job |
| F6-05 | Best-Effort 的 Verified Claims、Unresolved Goals、等级、成本与来源绑定同一快照；部分结果不称完整，无合格候选明确未完成 | 混合版本、将未知成本填零、部分或无候选结果标整题完成 |
| F6-06 | 显式新 Run 采用冻结策略；旧 Run 与关闭状态沿用原合同；输出持久化前核对来源版本 | 默认开启、旧 Run 热迁移、竞争失效后保存为当前 |

测试使用两个现有公共接缝：输出 API/PresentationArtifact 验证绑定、失效、请求身份和交付一致性；真实浏览器验证段落依据、链接目标、原文切换及刷新。复用 S06 与 F1/F3 回归，只为新增行为增加聚焦文件。按 [工程门禁](development-gates.md) 完成双轴审查、相关回归和冻结源码最终检查。

## 独立讲解质量 rubric

本 rubric 与实现测试分开记录。实现者不能用自己的测试通过数代替讲解评分；评审者从输出样本与原始公开报告独立评分，保留理由和样本来源。

各维度为 0–2 分：0 为缺失或误导，1 为存在但需要读者自行补足，2 为明确且可直接核对。

| 维度 | 2 分标准 |
| --- | --- |
| 依据可查 | 关键断言具有可定位、可核对的来源及版本 |
| 范围准确 | 清楚区分原文审查、形式目标核验、原题对应与未完成目标 |
| 讲解组织 | 教学输出按结论、依据和缺口组织；报告输出明确交付范围、成本与来源 |
| 数学忠实 | 未擅自增添结论；新增断言保持待验证，失效来源不复活 |
| 可读性 | 中文表达清楚，状态不依赖颜色，链接和原文切换可使用 |

受控样本评分仅适用于样本本身。真实 provider、自然数学题的讲解质量与独立数学效果分别记录；未执行即 `not_run`。没有预先登记的自然题与独立评分，不声称高质量教学生成或数学能力提升。
