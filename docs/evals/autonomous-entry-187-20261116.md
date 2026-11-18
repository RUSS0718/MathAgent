# #187 自主求解入口验收

2026-11-16。代码源码45bd678，沿用faithful-autonomous-population分支。需求与设计见[任务合同](../engineering/autonomous-entry-187-contract.md)。

## 实现与边界

普通入口显示「自主求解（推荐）」；高级设置默认折叠，原生select按自主调度、资源与候选交付、调试与兼容分组。手选状态、边界说明及一键恢复可见。未启用自主服务时保持兼容入口和原reference名称。只修改两个Vue组件及浏览器验收，没有后端、依赖、预算或baseline改动。

## 验收映射

| 合同 | 公共入口与断言 | 证据 | 结果 |
| --- | --- | --- | --- |
| C1 | 默认推荐可见，选择器默认隐藏；320/1440无横向溢出 | faithful-entry.spec.ts默认提交与两宽度案例；green-browser截图 | pass |
| C2 | 三个optgroup、推荐项绑定star_reference；禁用候选项不可选 | advanced modes案例；本机live-observation.json | pass |
| C3 | 手选star_limited提交原值，恢复后仅再次提交star_reference；仅切换选项不提交 | advanced modes及两宽度案例 | pass |
| C4 | 未就绪阻止按钮和Enter；未启用自主服务保持legacy | 原有未就绪与兼容浏览器案例 | pass |
| C5 | 原生summary键盘Enter展开、两宽度截图、浏览器无pageerror；双轴审查无阻塞 | green-browser.log，review.md及本机live截图 | pass |

证据目录为被忽略的`artifacts/autonomous-entry/`，不提交浏览器状态或运行raw。

## 命令与观察

- 修改前运行`npx.cmd playwright test faithful-entry.spec.ts --grep "ready service defaults|advanced modes remain|autonomous preset disclosure" --output ../../../artifacts/autonomous-entry/red-browser`：4项按预期失败（旧推荐文案、旧高级选项/无分组）。见red-browser.log。
- 实现后`npx.cmd playwright test faithful-entry.spec.ts --output ../../../artifacts/autonomous-entry/green-browser`：14/14通过，12.5秒，覆盖既有任务改题/澄清/防重和本次入口。
- `npm.cmd run check`：依赖策略、类型检查、77项单测、构建通过。现有大于500kB打包提示仍存在；不属于本票优化目标。
- Modern Web Guidance检索并读取content-first-noise-reduction、forms、accordion，沿用原生details/summary/select，无新增依赖。CLI报告本机技能版本较旧，已读取当前检索返回指导；没有更改用户技能安装。
- `node artifacts/autonomous-entry/live-check.mjs`在本机8103核验构建产物：推荐入口及3组预设、切换并恢复、320px无溢出、0浏览器错误。新页面发生1次`/api/new_chat`空会话请求，0求解任务提交、0新增模型调用。只验证界面及协议选择，不作数学效果结论。
- 首轮本机观察脚本将预期空会话创建误判为意外写请求；随后试图复用空会话但列表无已保存空会话而停止。修正观察脚本白名单后最终通过；未为此更改产品代码或后端边界。

## 最终门禁

冻结源码 `45bd6780ffe43c6c20b10fae21e18f79bf59dd59`，运行
`uv run python scripts/run_final_gate.py --root . --output-dir artifacts/final-gates --run-id entry187-gate01`。
证据 `artifacts/final-gates/entry187-gate01/`：6/6阶段通过，耗时2120.734秒，
`source_changed=false`。源码hash为
`9fa31692926aa15ea53ae2c6431d2ebd4a8d65f0fa12dd5d1a6d150c64ea5350`。

- 快速检查通过，baseline字节和官方入口边界由既有检查覆盖。
- 后端完整离线检查：2215项，0失败、0错误、42项跳过；跳过不算已执行通过。
- 发布检查27项通过。
- 前端安装、审计、类型检查、77项单测与构建通过，审计0漏洞。
- 双轴审查：Standards无阻塞，Spec无阻塞，记录在`artifacts/autonomous-entry/review.md`。

门禁后仅更新本文与文档索引。最终文档交接提交可通过
`git log --oneline -- docs/evals/autonomous-entry-187-20261116.md`定位，不将该文档提交误称为门禁源码。

临时检查从30分钟调整为10分钟。完成核验时发现Windows PowerShell按默认编码读取
无BOM的脚本，中文绝对路径损坏，导致该监控未按预期归档和清理；任务结果码0
不能证明状态检查成功。已在当前PowerShell执行完成归档并删除定时任务及临时脚本。
这不影响独立后台门禁及上述状态证据；未宣称自动通知成功。
