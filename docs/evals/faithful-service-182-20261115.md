# #182 状态、控制与恢复组合验收

日期：2026-11-15（Asia/Shanghai）；起点 `f563ecb4289b265fb050ac2976620ca79ca20804`。[G2 合同](../engineering/faithful-service-182-contract.md)。本票只整合已有控制与状态，不代表 #168 完整服务或数学能力提升。

| 合同 | 公共入口与断言 | 证据（artifacts/issue-182/） | 结果 |
| --- | --- | --- | --- |
| G2-1 | Job GET 投影安全暂停请求、暂停、切换收敛、unknown 和未完成；终态优先，按钮依后端动作 | backend-red.json、backend-green-final.json、frontend-browser.log | pass |
| G2-2 | 只读重复读取不改 Solver；unknown 重试需新身份，原预留和截止时间保留 | backend-regression.json；原 test_star_product_recovery 公共合同 | 聚焦通过 |
| G2-3 | 澄清后失效、干预交付绑定、形式范围、撤销上下文及表达来源 | #172/#177/#178/#179/#181 已验收记录；最终门禁复核相关合同 | 前票证据复用，门禁 pass |
| G2-4 | 375/1440 布局、文字状态、后端按钮准入、Enter 暂停、详情入口，无横向溢出 | frontend-browser.log、frontend-browser/、frontend-clarification.log | 受控浏览器通过 |
| G2-5 | 既有真实答案的刷新、重开深链、服务重启后读取，零写请求 | read-before-restart.json、read-after-restart.json、read-final.mjs、mobile.png | pass |

复用真实 Run `run_2fa0391d0ebdf22aac27bf15dd833482` 与 Session `session_44937cbc096761daf8ce6fab908ee6bc`，答案5、原四次 Request Attempt、teach/report 原独立输出身份保持；原报告可见，Provider 三项用量仍为未知。读取没有新求解、表达或记忆写请求。真实来源是 #169，本次是读取与恢复验收，不是新增模型决策证据。

初始真实浏览器预检查使用未启用 `VITE_F7_SYSTEM_VIEW_ENABLED=true` 的现有 dist，深链回到首页；启用原 F7 构建开关后通过。另一次观察脚本在系统页等待工作台区域超时，修正观察路径后通过；均不冒称产品修复。后端红例中的 unknown 初态最初缺根预算，补齐既有 ledger 后验证恢复许可，未放宽运行时约束。

集成审阅发现 paused 不应走通用 resume，同时必须保留专用父 Run 恢复入口；最终修复、审查及门禁结果在退出时补记。Standards/Spec 独立报告保留在 reviews/。自然并发、热切换、干预、经验采用撤销和自然可信缓存命中等前票未实证能力仍留 #183；本票受控组合不替代这些能力正向证据。

## 最终退出

产品提交 `abb0cc4`，末尾空行维护后冻结 `e62d1458a385ced6c754abceaf586fc09945ebc7`。门禁命令 `uv run python scripts/run_final_gate.py --root . --output-dir artifacts/issue-182/gate-control/runs --run-id gate-01`，六阶段通过，2142.922秒，source_changed=false。完整测试2105项、0failure/error、42skip（不计通过）；发布27项、前端69项、typecheck/build及audit通过（0 vulnerabilities）。11个baseline文件逐项SHA256一致，未重新评分。证据在 gate-control/runs/gate-01/。

最终后端27项聚焦、强化专用API 2项通过；前端4项浏览器覆盖375/1440、键盘暂停、专用恢复端点及权限空时隐藏重试/继续。过期或缺失根预算不再授权，原Job/控制/预算/收据不变且零派发；成功请求同键到期后仍重放既有收据，冲突键拒绝。Standards初轮1项P2、Spec初轮P1/P2各1项均经修复复查解除，证据保留原失败；报告见 reviews/。

G2-3具体回归入口：`test_answer_invalidates_prior_candidate_dependencies_and_presentation`（#172）、`test_native_report_resolves_only_with_bound_parent_review`（#177）、`test_require_formal_failure_keeps_answer_and_marks_requirement_unmet`（形式范围）、`test_revoked_record_filters_persisted_copy`及`test_source_session_opt_out_invalidates_imported_ancestor`（#179），另复用F6/F7保存输出与深链合同；本次完整门禁覆盖这些测试，不能替代自然模型能力证据。

最终源码/构建的真实只读重启比较见 restart-comparison.json、job-before-restart.json、job-after-restart.json：整个budget、request_attempts与final_response逐项相同，phase=completed，4次原Attempt。服务已停止，临时MathAgent-Issue182-Gate检查删除；没有活动长测试要接管。门禁后仅文档变更，不重复产品套件。继续当前模型选择，确切型号与继承未知；保护tests/test.md。#182达到G2工程退出，#168和#183仍未完成。