# #176 串行自主干预与成果采用验收

日期：2026-11-14（Asia/Shanghai）。状态：已按授权调整为开发接线验收，最终门禁进行中，尚未退出。父规格 #168 D1；[任务合同](../engineering/faithful-service-176-contract.md)及[接续合同](../engineering/unattended-ticket-loop.md)定义要求。起点 `64a8c98c72252c2d8501e147b231489a462b7106`；真实 GitHub 依赖仅 #170，已 closed；核验快照 `artifacts/issue-176/dependencies-before.json`。

## 现有证据

- 合同提交 `58f9255`；前端 `5f11096` 及空原因字段兼容 `6384a54`。新增只读干预状态和来源/采用记录，接入主工作台及持久报告；保留实验性和最终整题审查说明。
- 前端失败见证 `artifacts/issue-176/ui-red.log`：缺少干预组件。`node --experimental-strip-types --test tests/serial-intervention.test.ts tests/execution-switch.test.ts` 两项通过，`ui-green.log`；nullable reason 的最终聚焦检查一项通过，`ui-null-reason.log`。
- `npm run typecheck` 与 `npm run build` 通过，日志 `ui-typecheck.log`、`ui-build.log`；构建保留既有 chunk 大小提示。
- `npx playwright test tests/browser/serial-intervention.spec.ts --workers=1 --output ../../../artifacts/issue-176/ui-browser` 一项通过，覆盖 320/768/1024/1440 宽度和只读重开，零写请求、零浏览器错误。`ui-browser.log` 与对应截图；仅受控 public report 数据，不是自然模型自主触发证据。

## 真实验收

live01 使用源码 `803cc001783d096ab98590fa34387624558b7559`，配置 SHA256 `9170fa5f39e8262e2ea780a54478bdd14d10e4c6da6531381d3f9a055cf97364`；48 调用/2400秒上界和固定 Python 镜像沿用既有授权。普通浏览器输入正整数方程 `x²+y²+1=3xy` 的全部解及穷尽证明，期望答案不注入模型。Run/Job `run_bb98df2f10cbb06134a7c30bf929e9df` 失败，5 个物理 Attempt 的传输记录均为 success，但 Planner 逻辑调用记录为 timeout / `unknown_outcome`，不能据物理传输成功升级求解结果。未进入干预、未交付答案，unknown 不恢复或自动重发。

证据为 `artifacts/issue-176/live01/diagnosis.json`、`job-final.json`、`persisted-latest.json`、`report.json`、`interventions.json` 与 `job-reopened.json`；五个 Attempt 完整 ID 见 diagnosis。原观察脚本的 GBK 编码错误、重接时误用资源路径导致的 404/401 分别保存在 `observer-failure01.json` / `observer-failure02.json`；修复后只读接回原 Job，刷新前后 Attempt 身份不变，零写请求。可选 goal-cache GET 出现 SQLite 锁错误，不能称干净 UI 正向通过。观察进程最后为 PID23440，服务 PID24012；终态已停服务并删除 `MathAgent-Issue176-live01` 临时检查，见 `service-closure.json`。旧失败不覆盖。

live02 使用最终产品源码 `1b1a05809e6df19d38710dbb8a5a967ea7ad4e01`，配置 SHA256 同上。四次实多项式的两参数恒非负条件题用于降低规划负担；新 Run/Job `run_aa32a95e7b989596fac16682ef680304`，不重试旧 unknown。四个 Attempt 为 `ec0ea00023614b5a9b1800d1b24be58e`、`ad7e4d8290d24589afad47da42189a4d`、`cf4c61ecdd9149e9a41cb5d77a2bdca8`、`a736c5c2baa24bcea985ac57f366b8e7`。物理传输均 success，逻辑调用完成，但 Planner 以 `invalid_planner_checkpoint` 失败，未进入干预、无已验证答案；不能按传输成功计通过。

live02 证据为 `artifacts/issue-176/live02/diagnosis.json`、`job-final.json`、`persisted-latest.json`、`job-reopened.json`、`report.json`、`interventions.json`、`browser-errors.json` 及 `browser-mutations.json`。原根限额和 deadline 未变；只读刷新 Attempt 不变、零新增写请求、无脚本错误。终态截图 `reopened.png` 仍为加载态，不能证明真实 UI 稳定终态或干预展示通过。服务 PID28052、uv PID30088 已按创建时间核对停止，观察 PID18304 已结束，临时检查已移除，见 `service-closure.json`。

两次有明确诊断目的的尝试均无自然干预证据，按接续合同调整退出范围，并同步 #176/#183。受控开发证据替代本票的开发接线退出要求，不替代自然触发、真实 F4 成果处理、完整正确交付及稳定真实 UI 正向闭环；这些继续留 #183，失败保持原判。

