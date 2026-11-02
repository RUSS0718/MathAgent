# SP-07 记忆、Skill 与局部指导合同

日期：2026-10-23；基点 `ba675977`，责任 #63 的 SP-AC-11/12/25/26；来源 SC-014/015/020/028..033/037，STAR AC-12/14/21..26/31/33。

沿用认证 Job HTTP → 原 STAR controller → InternModelAdapter/S3 → Run/SSE/report/Evidence，不新增执行循环。先公共失败用例、最小实现、聚焦、offline、release，再记录实际结果。官方冻结入口不变。

- 明确 blocked 的步骤触发 stuck；已知终止工具 timeout、tool_error/不匹配触发 timeout/code_issue。远端和非 managed timeout 的 unknown 保持待复核，不自动重发。局部恢复有次数界限且仍受原账本、取消和 deadline 约束。
- Guidance 与跨计划 Decision 分开持久化；specific_task 成为下一实际角色请求目标。retry/explore/traceback 由控制器核验并执行；`replan` 只进入独立 ReplanDecision（spec #70 统一裁决合同，ALIGN-03 #73 修订原"由 Guidance 直接换计划"的表述），仅当前转换的有效 APPROVE_REPLAN 才归档换计划并传入本次禁止方向与救援成果；纯推理同时改变请求权限与运行时工具拒绝。
- 七类协议各有版本、触发和权限；实际出站系统层包含非空协议。公开仅 ID/version/trigger/permissions、投影版本及摘要指纹，不公开完整 prompt、数学报告或隐藏推理。
- 本地会话按角色/计划/步骤隔离，最新权威投影覆盖历史；同题 Meta 连续、不同 Run 不串题。重建再注入可验，进程崩溃续算由 SP-08 验收。
- 多项白名单非代码研究沿原 S3 派发，失败/unknown 保留；可用结果带 task 来源汇总进入新计划，不能升级为已证事实。

故障注入、scripted、live、replay 分开标注；公共验收和最小旁路探针必须识别去掉协议、任务消费或权限栅栏的失败。完整生命周期 UI 属 SP-12，此片沿现有事件展示接缝。
