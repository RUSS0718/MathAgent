# 决策依据验收记录

验收日期为 2026-11-20（北京时间）。验收从 Flask 服务的 `/dashboard` 或原会话深链进入。规格与验收条件见 [星图交接规格](../specs/showcase-decision-evidence.md)。下表中的产物路径相对于集成工作树。

| 工单 | 入口与运行模式 | 观察结果 | 证据 |
| --- | --- | --- | --- |
| #219 真实交接 | `1053f49`，D2 已存会话与受控公开事件，Chromium | D2 同一方向的第 3 和第 15 条消息打开不同的公开依据。受控记录覆盖新消息到达后保留选择、四种动作和相应到达反馈、减少动效、无依据提示以及键盘关闭与焦点恢复。32 项定向回归通过。 | `artifacts/decision-evidence-218/t1/focused.log`，`tests/browser/message-evidence-219.spec.ts` |
| #220 四次方程纠错 | `50d4704` 生产构建，桌面浅色与窄屏深色，模拟 | 显示原候选和 $a=-3$ 反例。修正发布后才显示两个不同正根的条件和 $a>2$。$a=2$ 追问显示 $(x^2-2)^2=0$ 并定位步骤。0 次求解 POST。 | `artifacts/decision-evidence-218/t2/acceptance.json`，`tests/quartic-evidence-220.mjs` |
| #221 实时图文 | `725a137` 生产构建，真实 Intern-S2 | 在普通工作台分别发送纯图和附要求的同一张 PNG。2 次 POST 均返回 202，进入不同的会话与 Job，两个终稿均为 $x=4$。会话刷新和补取证据没有新增求解。 | [题图验收](showcase-image-acceptance-221-20261120.md)，`artifacts/decision-evidence-218/t3/readback/evidence.json` |
| #222 模式和导出 | `666775a`，Chromium 1280 和 390 像素，模拟 | 同题每种模式只出现一份终稿。实际剪贴板和下载文件一致，并与屏幕上的题目、公式、推导、结论、复核、检查范围和模拟来源相符。0 次求解 POST。 | `artifacts/decision-evidence-218/t4/verification.log`，`tests/decision-evidence-report-222.mjs` |
| #223 补条件 | `68e9b96` 生产构建，真实 Intern-S2 | 输入「求这个三角形的面积」后，在同一 Job 补「底 6 厘米，对应的高 4 厘米」。输入版本从 1 变为 2，答案为 12 平方厘米。刷新时 0 次 POST。 | `artifacts/decision-evidence-218/t5/acceptance-summary.json`，`tests/triangle-clarification-223.mjs` |
| #224 D2 历史 | `ff789b6`，Chromium 1280 和 412 像素，已保存的真实记录 | 从历史查看 $a=3$ 和 $x^2-3x+2=0$。刷新保留回放位置与原 Job，0 次写请求。审计的 7 张表与彩排数据一致。 | `artifacts/decision-evidence-218/t6/browser-integrated.log`、`storage-audit-integrated.json`，`tests/archive-replay-224.mjs` |
| #225 关联变式 | `5559398`，Chromium 1280 和 390 像素，模拟 | 独立变式答 $a<-2$ 或 $a=2$，并显示 $a=-2$ 时唯一实根 $x=0$。返回原题保留原条件和 $a>2$。再次打开沿用已有变式。0 次 API 写请求。 | `artifacts/decision-evidence-218/t7/`，`tests/decision-evidence-quartic-variant-225.mjs` |

模拟、受控浏览器记录与真实请求分别记录。图文和澄清基于固定示例，没有进行数学准确率比较。D2 回放基于 [#209 彩排留档](onsite-demo-209-20261118.md)。
