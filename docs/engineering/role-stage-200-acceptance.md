# #200 当前计划双入口工程验收

2026-11-18，Asia/Shanghai。状态：fresh fixer 已修复双轴四项并通过聚焦复验；#199 整体退出仍按实施合同验收。
起点9765244，专属feat/role-stage-plan-200。
前轮已测源码33a79e7e280d2543ce46fd9e112cbb14616eaf84。
已合入集成tip 7e5d8ef（合并提交7acb862）。未改tracker、未推送、未创建PR。
沿用会话当前模型，未指定或更换；无法独立证明宿主的具体型号继承结果。

## 本轮双轴修复与复验（2026-11-18）

本节覆盖下文前轮“未修/待复验”结论。本轮起点 b9e37e0，专属工作树
`C:/Users/CQX/.codex/worktrees/role-stage-200-review/Challenge-Cup-2026`，
分支 `fix/role-stage-200-review`。后端提交 ca536e8，最终源码
`0db5e744c3ea2cd5628d0ccbf6e45c805d374079`。提交后的文档变更不改变该已测源码。

| 审查项 / 合同 | 修复与公共接缝复验 | 证据（本工作树 artifacts/role-stage-200-review/） |
| --- | --- | --- |
| 规格 P2 来源身份冲突；RS-05/22 | 保存及读取复用同一 HMAC 构造，复核 Run、problem、specification、plan、attempt、事件及正文版本；旧引用仍可读为 replaced，改写旧记录身份或引用均 unavailable | red-backend.log：2 测试、8 个失败子场景；green-backend-02.log：8 项通过 |
| 规范 P2 存储职责；RS-06/19/22 | API 调用 solver_harness/storage.py 的 read_owned_snapshot；每次 get_job 归属鉴权，复用 SolverStateStore.get_run 只读事务及 run/problem/config/revision 行与 state 校验，不进入 SolverHarness/current_solver/persisted_solver 恢复路径；损坏来源不修复 | 同上；行冲突与 SQL dump 不变断言；regression-backend.log |
| 规范 P1 非法计划事务；保存接缝 | 独立复验发现旧 validate_plan 捕获 ValueError 后仍提交非法计划；现在异常进入已有存储回滚分支。[None] 提交失败、连接无遗留事务、Run/事件不变，同连接后续合法保存成功 | red-rollback.log：原实现未抛出预期错误；green-backend-02.log、regression-backend.log |
| 规格 P2 更新提示；RS-18 | 规划/协调面板接收正常 initial_plan_generated/plan_replaced 的保存引用；状态事件即便携带引用、无保存引用的计划事件均不提示；真实保存只提示“有新成果，更新查看”，不自动 GET 或替换正文；点击后才读取对应来源 | red-browser.log：缺更新按钮；green-browser.log：3 项通过；regression-browser-02.log：6 项通过（含两个角色与 1024/1440 桌面） |

最终聚焦后端 43 项全部通过；前端 typecheck 通过；官方 baseline 的 11 个 SHA256
全部一致，见 baseline.json。新增浏览器负例等待断言曾用角色查询寻找模态背景滑块，
导致 2 项夹具失败；改为 DOM 查询后 6 项通过，原失败保留在
regression-browser-fixture-failure.log。未把失败覆写成成功证据。

实际命令：

```powershell
$env:UV_PROJECT_ENVIRONMENT='D:/project/工程化MathAgent/Challenge-Cup-2026/.venv'
uv run python scripts/run_unittest_report.py --expect-count 43 tests.test_role_stage_200 tests.test_conversation_workbench tests.test_reviewer_boundary_195 tests.test_star_product_planning tests.test_solver_harness_replan tests.test_solver_harness_persistence
# showcase/frontend/chat-frontend
npm.cmd run typecheck
npx.cmd --no-install playwright test tests/browser/role-stage-200.spec.ts tests/browser/conversation-workbench.spec.ts --grep 'desktop|mini coordination|1440px|1024px' --workers=1
```

本轮所有修改文件：showcase/role_stage_results.py、showcase/role_stage_api.py、
showcase/solver_harness/storage.py、tests/test_role_stage_200.py、
showcase/frontend/chat-frontend/src/components/ConversationWorkbench.vue、
showcase/frontend/chat-frontend/src/components/RoleStagePanel.vue、
showcase/frontend/chat-frontend/tests/browser/role-stage-200.spec.ts，以及本验收文档。
source.zip 为上述七个代码/测试文件在最终源码 SHA 的快照；source-manifest.json
记录源码 SHA、文件哈希和证据目录。产物仅留忽略目录，不提交日志或运行 raw。

复用既有 root .venv 与 node_modules（工作树 junction），未安装或修改依赖。
未访问 tests/test.md、未修改 root 已有工作、未跑整仓/真实模型/手机测试、未操作
GitHub/PR。以上为 fresh fixer 的修复与受影响差异复查，未冒称新一轮独立双轴审查。
完整阅读保位/重开恢复/失效同步仍留 #204/#205，不用本轮信号测试代替后续验收。
本地 integration 合并前已核对 tip 从 7e5d8ef 推进至 aeeefdc（已含 b9e37e0），
无其他源码分叉；合并 SHA 由最终交接给出。继续使用当前选择的同一模型，未指定覆盖，
具体型号及宿主继承结果无法独立核验。所有检查均秒级完成，无定时检查待交接。

## 实现与公共接口

正常计划保存事务追加state.role_stage_results，事件保存role_stage_source。
正文仅取step_id/title/objective/depends_on；题意正文未引用，因此无需冒认协调推导。
计划来源的内部生产者role=planner；controller复用同一已保存阶段安排。
后续发现与审查生产者可独立模块加入同一记录集合，查询先按生产者隔离。

