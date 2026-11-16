# 本地 Showcase 审阅入口

2026-11-17，#195 / #188。仅为单机展示权限边界；阶段最终验收见
[用户答疑记录](../evals/user-solving-188-20261116.md)，下文首轮失败保留为历史。

服务进程配置 `SHOWCASE_REVIEWER_SECRET` 为独立随机密钥（不写入仓库、URL 或日志）。缺少配置时拒绝兑换，包括 TESTING。浏览器先 GET `/api/check_auth` 建立 Cookie 并取得 csrf_token，再 POST `/api/reviewer/grant`，JSON `{ "secret": "由操作者安全输入的密钥" }`，请求头 `X-CSRF-Token` 使用该会话令牌。成功后 `/api/check_auth` 的 permissions 含 `reviewer.access`。密钥不能放入前端构建配置。

浏览器可直接打开 `/dashboard/reviewer`，输入密钥完成授权后进入设置页；
该公开页面只提供兑换表单，不提供技术数据。授权后可打开技术深链。
普通暂停与专用恢复使用既有 `/interventions/pause`、`/interventions/resume`
操作接口，干预详情仍需审阅授权。普通进度显式区分模拟与真实执行。

可信 CLI 需要读取技术数据时，另在客户端进程安全设置
`SHOWCASE_CLIENT_REVIEWER_SECRET`，值与目标服务的审阅密钥一致。
客户端建立会话并取得 CSRF 后显式兑换；不设置该变量时保持普通身份，
技术操作返回拒绝。实验内置服务与本地运行诊断各自对自有 app 兑换授权，
不为普通 HTTP 会话放宽权限，也不输出临时密钥。

授权只绑定该 AuthSession，SQLite 保存 grant；重启后仍有效。其他同 local-user 会话不继承；logout 撤销原会话及其审阅能力。修改配置密钥不会撤销既有授权；撤权使用原会话 logout。拒绝兑换不会清除已有授权。归属检查继续生效。

服务端按普通 URL 模板白名单放行，其余端点默认需要审阅授权，覆盖报告、Evidence、输出来源、候选、artifact、memory、intervention detail、system、campaign、debug 与 legacy Run。普通 Job、控制和事件 URL 沿用，JSON/SSE 按嵌套白名单投影。`GET /api/agent/jobs/<id>/answer` 唯一正文只读，响应 no-store；接入 #194 `presentation_api.get_final_answer`（合入 #194 后已移除独立开发 fallback）。GET 不调用生成器。

技术 SPA 组件仍须由前端按 permissions 阻止挂载；静态 JS 可下载不代表授权，后端所有技术数据请求独立受保护。`/dashboard/session/<id>` 普通历史入口保留；技术 dashboard 和 dashboard-assets 深链接受保护。

技术 HTTP 测试可显式调用 `tests.reviewer_support.reviewer_client(app, client)` 得到 `(client, csrf)`。助手配置仅该 app 的测试密钥并走真实授权 HTTP；只用于审阅场景，普通身份和拒绝用例不能全局升级。旧 `/report`、`/evidence`、`/outputs`、`/api/runs` 等技术场景已在集成修复中显式迁移，普通负例仍保留。以下为首轮历史记录，不代表最终源码残留：已抽样 `tests.test_flask_showcase` 12项有2失败、2错误，涉及 polynomial、legacy Run、capabilities 及 report；证据 `artifacts/issue188/reviewer-195/legacy-http-regression.json` / `.log`。

新增6项 HTTP合同通过；`tests.test_workspace_jobs` 3项通过。首次授权红灯、投影红灯和 answer helper 未集成红灯已在执行输出观察；answer 红灯留存 `artifacts/reviewer-195/red-answer.json` / `.log`。绿色证据见 `final-focused.json` / `.log` 及 `workspace-regression.json` / `.log`。没有运行全仓、长测试、浏览器或真实 provider 测试，亦不声明公网多租户安全或数学能力提升。

合入集成分支 e8db522（本地 merge 6796e52）后，使用实际 #194 helper 验证：新增7项 + 工作区3项通过。额外组合输出12项共22项中有2失败，都是新输出测试尚未兑换 reviewer（预期409/200，实际403）：`OutputRulesTest.test_new_output_post_cannot_generate_template_before_worker` 和 `TerminalOutputContractTest.test_teach_model_once_and_reads_never_dispatch`。这两项应由集成测试迁移者在技术读取场景显式用 reviewer_support，普通 `/answer` 读取仍维持普通身份。证据 `artifacts/reviewer-195/integrated-22.json` / `.log`；未修改其他负责人输出测试。只读 pending 不生成正文，实际 fake worker 完成后普通 answer 返回 ready 且刷新一致。
