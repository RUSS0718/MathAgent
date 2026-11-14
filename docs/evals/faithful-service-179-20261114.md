# #179 授权经验记忆与撤销验收

日期：2026-11-15（Asia/Shanghai）；状态：达到用户授权调整后的开发接线退出条件，真实能力边界按下文保留。[任务合同](../engineering/faithful-service-179-contract.md)；父规格 #168，当前票 #179。

## 源码与边界

接续起点 fc50ec3ac573e5699f8b678ab4f602e47546c3b2。实施期间共享 checkout 被其他任务推进至 f87266522d7581a8b8db447ff77eb1a17ae6de98，包含 #184 等独立变更。本票原提交 56c9792 保留在该分支，随后仅将本票 cherry-pick 回 faithful-autonomous-population，成为 a82b34563353631faf8693e6d0c4a2c7cd584723，父提交即接续起点。双轴最终复查及门禁针对 a82b345，不含 #184。

复用现有会话同意、观察 Store、显式导入和来源祖先链。普通 intake 形成可信规格后，每次模型请求重新读取当前同意与同域观察；过滤旧 advisory、记忆相关角色历史及其派生摘要，再重建上下文。原审计与有效数学账本保留，已发出的请求不能撤回。并发 worker 继承记忆能力开关。经验仍为 advisory_only，不授予数学证明等级。

模型响应可报告来源受限、有界理由的 adopt/reject；未报告记 not_reported，注入不等于采用。公共 memory_usage 投影和前端展示已完成，受控公共检查及浏览器验证通过。

## 失败先行与审查

证据目录 artifacts/issue-179/。red-request-fence.log 保留停用、清理及持久副本篡改三项失败；red-ancestor-consent.log 保留祖先关闭仍可注入；red-decisions.log 保留缺失决策协议；red-worker-inheritance.log 保留并发开关继承失败。最终 public-projection-summary.json 记录37项、0 failure/error/skip。

前端原有入口补齐显式导入、清理和效果说明；首轮受控浏览器4项、单测7项及类型检查通过，原 red-browser.log 保留。该结果不等于真实 provider 或数学收益。实际查看 memory-320.png，窄屏无横向溢出，管理入口及关闭效果说明可见。

Standards 与 Spec 分别审查。Spec 指出并发 worker 未继承开关和决策只存内部的两项 P1，均已修复。reviews/standards-recheck.md 与 spec-recheck.md 对最终 a82b345 复查无剩余阻塞；原报告保留。

## 真实验收

`live01` 通过普通 Chromium 和公共 Job/API 提交 `计算 2+3。`，得到答案 `2+3=5`；provider 请求成功但用量缺失，Job 因 `formal_requirement_unmet` 失败。该 Run 仍自动写入同所有者、同会话、domain=`integers` 的观察，outcome 保守记为 `unknown`，Run/Job/Attempt、来源和失败均保留。

`live02` 在提交前因观察器要求“恰有一个会话”而停止，未发模型请求；该失败保留。`live03` 明确选择恢复的同所有者会话，普通 Chromium 提交 `Compute 3+4 using ordinary arithmetic. No machine verification is requested.`。页面仍在旧 Job 上，因此通过旧 Job 的 `/revisions` 创建关联新 Job `run_9ba09d5598ac821d090a71ba783a23e8`，共5次模型调用（含 intake 修复），成功交付 `3+4=7`。三个后续调用带有首轮记录 `8acbd5a10ec54722a11123e7014b1271`，决策均为 `not_reported`；观察 outcome 仍因 provider 用量缺失记为 `unknown`。第三轮观察器等待错误的提交端点，30秒后超时，未保存新 Job 的实际公共 GET 或页面终态；原观察器失败保留，不重发、不改写原判。

事后以 SQLite 只读连接核对 Job 和状态，并调用现有 `project_run_memory` 导出有限公共投影。`acceptance-reconciliation.json` 及 `live03/run_9ba09d5598ac821d090a71ba783a23e8-offline-memory.json` 保存状态 revision=650、来源、`not_reported` 和配置摘要。数据库前后 SHA256 相同、零新增模型请求；这是离线证据核对，不是实际 HTTP GET 或浏览器展示验收。真实管理操作仅执行过启用；关闭、清理、跨会话导入均为 not_run。

真实运行使用原根预算（48/48/8/262144/1100），没有增加成功率、性能或大样本门槛。live01 为4次模型调用、live03 为5次；两次尝试没有得到自然 adopt/reject，按接续合同停止追加碰运气调用，调整本票为开发接线退出并将缺口留 #183。配置、Job、数据库投影和脱敏截图位于 `artifacts/issue-179/live01/` 与 `live03/`；配置 SHA256、原观察器状态及事后核对见 acceptance-reconciliation.json。凭证、完整 prompt 和 raw response 未进入提交记录。具体助手型号及新 session 继承结果无法核验；provider `intern-s2` 不是助手型号。

## 验收映射

| 合同 | 公共入口与证据 | 当前结果 |
| --- | --- | --- |
| C1 | 既有无同意公共求解回归 | 聚焦通过；真实运行均显式授权后进行 |
| C2 | 普通真实输入、自动捕获、同域来源、决策状态 | 工程通过；真实捕获与来源注入可追踪，模型决策为 `not_reported`；新 Job 公共投影仅事后离线导出 |
| C3 | 同所有者显式导入、祖先控制反例 | 聚焦与来源祖先反例通过；真实跨会话导入 not_run |
| C4 | 公共关闭后显式新身份 resume，旧unknown保留、deadline不变、后续请求不带旧经验 | 受控公共反例通过；独立进程真实重启 not_run |
| C5 | 现有管理 API、受控浏览器启用/关闭/导入/清理 | 前端4/4、单测9/9；真实仅启用已执行，关闭/清理/跨会话导入及真实终态来源 UI 闭环 not_run |
| C6 | 最终双轴审查、冻结门禁 | pass：gate-01六阶段、2095项、0 failure/error、49 skip、source_changed=false |

## 运行与交接

门禁入口由 `artifacts/issue-179/gate-control/worker.ps1` 固定，执行快速检查、完整离线检查、发布检查、前端安装、前端检查及依赖审计，命令和退出码保存在各阶段日志。聚焦命令及前端红绿记录保留在本票 artifacts；事后核对命令为 `uv run python -c "import runpy; runpy.run_path('artifacts/issue-179/reconcile.py')"`。仅文档修订依工程门禁检查差异和链接，不重复未变产品套件。

仍未实证的自然 adopt/reject、真实关闭/清理/跨会话导入、独立进程重启后的真实撤销与继续，以及完整真实管理和来源 UI 闭环均交给 #183。受控用例通过不代替这些能力。#168 与 #183 继续开放。

真实后台实例、服务和临时 ScheduledTask 已退出并清理；没有本票监控或代理留守。最终源码为 `a82b34563353631faf8693e6d0c4a2c7cd584723`，其父提交为交接起点 `fc50ec3ac573e5699f8b678ab4f602e47546c3b2`。实现聚焦37项通过，前端单测9/9、浏览器4/4，最终门禁六阶段通过。以上证明本票工程接线与有限真实闭环，不证明数学能力提升或 #168 完整服务。

tests/test.md 不读取、不修改、不提交、不删除；继续使用当前模型和思考设置，不覆盖具体型号。下一票按实时依赖选择 #180。
