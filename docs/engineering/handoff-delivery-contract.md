# 显式工程交接与格式交付实验合同

状态：用户于2026-11-06批准的独立策略实验；不替换SP-05/SP-10及#127/#128原验收。

## 目标与最小实现

在可信服务配置中显式选择`acceptance_mode=handoff`，默认仍为`strict`，HTTP请求和模型输出不能选择模式。复用当前Python编排、角色协议、调用身份、预算账本、工具隔离、持久事件与整题审查绑定，不新建第二套编排器。

有效步骤审查的CHALLENGE数学异议不再驱动重复Challenge循环，而是记录为`REVIEWED`并将报告及异议作为**未经证明的草稿**交给后续角色。TRACE_BACK及PROPOSE_REPLAN是显式控制请求，仍交由既有Meta/回退处理，不当作普通草稿略过。只有真实ACCEPT仍可形成accepted_results；未接受报告不得升级成事实、证明或已接受依赖。最终生成明确区分有效事实与未经证明草稿，整题Verifier看到同一份草稿和实际完整候选。

整题审查ACCEPT或REJECT都可结束本实验，但对含异议步骤的运行，工程交付与数学接受分开记录；保持`completed_unverified`及公共`NEEDS_REVIEW`语义，不伪造`completed_llm_reviewed`、Job数学成功或旧Issue PASS。最终REJECT原样持久化，并通过既有review_binding核对真实调用、Run/plan/attempt、候选版本和同文本身份。

未知远端请求、未修复JSON/schema错误、矛盾ACCEPT、工具请求未履行、身份错误、预算/取消、缺失整题审查或文本改写仍阻止工程PASS。best-effort=false；不在预算结束后选用旧候选。全题和每调用预算以新manifest冻结值为准，不修改旧Run。

## 验收与验证

先以相同的两步报告、CHALLENGE与最终REJECT复现现有数学门槛（RED），再验证显式模式能交接报告与异议、生成非空答案、完成真实审查及同文本绑定，accepted_results不出现被拒绝报告。默认模式保持原停止；非法裁决、预算不足、未履行工具、未知结果及文本改写均不得工程PASS。公共Job接缝验证服务配置、实际HTTP上下文和持久终态，不只断言辅助函数。

线上沿用simple和octagon-colorings原样完整分母2，新源码/manifest/Run身份及已批准预算，串行运行。独立记录工程交付、数学审查、原Issue核验和usage；任何工程FAIL/UNKNOWN不报工程PASS。原#127未满足时保持open，#128不启动。

## 收益、成本与风险

局部接线只改变显式实验的步骤推进和最终交付策略，避免独立编排器重复预算、工具及绑定机制。代价是草稿上下文增加，以及未接受的前提可能影响后续答案；用明确的草稿字段、原审查意见和保守数学状态暴露该风险。此实验验证工程交接，不保证数学正确或完成，不宣称能力提升。

修改前独立策略审查（Locke，01a1ae99-1444-7991-9e58-fbec88d5c981）支持局部接线；独立编排器的额外状态/预算/恢复维护成本超过本次收益。主线程选择局部策略，沿用真实负面裁决与既有绑定，公开Job不能因工程PASS自动变成数学成功。这是用户批准的策略调整，单独计数，不把历史数学分歧追记成代码bug。

## readiness-29之后的输入去重及提供方错误边界

真实第10步返回finish_reason=error/INPUT_LENGTH_ERROR，确认输入重复与错误分类缺陷。独立策略审查（Hypatia，01a1aee5-2aa0-77d0-8d25-4a656ddbeae1）选择局部精确去重和通用提供方终止分类，不引入压缩框架或新编排器。只在detached历史中，旧reviewed_drafts完全等于当前前缀、且Run/非空session_key/handoff模式均匹配时，改用可还原前缀引用；当前完整草稿保留一份，状态投影只引用当前请求。原持久history、响应、报告和回执保持，不匹配或身份缺失不去重。

完整收到的finish_reason=error在JSON解析之前记为provider_generation_error/provider_failed并终止，不进入格式修复。该规则不匹配任何具体错误正文；真正stop+非法JSON仍有既有一次修复，未完整流仍UNKNOWN。取消后的终态不被迟到提供方错误覆盖。所有身份、预算、工具、整题审查与最终绑定门槛保持。

字节重放和局部测试只证明消除已识别副本及分类正确，不证明达到提供方精确token上限（未知），也不保证后续完成。下一批必须新源码、manifest和Run，不恢复旧29。
