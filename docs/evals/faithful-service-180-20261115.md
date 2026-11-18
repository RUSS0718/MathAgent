# #180 自主证明缓存开发接线验收

日期2026-11-15（Asia/Shanghai）。基点df5e9d06806e15c9438516fcad33ee88ef03c5f3；产品冻结源码35eaa4350c6ffa265e94156ba8dafbcdc1b4b703。适用[本票合同](../engineering/faithful-service-180-contract.md)和[接续合同](../engineering/unattended-ticket-loop.md)。当前模型及思考设置未主动覆盖，具体型号和继承结果未知。

复用既有S10自动缓存及#178普通形式目标接线；本票只新增命中审计的当前Run、Attempt、状态和L2等级及既有缓存UI显示。默认关闭、可信来源、身份覆盖、当前核验、原根预算、旧L3不得继承和经验授权均沿用原边界。

| 合同 | 公共入口及断言 | 证据 | 结果 |
| --- | --- | --- | --- |
| 可信来源及身份 | 现有S10缓存控制、可信Lean admission，普通答案/L1拒绝 | `artifacts/issue-180/focused.json`，28项0skip | pass（工程） |
| 当前Lean及原预算 | 真实固定Lean两次执行，不同Attempt，原账本tool_calls=2；等级L2 | `red-02.json/log`缺字段失败；`green.json/log`修复通过 | pass（固定内核） |
| 来源/原因/当前回执UI及控制 | 既有公共会话缓存API按所有者/会话授权，UI显示当前审计身份 | `ui-red.log`原失败；`ui-green.log`3项浏览器；28项包含API/控制检查 | pass（受控） |
| 普通输入真实来源及自然命中 | 普通浏览器，真实Intern与Lean，持久Job/Report | live01/02/03原记录 | fail；自然命中not_run |
| 不依赖经验捕获 | 未改记忆授权、捕获或注入 | Standards/Spec报告及diff | pass（静态） |

命令：`uv run python scripts/run_unittest_report.py --summary-json artifacts/issue-180/focused.json --diagnostics artifacts/issue-180/focused.log tests.test_faithful_s10_goal_cache tests.test_faithful_s10_goal_cache_integration tests.test_faithful_s10_goal_cache_api tests.test_faithful_s10_goal_cache_controls`。前端在chat-frontend运行`npx playwright test tests/browser/faithful-goal-cache.spec.ts --workers 1`；Ruff和diff检查通过。初次测试因旧硬编码manifest缺失skip，未计成功；从#178留存可信manifest恢复忽略目录后取得真正红绿。

## 真实运行边界

三次均经普通UI提交，明确公开API启用本会话缓存；无拦截或手填形式策略。配置来自#178，根预算48模型/48HTTP/8工具/262144tokens/1100秒不变。前两次Lean输出上限262144，第三次仅改1048576。服务、观察器、配置与源码字节身份在各live目录封存。

- live01：Job `run_2a7c6a6905a6ee8a37d1f5a0706a7a40`，4次模型调用，正确恒等式数学答案并succeeded；Lean输出425499字节超限，formal_output_limit，无可信来源。先前“未选择形式化”的诊断已纠正，实际选择并执行过Lean。自然命中未执行。
- live02：Job `run_410fd3de8ce17f7d4b48dd08fba1bd32`，明确Lean请求，5次模型调用后failed，无可信来源；不算正向验收。
- live03：Job `run_96c341281421cdbcde28ff4ee1e601c5`，输出上限修正后仍unsupported及根预算耗尽，5次模型调用后failed，无可信来源。未通过不代表模型或缓存普遍不可用。

每轮`run1-final.json`、`run1-report.json`、`run1-cache.json`及终态截图为公共GET/UI证据；观察器失败不覆盖Job状态。provider缺失用量维持unknown，不重发。缓存events只有启用，不能宣称命中、采用或当前证明资格。固定内核和受控UI不替代自然能力。自然命中、真实当前回执UI和跨进程恢复仍留#183，#168未完成。

双轴报告`artifacts/issue-180/reviews/{standards,spec}.md`：Standards无阻塞；Spec无新增代码偏差但指出真实证据P1缺口。开发退出依合同显式调整，原完整目标保持在#183，不把该缺口伪装成已通过。

## 最终工程退出

`uv run python scripts/run_final_gate.py --root . --output-dir artifacts/issue-180/gate-control/runs --run-id gate-01`：六阶段通过，耗时2121.219秒，source_changed=false。2095项测试、0failure/error、42skip；恢复可信manifest后原7项Lean跳过实际执行，skip不计通过。发布27项、前端安装/审计/检查通过；既有大bundle提示不作新增改动。证据`artifacts/issue-180/gate-control/runs/gate-01/{status.json,repository-check/tests.json,fast.log,release.log,frontend-check.log}`。快速检查包含官方baseline字节一致。

Spec复核`reviews/spec-recheck.md`确认调整透明、开发退出无新增阻塞，原真实证据P1仍未通过。#183移交评论6881008410。达到有效开发退出条件，不能称完整服务通过。仅文档收尾发生于门禁后，最终交付HEAD另见交接及Issue完成评论。所有live服务/观察器、gate进程与MathAgent-Issue180-*临时检查已结束清理，无监控转移。
