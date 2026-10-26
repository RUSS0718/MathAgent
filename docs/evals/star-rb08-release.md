# RB08 发布与真实实验记录

日期：2026-10-26（Asia/Shanghai）。规格为 [#87](https://github.com/RUSS0718/MathAgent/issues/87)，责任票为 [#95](https://github.com/RUSS0718/MathAgent/issues/95)。集成分支 `showcase-star-robustness` 保持 engineering-preview。工程门禁通过，真实 E1 未通过，E2 未执行。

## 固定版本与证据

最终产品发布、前端、浏览器、资格核验和真实实验均使用 `a10481d4aaf6f61e419eb2abe095a8206faadb4c`。实验入口的源码身份哈希为 `b262c978b2c7172d3dbb2af763d1ccba9a8a5636cf8d0a46034564848a3911f9`，算法见 `showcase/star_experiment_archive.py`。本记录及索引属于实验结束后的文档变更，不改变已验收运行时代码。

离线完整门禁通过版本为 `598cb73f33562deb6b3d1f21441214c2bbcd1f59`。它与最终版本的产品运行时代码相同，仅两个测试文件存在差异，已由最终产品发布全套覆盖。

原文证据位于仓外 `D:/project/工程化MathAgent/notes/star-robustness-20261025/rb08/`。`release-gates.json` 保存源码身份、检查日志哈希和独立审查记录哈希。真实题单、独立答案、完整角色上下文、数据库和运行 raw 均未提交。本页只记录脱敏结果。

可提交的日志身份、检查结果和失败预算见[脱敏证据摘要](star-rb08-evidence-summary.json)。

环境为 Windows 11、Python 3.12.13、uv 0.10.9、Node 24.18.0、npm 11.16.0、Docker 29.6.1 Linux。隔离镜像固定为 `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d`。

## 工程门禁

| 检查 | 实际结果 | 仓外原文 |
| --- | --- | --- |
| `uv run python scripts/check.py --offline` | 742 项，0 失败，1 跳过；六个旁路检查入口通过 | `offline-final-verified.log` |
| `uv run python scripts/check_showcase_release.py` | PASS；742 项，0 失败，1 跳过；入口、冻结哈希和发布合同通过 | `release-final-resumed.log` |
| 前端 `npm ci --no-audit --no-fund` | PASS | `npm-ci-final.log` |
| `npm audit --audit-level=high` | 0 漏洞 | `npm-audit-final.log` |
| `npm run check` | 依赖合同、类型、27 单测、构建通过 | `frontend-check-final.log` |
| 通用 Playwright Chromium | 54/54，通过；未更新截图或阈值 | `browser-general-final.log` |
| 真实产品 Playwright Chromium | 12/12，通过 | `browser-product-frozen.log` |
| 实际 E0/E3 资格核验 | 107 项，0 失败、0 错误、0 跳过；五类旁路命中目标断言 | `qualification.json` |

两项完整后端检查中的唯一跳过均为 `SHOWCASE_RELEASE_GATE=1` 的发布递归保护。Docker 适用用例没有跳过。Playwright 运行真实浏览器；本环境没有 Chrome DevTools MCP，本页不声称执行了 DevTools 检查。

规范轴、规格轴和门禁补修均完成复审。发现并修复了真实题单入源码、数学等价分数评分、非快通道来源校验、迟到用量结算、非流式首文本观测及后续来源门禁问题。普通 Run 异常后的截止语义也已补修。最终两次测试修改分别修正取时断言和真实隔离长链的观察窗口，未增加产品预算。

首轮失败日志 `offline-final.log`、`release-final.log`、`release-final-verified.log` 保留。`release-final-complete.log` 对应进程消失且没有退出码，记为中断，未计通过。最终 PASS 来自实际重新执行的发布脚本，不使用缓存测试结果替代。

## 原注册真实实验

资格核验实际重放旧归档，校验输入完整性及最终交付来源，外部派发为零。旧样本复评不改变其原预登记资格，也不自动满足 #80。

原题单、顺序、数学义务和模型条件在首次真实请求前冻结，清单哈希为 `1fbdf9162388c25644bb0f152d1b04e495d27ac4c73dfd8d04df65a4d65d09e3`。保持 Intern S2、180 秒请求上限、8192 单响应输出上限、retry=3、thinking_mode=true、temperature=0.2，完整参考模式自然路由。

| 原 E1 Run | Job | logical / HTTP / 题目工具 | 已知 tokens | 未结算预留 | 交付耗时 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| 首个算术任务，非流式 | `run_1aa6cda6fd6073488cf49995c3bda2b5` | 3 / 3 / 0 | 4967 | 0 | 76.344 秒 | 答案及解释复核通过，审查与文本绑定一致，E1 门槛通过 |
| 同题，流式 | `run_eb1e66e00bf1be3f07737ba2feb5f489` | 2 / 2 / 0 | unavailable | 28854 | 23.235 秒 | 预算准入不足，整题审查未派发，任务未完成，E1 门槛失败 |

原批次终态为 `e1_gate_failed`：E1 只执行 2/4，另两项未执行；E2 为 0/6。共 5 logical、5 HTTP、0 题目工具，独立环境探针4次。整轮墙钟333.109秒包含准入、运行及独立复核等待，不等于两项用户交付耗时之和。账本已知 tokens=4967，预留=28854，charged=33821；charged 包含保守预留，不是供应商实测消耗。费用未返回，`cost=null`。

数学复核由本聊天主代理完成，与 Intern S2 求解提供方独立，绑定题文及实际答案哈希。它是 AI 复核，不是人工认证或形式化证明。首项实际包含正确算术及解释；第二项交付的只有预算耗尽提示，没有可接受或反驳的数学答案，记为 undecided。

首项是合法 Explore 快通道，`fastpath_no_step_proofs` 不表示缺陷，也不满足非快通道资格。两项均未提供自然非快通道成功，Challenge、Traceback、Replan 的真实自然触发均为 `not_covered`。小样本及未完成流式任务不能支持普遍提速、p95 或数学能力提升结论。

原批次归档位于 `live-round-1/`。16 项文件的不可变哈希已逐项核验。原始 false、失败、预算、审查、独立复核及未执行项均保留。

## 用户授权的一次独立流式诊断复测

原批次结束后，用户明确要求重试。另存 `stream-retry-1/registration.json`，记录授权、原结果哈希、同题同源码同条件以及最多1个Run，不恢复原批次。入口实际再次完成107项、0跳过及五类旁路资格核验，随后只派发这一项流式任务。

复测仍为 failed：2 logical、2 HTTP、0题目工具，交付40.750秒。两次 provider usage 均缺失，保留29193 tokens预留，整题审查未派发。原结果哈希保持不变。复测脚本退出0只表示诊断执行和归档完成，不表示任务或 E1 通过。

两次流式运行合计四次请求均为 HTTP 200、正常 `stop`，`unresolved_attempts=0`、`transport=known`。`unknown_attempts=2` 是各 Run 的缺 usage 计数，不能称为两次网络超时。当前 payload 未显式索取最终 usage 事件，是否支持及是否足以修复尚待核对。实际观察到的是：保守预留未结算，下一审查无法准入。不能把未知用量当零、增加预算或关闭审查来规避。

本轮加单次复测共7次真实HTTP请求，已知tokens=4967，保留预留共58047，费用仍未知。诊断复测不算原E1的第三项，不放行E2。新缺陷及修复验收见 [#96](https://github.com/RUSS0718/MathAgent/issues/96)。

## ROB-AC 逐项边界

下表的“离线通过”仅指本规格公共入口和受控故障合同，不扩展为真实数学能力结论。切片入口见 [RB01](../engineering/star-rb01-offline-acceptance.md)、[RB02](../engineering/star-rb02-computation-evidence.md)、[RB03](../engineering/star-rb03-proof-obligations.md)、[RB04](../engineering/star-rb04-result-semantics.md)、[RB06](../engineering/star-rb06-e3-acceptance.md)、[RB07](../engineering/star-rb07-experiment-coordinator.md)。

| ROB-AC | 状态与证据范围 |
| --- | --- |
| 01 | 离线通过：实际接受来源、多候选、计划、续接、修复与重试选择；RB01与全量门禁。 |
| 02 | E0通过：旧归档校验、零派发重判、两版runner和旧结果保留；资格核验。 |
| 03 | 离线通过：跨Run、伪造、改写及缺来源拒绝；真实非流式快通道合法区分。 |
| 04 | 离线通过：真实隔离无预期值不产生假 mismatch；RB02。 |
| 05 | 离线通过：匹配、不匹配、执行失败、无输出分离；RB02。 |
| 06 | 离线通过：空输出、旧回执与历史恢复；RB02。 |
| 07 | 离线通过；一项真实非流式三调用、答案及解释通过，流式未完成。 |
| 08 | 离线通过：数值与sharp义务对照；RB03；真实E2未覆盖。 |
| 09 | 离线通过：冲突及未完成义务有界拒绝；RB03。 |
| 10 | 公共报告、Evidence、SSE及浏览器通过；真实非流式完成与流式未解状态一致。 |
| 11 | 离线通过：局部范围、改写失效、历史及legacy兼容；RB04。 |
| 12 | 受控HTTP通过；真实流式阶段可观测、非流式首文本为unavailable。 |
| 13 | 受控截止、未知和迟到结算通过；本次真实未触发网络未知，不补造live覆盖。 |
| 14 | 离线通过：完整schema、有界修复和attempt计数；实际资格核验。 |
| 15 | 离线通过：取消、预算、deadline、真实进程退出与恢复；RB06。 |
| 16 | 真实Docker受控验收通过；实际环境探针有独立账本；E2题目工具未覆盖。 |
| 17 | 五类RB06旁路及常规六入口通过；崩溃不算目标断言命中。 |
| 18 | 已归档实际目的、阶段和预算；流式provider用量缺失，保留预留，不能称全部实测。 |
| 19 | 通过：最终门禁、E0及实际E3资格核验先于真实请求。 |
| 20 | 未通过：原E1只执行2/4，流式任务未完成。 |
| 21 | 未执行：E1失败阻止全部E2，无真实三类题求解结论。 |
| 22 | 原批次停止生效，未继续后八Run；用户复测单独注册，不覆盖原账本。 |
| 23 | E3受控机制通过且无真实提供方调用；live三类机制均not_covered。 |
| 24 | 固定身份、失败及独立复核已归档；数学完整交付仅首项通过。 |
| 25 | 工程门禁通过；同运行时离线、最终发布与浏览器原文可核对；跳过单列。 |
| 26 | 明确未完成；本记录不关闭#87/#95，不升级#80或#70。 |

## 工单与后续责任

RB01–RB07（#88–#94）已按自身工程验收关闭。#95和#87保持开放，原因是原注册E1未完成、E2未执行且真实非快通道未取得。#80 的 ALIGN-AC-18仍未通过；本轮补充了最终浏览器和发布证据供AC-19审阅，未宣称其全部其他要求已经满足。#70不自动关闭。

下一修复责任是#96。后续真实复验须有新的预登记及变更理由，保留本页失败与未决预留。官方文件、默认入口及预算不改，不合入main。