## 初审及修复

`artifacts/issue-176/reviews/standards.md`：一项 P2 重复适用性检查的判断性建议，未确认硬性标准违规。`spec.md`：P1 实验身份缺少 Run 命名空间、P2 采用后父审查硬编码轮次导致身份冲突；`integration.md` 补充自动干预遗漏独立权限。修复提交 `30cefc6`、`2683206`，合入集成 tip 后为 `1b1a058`。`standards-followup.md` 硬性违规/判断性问题均0，`spec-followup.md` 无新增遗漏、错误或越界；静态复审不充当运行证明。

`artifacts/issue-176/review-fix/summary.md` 是精确证据入口：共享数据库双 Job `p1-red.log`→`p1-green.log`；两轮拒绝后采用的旧回执冲突 `p2-standards-red.log`→`replay-final.log`；消费 Run 检查的删除变异 `standards-red.log`→`standards-green.log`；关闭权限 `permission-red.log`→`permission-green.log`；旧 Run 不补授权 `old-run-green.log`。`focused-final.log` 7项通过，最终回执预留修改后只重跑受影响用例，`replay-final.log` 1项通过。此前个别带 green 名的探索日志包含失败，不能仅按文件名计通过。

初始后端4项及 native17项通过，见 `artifacts/issue-176/backend-evidence/backend-delivery.json`；前端最终翻译后的 build 通过，见 `ui-final-build.log`。来源采用保持 `llm_reviewed`，父账本不复制，最终仍经整题审查。分类证明正向采用与真实进程退出续跑为 `not_run`；额外恢复测试的数据库/快照接线失败已留证并撤除，不能当产品恢复通过。41份工作树 ignored 证据及 SHA256 清单保存在 `worktree-archives/`；managed 归档拒绝移除 primary checkout，因此保留，不绕过删除。实现及审查代理均已关闭。

## 验收映射

| 合同 | 公共入口与断言 | 证据 | 结果 |
| --- | --- | --- | --- |
| D1-1 | 普通 Job，合法串行 checkpoint；冻结及当前权限、原预算/硬停、unknown/取消 | 本票公共7项、permission/old-run日志、native17项 | 受控通过；自然未触发 |
| D1-2 | native 分臂与核验；共享数据库双 Job 的独立来源和身份 | backend-delivery、p1红绿 | 受控通过；真实F4未运行 |
| D1-3 | 采用及消费同一来源核对；拒绝跨Run、陈旧来源及不存在证明；不复制父账本 | SerialAdoptionTest、standards红绿 | 受控通过 |
| D1-4 | 采用专属父审查身份及自身回执重放；原等级、最终整题审查保留 | replay-final、公共Job整题审查 | 受控通过；分类证明正向/进程退出 not_run |
| D1-5 | 工作台及报告来源/等级/采用/继续结果；移动/桌面刷新零写；unknown不重发、取消停止 | ui-browser、公共故障；两场真实diagnosis | 受控通过；两场自然验收失败，真实干预UI未实证 |

机器映射见 `artifacts/issue-176/acceptance-map.json`。这些结果不声明数学能力提升、#168完整交付或未执行专项通过。

## 最终门禁与交接

`1b1a058` 的 `gate-01` 在 offline 阶段因最终 Ruff 检出测试文件4处 I001 导入排序而由所有者中止，见 `gates/gate-01/owner-abort.json`，不计通过。排序修复提交 `1bf47fb`，无行为改变，最终 Ruff 通过见 `review-fix/final-ruff-fixed.log`；语义审查仍适用。

`gate-02` 冻结源码 `3b2934a521faecb0212a323ae8cae04f0cb735bc`：快速阶段通过，offline 2070项中1 failure、0 error、49 skip，耗时1884.508秒，`source_changed=false`。失败为 `FaithfulPopulationJobTest.test_population_can_contract_expand_and_contract_on_new_receipts` 的20秒公共观察超时；后续阶段未执行。原失败保留。单项原代码复验18.972秒通过，已接近观察上限；这支持观察窗口偏紧的解释，未实证具体环境根因。提交 `f34857d` 仅把该三次切换用例 `job_timeout` 改为60秒，保留全部切换、最终交付断言及产品预算/deadline；修后单项19.097秒通过，Ruff通过，见 `gate-timeout-focused/attempt-01.json`、`fixed.json`、`ruff.log`。

`gate-03` 待对包含该修复及本记录的冻结源码执行 `uv run python scripts/run_final_gate.py --root . --output-dir artifacts/issue-176/gates --run-id gate-03`；最终结果待记录。门禁通过不能替代真实能力。最终交接 SHA 另记，纯文档变化不重复运行同源码门禁。
