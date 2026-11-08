# S05 与 F1/S07 工程退出验收

日期：2026-11-08（Asia/Shanghai）。集成分支：`mathagent-faithful`。

**S05、F1/S07 分别工程退出通过，均为 `engineering-preview`。** 本记录不声明数学能力提升。依据 [S05 合同](../engineering/faithful-s05-contract.md)、[S07 合同](../engineering/faithful-s07-contract-exit-20261108.md)、[#147](https://github.com/RUSS0718/MathAgent/issues/147) 与 [#144 阶段决议](https://github.com/RUSS0718/MathAgent/issues/144#issuecomment-6703147321)。

## 源码与交付身份

起点：`47428eb7263cf2cb3a452df3967f81ffd88a8510`。最终集成源码和成功门禁源码均为 **`932a234824ca88036061f189e8c2689ecd2d3ddb`**。之后的验收、合同和索引提交仅修改文档；最终交接 SHA 以该文档提交及交接回复为准，不冒称文档提交重新运行产品门禁。

主要集成提交：S05 `bf20c97`；S07 `7c27673`；真实公开投影及默认路径修复 `2edf0de`；来源与控制命令 `465e949`；图页面 `ed17e2e`；历史依赖与审查新鲜度 `51bdc73`；DTO 等级合同 `932a234`。提交尚未 push。

## F1/S07 行为与独立结论

- 复用既有 SolverHarness、SQLite 状态和事件 CAS。新 Run 可信配置显式启用 `proof_graph`，默认关闭、排除 CORE；旧 Run 不迁移、不热开图。官方 baseline 与评分预算不变。
- 区分命题、推导、证明尝试和来源；模型报告只产生候选。有效支持必须绑定可核验的已接受账本、调用、审查、claim、依赖及适用回执，保留原等级。
- 单推导前提为 AND，同命题独立支撑为 OR。撤销一条支持仍保留独立支持；最后支持消失才传播失效。失效尝试不因恢复重新接受。
- GraphBootstrap 保留未导入记录和受控原因，不捏造依赖或升级证据。普通新图变更的循环、悬空依赖、重复身份及历史依赖改写整次拒绝；图版本和来源规格绑定受校验。
- 完整快照追加历史。通用补丁不能写图或图策略，防止伪造合法版本历史和给旧 Run 热启用图。取消/deadline 在图派生前后检查。
- 模型反例候选不成为反驳。`proof_graph_commands.accept_counterexample` 通过持久化独立工具回执接受；冲突保留独立标记并阻断下游。`resolve_conflict` 要求冲突之后的新审查，保留 revision/CAS 和来源约束。
- 控制命令是显式入口，不自动派发模型冲突审查，不增加第二套求解循环。本文只验收受控入口，不声称默认 Job 会自主产生新冲突审查。

**F1/S07 工程结论：通过。** 17 项专属测试覆盖 AND/OR、独立回执、冲突、历史依赖变造拒绝、重启、快照、CAS、取消/deadline、Bootstrap 和旧 Run。两个实际公共 Job 测试覆盖真实图生产者、关闭开关、report、隐私及只读零调用。

## S05 行为与独立结论

- 复用持久事件、公开 projection、ChatWorkspace、AgentTimeline、RunReview。根义务为进度分母；展示根义务台账、真实角色活动、计划/尝试历史、请求重试、时间线和可折叠长产物。
- 公开图仅在真实生产者投影存在时显示。锚点绑定 Run、graph version 与快照内节点别名；按尝试显示 AND 前提和 OR 支撑，不含命题原文或证明私有内容。
- 丢失 POST 回包后复用相同 key/Job；SSE 断开、重复、持久游标重连、刷新和跨 Job 导航保留身份。只读查询、重连和刷新不新增求解调用。
- 浏览器使用真实本地受控 provider 经 SQLite 持久化的事件。终态重新读取事件，并断言持久 ID、可见 DOM ID、样本 ID 完全一致。集成图运行 **50/50 样本，nearest-rank 第 48 项，P95=818 ms**，满足 ≤2 秒。它不是 provider-live SLA。

**S05 工程结论：通过。** 非图 Python 5 项、原有 Chromium 产品回归 13 项通过；最终集成专属 Chromium 5 项通过，包含真实图、POST/SSE、历史、长产物、刷新和身份隔离。

## 验证结果与证据

原始运行产物均在集成工作树的忽略目录，不进入提交。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 最终六阶段门禁 | 6/6，`source_changed=false`，1479.297 秒 | `artifacts/final-gates/faithful-s05-s07-02/status.json`、`source-manifest.json` |
| 完整 unittest | 1496 项，0 failure、0 error、42 skip，1352.562 秒 | 同目录 `repository-check/tests.json`、`diagnostics.log`；skip 不计通过 |
| 快速与发布检查 | fast 通过；release 27 项通过；官方导入/JSON、Demo help/HTTP、baseline 边界通过 | `fast.log`、`release.log`、`offline.log` |
| 前端门禁 | npm ci/audit/check 通过，0 漏洞；类型、单元测试、构建通过 | `frontend-install.log`、`frontend-audit.log`、`frontend-check.log` |
| Faithful 相关回归 | 145 项通过；其后追加边界由专属与最终全仓门禁覆盖 | `artifacts/faithful-s05-s07-coordination/faithful-regression-02.log` |
| S07 最后聚焦 | 17 项通过 | `spec-fixes-04.log`；目录同上 |
| 实际公共图入口 | 2 项通过；启用与默认关闭、report、只读调用计数 | `public-integration-03.log`；目录同上 |
| 真实集成浏览器 | 5 项通过，30.5 秒；50/50，P95 818 ms | `artifacts/faithful-integrated-browser-01/` 的逐样本 JSON、截图；`browser-integrated-01.log` |
| 早期纵切证据 | Python 5、产品浏览器 13、review02 其余 4、history07 后续 1 通过 | `artifacts/faithful-line-evidence/`；早期 P95 505 ms 属于非图条件，不替代集成 818 ms |
| Ruff 与 diff | 修改文件检查通过 | 聚焦执行记录与差异检查 |

最终门禁主 PID 4288，开始于北京时间 18:50:29。临时 30 分钟检查任务及终态检查脚本已删除；无门禁或测试任务仍在运行。保留用户可手动运行的只读 `monitor.ps1`。

## 双轴审查与失败记录

Standards 发现的图模块 mock/缺真实生产者、通用补丁热开图或篡改历史问题均已修复并复查。Spec 发现的时延样本缺完整分母、多计划缺浏览器恢复、非法依赖未整次拒绝、账本等级或 claim 绑定不足、缺正式图控制入口问题均已修复。追加复查要求拒绝历史结果 ID 依赖变造及过期冲突审查，已补约束和反例测试；最终两轴没有未解除的退出阻塞。

首轮门禁 `faithful-s05-s07-01` 在 offline 失败：1496 项中 1 failure、0 error、42 skip，`source_changed=false`。唯一失败是 `test_star_readiness_late...test_late_usage_updates_original_attempt_after_terminal_archive_is_frozen` 返回 `evidence_mismatch`，而非期望 `unknown_transport`。未放宽断言、未据此修改产品逻辑；单独 3 项与后续 8 轮 24 项均通过，未稳定复现，根因未确认。第二轮同源码完整门禁通过。第一轮失败仍保留，不能解释为根因已修复。

早期浏览器失败涉及夹具缺 ProblemSpec、Vite base、旧题目标识、Meta 分支与重复文本定位；按具体失败修复并保留独立运行目录。历史夹具的 traceback/replan Run 可因 `work_unit_prerequisites_incomplete` 失败，浏览器明确核对该终态并验证历史恢复，不把它写成求解成功。

## 能力边界与后续前置

42 项 Docker/Reference 仍跳过。provider-live、完整真实隔离环境、容量/SLA、自然题规格/方法语义和数学收益均未验证；没有付费 provider 实验。浏览器实际图样本是单个受接受 Lemma；多前提/多支撑组合由持久化测试覆盖，不能声称其全部组合已有浏览器实测。

S05 退出解除 S06 的剩余工程前置；S07 退出解除 S08、S09 的工程前置。**S06 Composer、S08 路线/APRS、S09 Lean 及完整并发均未实现。** #146 保持开放，其余 live 或能力票不因此升级。

交接继续使用当前选择的同一模型，不主动切换。子代理调用未传模型覆盖参数；无法核实上一窗口具体型号或独立确认实际继承结果，不猜测型号。
