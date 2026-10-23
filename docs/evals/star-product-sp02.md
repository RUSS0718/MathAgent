# SP-02 STAR Job 纵切验收记录

日期：2026-10-23。工单：#58，父规格：#56。基点：251f620。证据类型为 scripted 与 fault_injection；本片真实 Intern 调用为0。

## 交付边界

现有认证、ChatSession、Job及Run入口增加可选 `solver_mode`。省略时为 `legacy`，保留原请求摘要与原有执行路径。显式启用服务 `uv run python -m showcase.flask_app --star-limited` 后，Workbench可选择 `star_limited`。配置注入支持 `SHOWCASE_STAR_ENABLED=True`、真实 `InternModelAdapter`及明确的`SHOWCASE_STAR_EVIDENCE_KIND`。

`star_limited`复用实际SolverHarness：Explore、原会话润色、新会话整题Verifier；所有模型经现有Adapter和S3预算/控制绑定。临时与真实存储均沿用Job的run_id和SQLite路径。Job/Run/SSE/报告/Evidence保存模式、缺失能力、Solver revision及同ID checkpoint投影。Solver commit后投影不含prompt或原始调用，workspace事务对稳定Solver event ID去重。数学状态仍在Solver表，checkpoint只是终态执行位置，尚不提供中途安全续算。

`star_reference`和`star_best_effort`始终在入队前拒绝，不能用配置布尔值绕过。隔离输出旁路、已接受步骤恢复、完整核心产品验收和最终文本审查绑定均未关闭。未知模式及未实现消融拒绝；固定预设不接受自定义开关，不能关闭整题审查。LLM ACCEPT只表示LLM整题审查，公开verification仍为unknown；required需要更强证据时为NEEDS_REVIEW。

## 可重复公共验收

`uv run python -m unittest tests.test_star_product_jobs`通过5项。测试使用真实InternChatClient和Adapter，仅替换HTTP传输。独立观察三次实际请求内容：Explore候选、同session润色、新session Verifier收到实际润色文本及原题。实际出站3次，原账本logical_calls和http_attempts均为3，provider usage为30 tokens。Job、Run、报告及Evidence回答一致；另开应用读取同库后，Solver版本和预算不变，出站仍3次。

REJECT与非法Verifier裁决分别走fault_injection：各实际3次HTTP，均失败而非将候选当答案，provider未知usage保留。完整模式缺前置、未知模式、关闭审查、自定义核心开关均在入队前拒绝。同幂等键更换模式返回409。该组反例能识别忽略模式、跳过审查、返回草稿和重放读取派发等旁路。

## 界面与检查

前端`npm ci --no-audit --no-fund`、`npm audit --audit-level=high`和`npm run check`通过：0 vulnerabilities，类型、13项单元测试及构建通过。Playwright真实Chromium在320/768/1024/1440四种宽度验证显式选择、原模式默认、完整选项禁用、实际提交solver_mode、STAR身份，全部4项通过。浏览器错误/警告0，Axe违规0，无横向溢出；截图实际目检320与1440。此处页面API使用合成展示数据，不当作Solver能力证据。Chrome DevTools MCP不可用，使用现有Playwright；未声称网络性能剖析。

原有live pipeline/control/budget相关25项通过；发现legacy live编排允许fake标记注入流水线，修复STAR dispatch glue后，campaign与live工具18项通过。曾并发启动offline和release（两者均跑完整套件），造成重复运行和等待，已终止本worktree所属冗余进程，改为顺序验证。最终完整门禁结果见下文，不用早期中断结果声称通过。

## 后续责任

SP-03补齐多角色/工具/并发/迟到结算及数学提交控制反例；SP-04之后扩展真实机制。SP-08验证接受步骤与checkpoint崩溃窗口及显式未知重试；SP-09修复实际输出隔离旁路；SP-10完成实际交付文本绑定；SP-13负责真实模型与独立发布验收。当前受限成功不代表完整STAR、数学正确率提升或这几票通过。

## 最终回归结果

主代理独立执行 uv run python scripts/check.py --offline：348 项测试通过（201.849 秒），repository_check=PASS；其中凭证无关发布门禁测试也通过。输出保留在 ignored artifacts/sp02-root-check.log。所改 Python 文件 Ruff、git diff --check 通过；官方冻结文件及 requirements.txt 差异为空。完整 STAR 前置缺口仍未关闭。