GET /api/agent/jobs/<job_id>/role-results/<role>?source=<opaque>
每次查归属，直接读取保存状态，不走current_solver/persisted_solver及其reconciliation。
普通路由分类和after_request均已明确接线，report仍需reviewer。
默认按run/problem/spec/plan/attempt精确匹配；显式空或坏source不可用。
来源缺失、重复、损坏、正文或检查版本冲突、state跨Job绑定均不可用，不回填。
公开DTO见src/api/role-stage.schemas.ts，内部/接口见showcase/role_stage_results.py。
仅planner/controller有本票内容；无完整argument/report、原始步骤ID、调用身份产品标签。
公式不截断，敏感串用public_text整体抑制，目标通过既有安全Markdown/KaTeX渲染。

## 验收映射

| 合同 | 公共接缝与断言 | 证据 | 结果/边界 |
| --- | --- | --- | --- |
| RS-01 | 关键进展/完整星图同一plan正文、版本、有效性、check；迷你协调入口 | role-stage-200.spec.ts；panel.png | pass，本票计划范围 |
| RS-02 | 开面板不筛选；独立只看该角色才筛选；旧工作台1024/1440桌面断言已更新 | desktop-final-03.log | pass |
| RS-05、22 | 跨Job state、空/坏/重复引用、attempt不匹配、正文/check冲突不回退 | test_role_stage_200.py；backend-final-03.log | pass来源守卫；来源身份重写冲突仍有P2，未解除；历史与迟到组合留203/204 |
| RS-06 | 冻结Job和solver业务；重复读取calls/counters/budget/plan/results/events一致，无requests Session派发 | PlanReadTest；backend-final-03.log | pass；SQL dump为附加断言，AuthSession维护不作为业务合同 |
| RS-08、20 | 结构校验不代表完成；协调为安排；无题意冒认及第十节点 | 面板DOM、panel.png；API白名单 | pass计划范围；九角色等级留201/202/205 |
| RS-18 | 正常保存生成来源信号，status事件不改已存正文；运行状态与读取正文独立 | PlanSourceTest；面板独立props/content | 保存边界pass；新保存成果提示属本票未完成P2，交fresh fixer；阅读稳定留204 |
| RS-19 | 普通归属授权、未认证拒绝、不同归属404、报告仍403、敏感样本整体抑制 | PlanReadTest；reviewer边界回归 | pass |
| RS-21 | Enter/Space双入口、Tab面板操作、Escape/关闭后回触发点，可见焦点和标题 | role-stage-200.spec.ts | pass基础；触发点消失/全九角色异常留205 |

RS-03/04/07/09–17及其余跨角色组合属于201–205，未以本票结果替代。
未运行真实模型、真实工具、整仓长测、手机场景；不宣称数学能力提升。
独立双轴审查已由主控完成，固定7acb862，报告位于仓库外
C:/Users/CQX/.codex/tmp/role-stage-200-review-standards.md 和 role-stage-200-review-spec.md。
- P1保存步骤无校验导致共享事务遗留：56c6e0增加validate_plan后再创建来源；未独立重跑审查探针，不预记解除。
- P2旧记录plan_version被改写但保留source_ref仍可发布：未修，需复核完整来源身份绑定。
- P2 API直接读私有SQL绕过ADR-0013统一校验：未修，需存储层只读公共接缝。
- P2新保存成果提示缺失：未修，属于#200要求，交fresh fixer，不能推迟为#204。
最终33a79e7与审查7acb862不同；通过的40+4项不覆盖上述未解除缺陷，不构成整体验收。

## 红绿证据与命令

工作树artifacts/role-stage-200/为忽略目录，日志与截图不提交。
- red-save.log：缺role_stage_results；该初版夹具另有Windows清理错误，已修夹具。
- red-read-03.log：普通用户新路由被403，稳定失败；green-api.log 17通过。
- red-source-guards.log：空source回退当前，稳定失败；green-source-guards.log通过。
- red-browser.log：缺角色入口；red-math-02.log：缺KaTeX；green-math.log通过。
- backend-final-03.log：最终40项聚焦后端；desktop-final-03.log：最终4项桌面。
- typecheck-final.log；baseline.json：11个baseline文件SHA256全部一致。
- panel.png为打开面板的桌面图，含正文、公式、版本和检查范围；desktop.png为关闭后图。
- green-desktop-final.log原有2失败保留：旧夹具期待“历史回放”，实际当前为“求解进展”；修正测试后复验通过。

```powershell
$env:UV_PROJECT_ENVIRONMENT='D:/project/工程化MathAgent/Challenge-Cup-2026/.venv'
uv run python -m unittest tests.test_role_stage_200 tests.test_conversation_workbench tests.test_reviewer_boundary_195 tests.test_star_product_planning tests.test_solver_harness_replan tests.test_solver_harness_persistence
# frontend/chat-frontend目录
npm.cmd run typecheck
npx.cmd playwright test tests/browser/role-stage-200.spec.ts tests/browser/conversation-workbench.spec.ts --grep 'desktop|mini coordination|1440px|1024px' --workers=1
```

## 交接与限制

共享合同 C:/Users/CQX/.codex/tmp/role-stage-200-shared-contract.md。
未触碰tests/test.md；未搬运原工作区视觉或失败展示改动。
保存版本随ledger增长；本票不做裁剪历史或增加缓存策略。
已有缺来源任务准确不可用。面板为基础原生dialog，后续205扩展异常与九角色职责；204接阅读composable，203接历史与来源模块。
本票中其他角色节点暂不打开详情，已撤除节点隐式筛选；这是205尚未实现的范围。
无需监控交接：聚焦检查均为秒级结束，无长测试、定时检查或后台求解需转移。
