# 本地 Showcase 审阅入口

2026-11-16，#195 / #188。仅为单机展示权限边界。

服务进程配置 `SHOWCASE_REVIEWER_SECRET` 为独立随机密钥（不写入仓库、URL 或日志）。缺少配置时拒绝兑换，包括 TESTING。浏览器先 GET `/api/check_auth` 建立 Cookie 并取得 csrf_token，再 POST `/api/reviewer/grant`，JSON `{ "secret": "由操作者安全输入的密钥" }`，请求头 `X-CSRF-Token` 使用该会话令牌。成功后 `/api/check_auth` 的 permissions 含 `reviewer.access`。密钥不能放入前端构建配置。

授权只绑定该 AuthSession，SQLite 保存 grant；重启后仍有效。其他同 local-user 会话不继承；logout 撤销原会话及其审阅能力。修改配置密钥不会撤销既有授权；撤权使用原会话 logout。拒绝兑换不会清除已有授权。归属检查继续生效。

服务端按普通 URL 模板白名单放行，其余端点默认需要审阅授权，覆盖报告、Evidence、输出来源、候选、artifact、memory、intervention detail、system、campaign、debug 与 legacy Run。普通 Job、控制和事件 URL 沿用，JSON/SSE 按嵌套白名单投影。`GET /api/agent/jobs/<id>/answer` 唯一正文只读，响应 no-store；接入 #194 `presentation_api.get_final_answer`，独立开发期保留窄 legacy fallback。GET 不调用生成器。

技术 SPA 组件仍须由前端按 permissions 阻止挂载；静态 JS 可下载不代表授权，后端所有技术数据请求独立受保护。`/dashboard/session/<id>` 普通历史入口保留；技术 dashboard 和 dashboard-assets 深链接受保护。

技术 HTTP 测试可显式调用 `tests.reviewer_support.reviewer_client(app, client)` 得到 `(client, csrf)`。助手配置仅该 app 的测试密钥并走真实授权 HTTP；只用于审阅场景，普通身份和拒绝用例不能全局升级。旧 `/report`、`/evidence`、`/outputs`、`/api/runs` 等测试应按场景迁移。已抽样 `tests.test_flask_showcase` 12项：2失败、2错误，其余通过；分别涉及 polynomial 技术端点、legacy Run 创建、旧 capabilities 字段及 report 访问。证据 `artifacts/reviewer-195/legacy-http-regression.json` / `.log`。没有批量更改旧断言。

新增6项 HTTP合同通过；`tests.test_workspace_jobs` 3项通过。首次授权红灯、投影红灯和 answer helper 未集成红灯已在执行输出观察；answer 红灯留存 `artifacts/reviewer-195/red-answer.json` / `.log`。绿色证据见 `final-focused.json` / `.log` 及 `workspace-regression.json` / `.log`。没有运行全仓、长测试、浏览器或真实 provider 测试，亦不声明公网多租户安全或数学能力提升。
