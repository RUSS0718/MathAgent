# #200 当前计划双入口工程验收

2026-11-18，Asia/Shanghai。起点9765244，专属feat/role-stage-plan-200。
已合入集成tip 7e5d8ef（合并提交7acb862）。未改tracker、未推送、未创建PR。
沿用会话当前模型，未指定或更换；无法独立证明宿主的具体型号继承结果。

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
