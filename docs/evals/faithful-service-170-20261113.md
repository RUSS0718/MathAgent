# #170 多步串行闭环验收（2026-11-13）

范围为 #168 的 A2/C1 子票 #170，实现起点 `e39eff306d852b40d1f50c326eaa0a1091e08ddf`。本票已达到工程退出；#168 完整服务及独立数学效果不能由本票推断。

当前截面（2026-11-13 14:24，最终门禁完成）：用户确认按简单串行案例收敛验收范围。真实浏览器普通输入已完成三个串行工作块、三次真实 Python、独立整题核验与同答案绑定，重开/刷新无新调用或 POST；下表逐项映射真实与受控证据。gate-02 的单项旧测试预期已修正，gate-03 最终门禁 6/6 通过、源码无漂移，达到 #170 退出条件。运行产品源码仍为起点 HEAD 加冻结 manifest-14；后续新增 CP05 测试修正及本文、索引更新，门禁冻结清单为 manifest-17（32 个文件）。先前 live-28 启动曾被自动审批拒绝且未创建 Job；用户确认继续后成功启动，拒绝不算 provider 失败。Git 交付身份和 Issue 关闭状态以 [#170 完成评论](https://github.com/RUSS0718/MathAgent/issues/170)记录的提交 SHA 为准；不启动后续子票。

合同见 [入口合同](../engineering/faithful-service-entry-contract.md)，运行证据保存于被忽略的 `artifacts/issue-170-work/`。GitHub 实时依赖核验确认唯一前置 #169 已关闭；领取评论为 `6831561266`。

| 合同 | 公共入口及断言 | 证据 | 结果 |
| --- | --- | --- | --- |
| A2-1 | 浏览器普通输入 → Job → Core 计划/工作块/串行路线 → Registry | `live-28-step-scope/acceptance.json`、`receipt-audit.json`：plan v1、3 个 ACCEPTED 工作块、1 路线、3 次实际 Python | pass（真实简单题） |
| A2-2 | ContextPack、依赖及图影响推进；失效/重复/停滞与资源守卫生效 | live-28 的 18 个 ContextPack、graph v9、S→T 依赖；`step-scope-final.json` 35 项含 S03 依赖阻断；`conjecture-route-regression.json` 38 项及原图/进展反例；live-27 实际重复前沿停止 | pass（真实与受控分别记录） |
| A2-3 | 普通会话和详情可读目标、状态、版本、图及真实工具结果 | live-28 的 `reopened.png`、`answer-visible.png`、`read-only-ui.json`、`details-ui.json`、`tools-visible.png`；详情显示 graph v9、3/3 根义务、路线、工具闭环 | pass |
| A2-4 | 候选拒绝后纠正；耗尽无新增派发；完整答案独立绑定 | `test_rejected_candidate_is_supplied_to_correction_after_real_registry_work`、`test_exhaustion_publishes_real_goals_partial_work_and_rejected_candidate` 等公共受控检查；live-28 为 accepted/same_artifact，T 的预期不符后独立复算 | pass（拒绝/耗尽为受控） |
| A2-5 | 模型/工具、答案/Evidence、刷新恢复完整；故障证据分开 | live-28 的 `job.json`、`report.json`、`evidence.json`、`system.json`、`summary.json` 及独立参考；live-01–27 失败保留，不改写旧 Run | pass |

早期验收题为从 `(0,0)` 到 `(12,12)`、只向右或向上、满足 `y<=x` 且避开 `(4,3)`、`(7,5)`、`(9,8)` 的格点路径计数。本地独立动态规划与反射法扣除交叉核对为 `68507`，该题未取得真实串行成功。最终使用依赖明确的 S→T 数值题，参考结果不注入模型；仅验证工程闭环，不构成准确率或效率评测。

## 最终真实串行证据（live-28）

普通输入要求先规划，再分别实际运行 Python 计算 S=1²+…+100²，以及 T=1+…+S，最后输出两整数。Run `run_e15b36f035378d6adabbf3e0f4a384f7`，持久会话 `session_8be53078caa0fffa35e2238a077599fc`。Planner 自主生成计算 S、使用 S 计算 T、输出三工作块；三者均 ACCEPTED/valid=true，根义务 3/3。共 18 次模型调用，17 completed、1 Explore 的已知 schema 失败经原有有界修复完成；没有 unknown 自动重试。保留原根预算、deadline、checkpoint 轮数及严格协议，不代填或改写计划。

三次 Python 均 executed=true、exit_code=0、cleanup_verified=true，分别输出 338350、57240530425、57240530425。第二次模型预期值不符，comparison_status=mismatched，不计已验证断言；核验器第三次独立复算回执为 not_compared。有限计算只支持对应数值目标，最终答案为 S=338350、T=57240530425，与事前独立公式和直接求和参考一致。whole_review=accepted、binding=same_artifact；未形式化验证，不声称子集/格点复杂题或数学能力提升。

`acceptance.json` 的 11 项检查全部为 true，包括源码冻结（31 个文件零变化）、ContextPack、图、真实工具、答案/Evidence 绑定与恢复。`summary.json` 为 1 次普通提交、刷新 0 POST、refresh_no_calls=true、errors=[]。额外只读重开 `read-only-ui.json` 与详情 `details-ui.json` 均为 0 POST、same_attempts=true、errors=[]；详情实际显示版本化证明图、路线、义务台账及含真实数字输出的工具结果。第一次补截图脚本误选隐藏元数据超时，只重跑只读读取并限定报告区域，没有新增求解；不将加载态截图当答案证据。

冻结源码为 HEAD `e39eff306d852b40d1f50c326eaa0a1091e08ddf` 加 `resume-source-manifest-14.json` 的未提交切片；该 manifest 与 Run 内 source-manifest 相同，SHA-256 为 `e71d649e80dd7aa01a4ac893ab8437a5f2211d01bb6eb0f4ad7dc9085a745d2d`。`verify-serial-numeric.py` 是生成原成功记录时的历史命令，因会写入 acceptance.json，不用于事后复查。安全复查使用 `uv run python artifacts/issue-170-work/recheck-serial-numeric.py artifacts/issue-170-work/live-28-step-scope`，只输出到终端、不改旧产物；分别报告原验收结果、当前产品源码匹配、索引及本文的允许文档变化。后续文档变化与原运行 manifest 区分，不重写冻结身份或原始 acceptance.json。

## 最终工程门禁与测试预期修正

`gate-02` 的 fast 通过，offline 实际执行 2007 项，1 failure、0 error、49 skip，`source_changed=false`，耗时 1701.719 秒；后续四阶段未运行，不计成功。唯一失败为原 CP05 空 Planner YIELD 用例预期只有 Explore、Planner 两次调用，未包含本票接通的已知协议错误单次格式修复。`cp05-repair-red.json` 单项稳定复现该调用次数差异。

只修改 `tests/test_cp05_public_job.py` 的该用例：提供两次同样无效的空 gaps 响应，明确断言 Explore/Planner/Planner 三次实际调用、`:repair-1` 身份、同一 checkpoint round、格式修复上下文及最终 `protocol_failure_unrepaired`，验证一次修复耗尽后停止。未改变产品、严格解析、调用预算或停止规则。`cp05-repair-green.json` 的 20 项聚焦全部通过，零 failure/error/skip；Standards 复查见 `standards-cp05-repair-final.md`，Spec 复查见 `spec-cp05-repair-final.md`。49 项 skip 未执行，ID 与原因保存在 gate-02 的 `repository-check/diagnostics.log`，不计通过。

本次测试文件未在 live-28 的 31 文件清单中；新增后以 `resume-source-manifest-17.json` 冻结 32 个变更文件并运行 `gate-03`，保留原实时成功的 manifest-14 和 acceptance.json，不覆盖历史身份。产品及原有测试字节仍与 live-28 相同；无需新增模型运行。门禁运行期间不改源码、测试、文档或 Git 暂存状态，结束后纯文档交接按工程门禁记录源身份。

`gate-03` 于 2026-11-13 13:54–14:24（+08:00）执行，耗时 1834.172 秒，六阶段全部 exit 0：

| 阶段 | 结果与边界 |
| --- | --- |
| fast | 官方 baseline 11/11 字节一致、导入及公共合同通过 |
| offline | 2007 项，1958 通过、0 failure、0 error、49 skip；expectedFailures/unexpectedSuccesses 均为 0 |
| release | 27 项通过、发布检查通过 |
| frontend-install | `npm ci --no-audit --no-fund` 通过 |
| frontend-audit | `npm audit --audit-level=high` 通过，0 vulnerabilities |
| frontend-check | 依赖合同、类型检查、63 项前端单测及构建通过；构建仍有大于 500 kB 的 chunk 提示，不构成性能验收 |

49 项 skip 的唯一 ID 和原因保留在 `gate-03/repository-check/diagnostics.log`：7 项未提供固定 Lean 环境，40 项未显式提供各测试要求的精确 Docker 镜像，2 项未启用 Docker readiness integration。均未执行、不计通过；live-28 的三次真实 Python 是独立专项证据，不代表这些隔离、Reference 或 Lean 测试通过。原 gate-02 失败记录保留。

门禁起点仍为上述 HEAD，`gate-03/source-manifest.json` 的 before/after source_hash 相同，为 `2d498f497614fd36621641f9e4cb519bcf4d69690a4f2a2b684000e8042651d0`，`source_changed=false`；变更清单 manifest-17 的 SHA-256 为 `b5b800205b8701723e4838285ed808946373aa447755063de20e738210ba4d3b`。门禁完成后仅更新本文及索引，检查文档差异与相对链接，产品、测试、依赖及配置不变。最终交接提交 SHA 在 #170 完成评论记录，和冻结门禁身份分别保留。临时定时检查 `MathAgent-170-active` 已移除，无新模型运行。

## 失败保留及审查

- `run_cdf71e8931bbbdeea0977490cea44f16`：3 次实际请求，Planner JSON 序列化失败。普通服务 checkpoint 路径缺少原有的一次协议修复，已补公共反例后接通；工具 0，不能当作工具验收。证据 `live-01-failed/`。
- 浏览器驱动在服务监听前启动的一次连接失败未提交 Job、未调用模型，单独保存在 `live-02-startup-failed/`；驱动补充只读健康等待。
- `run_78bd5db9c25b4056c2a1a95a5ba2e600`：Explore 首次与一次修复均为无效 JSON，3 次实际请求后正常停止，工具 0。证据 `live-03-protocol-failed/`。
- `run_bb2637946d264759bd3e7079630a7129`：4 次实际请求。Planner 首次有效 JSON 缺少必填 `checkpoint.status`，一次修复返回无效 JSON；保持严格解析并终止。不是未知远端结果。证据 `live-04-schema-failed/` 及 `protocol-diagnosis.md`。诊断发现 schema 错误修复缺少失败响应与字段信息，后续修复及真实复验另记。

上述真实失败均未执行工具，没有自动重提旧 Run。usage 缺失保持 `null`，本地预留计量不视为提供方实际用量。后续新任务本地配置 `service.json` 显式设定 2097152 token 上限，其他调用、工具与时间上限沿用示例；旧 Run 预算和 deadline 保持原值。

Standards 与 Spec 以起点差异独立审查。初审发现公开摘要敏感值残留、正常 NOT_FOUND 搜索阻断串行续行、部分成果依赖资格三项 P2；复查进一步纠正可选步骤跳过、历史猜想和授权救援的假阴性。逐项红绿记录在 `fix-*`、`recheck-*` 与 `rescue-*`。最终结论以各审查报告及本票最终门禁记录为准，不以测试数量代替真实闭环。

## 实际工具成功与恢复

普通浏览器提交英文子集计数题：从 `{1,...,20}` 选六个数，其和被七整除；要求递推依据、Python 实算和独立核对。Run `run_b51f536a20335a6c8778ae81b22e2667` 返回 `5538`，与本地独立 DP 和枚举交叉核对相符。6 次真实模型请求，1 次 `python_math` 实际执行，固定镜像 `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d`，回执 `executed=true`、`exit_code=0`、`cleanup_verified=true`，代码及输出引用可追踪。

整题检查为 `accepted`、`same_artifact`，未形式化验证。此题在 Explore 完成：plan_version=0、steps=0、routes=0，不能声称串行路线已执行。证据 `live-06-subsets-success/`；重新打开持久会话的 `subsets-read-summary.json` 为 `same_attempts=true`、`posts=0`、`errors=[]`，截图 `subsets-answer-final.png` 显示原答案和等级。早期驱动刷新截图只拍到加载状态，不能当作页面答案证据；后续只读重开补证，没有新增求解。

## 后续真实阻塞与最小修复

- `live-05-intake-failed/`：Run `run_a7d1807a9bbb76307674019859d6bd7f` 首次 intake 把 `directions` 拼成 `directionions`，严格拒绝；1 次请求，工具 0。
- `live-07-grid-failed/`：Run `run_f4239d9d93ace7714b74172a0749ec29` 两次 YIELD 后到原有 checkpoint 轮数上限，5 次请求，无合法计划。发现请求未说明 FINAL 是可交付执行计划而非数学已经完成，补充职责及原有剩余轮数信息，不增加上限。
- `live-08-workunits-failed/`：Run `run_0b8dcedc3231bda508c135af5d34b71c` 3 次请求，FINAL 计划映射产生同一步自依赖；checkpoint 路径缺少普通规划已有的绑定校验反馈，前移既有绑定校验并在原有剩余轮数内反馈错误。
- `live-09-plan-failed/`：Run `run_9c3a13e95aec915dc0da3574d1dfe2ed` 4 次请求，收到反馈后仍有自依赖/向前依赖，保持拒绝。规格本身无环，`workunit2-diagnosis.md` 说明合法绑定结构存在；未自动代填计划。
- `live-10-grid-failed/`：Run `run_db687e312ee26447ac5e382951ac9109` 6 次请求，Planner 有界协议修复失败，保持终止。
- `live-11-subsets-failed/`：Run `run_259326da7e7c41450aff02ee40e2e401` 5 次请求，计划重复归属产生 S4 自依赖。`planner-context-diagnosis.md` 重建两个实际出站 payload，hash 与记录匹配，确认完整规格及反馈到达；排除 ContextPack 丢字段。进一步消除单一/多重归属的指引矛盾，并让现有绑定异常指出具体 WorkUnit 和非法前置归属，不改变合法规则。
- `live-12-subsets-failed/`：最终源码上的 Run `run_746254ded30aac43ef320de4bb663ee0` 在 Explore 首次及一次修复仍为角色 schema 失败，3 次请求，无工具，无 Planner/串行成功。

上述失败都是独立的新任务验收，不是自动重发 unknown；unknown 零自动重试边界保持。反复运行未取得真实串行证据，停止进一步盲目派发。公开模型文档未确认支持 JSON Schema 强制输出，未添加未受支持的提供方参数或降低解析/绑定标准。

## 历史退出截面与继续入口（03:48，已由顶部当前截面更新）

**#170 尚未验收完成，保持开放，不创建下一票 session。** 当前 HEAD 仍为起点 `e39eff306d852b40d1f50c326eaa0a1091e08ddf`；本轮实现、测试与本文是未提交工作，不等于交付，未提交或推送代码。未读取、修改、提交或删除 `tests/test.md`，官方 baseline 未改变。

各增量双轴审查经修复后为 0 剩余阻塞，最后阅读 `standards-owner-final.md` 与 `spec-owner-final.md`，早先通过范围由对应 `*-final.md` 保留。审查不代替真实执行。最后仅修正两处测试导入排序；文件实际 SHA 保存在 `implementer-files.json`。最终聚焦结果见 `final-focused.json`；Ruff、diff 格式和快速门禁通过。

完整门禁 `gate-01` 在冻结源码上启动，fast 通过后进入 offline；2026-11-13 03:11:11 +08:00 因确认的 checkpoint 职责合同缺口由所有者中止，相关进程已退出，`owner-aborted.json` 为权威中止说明。其 `status.json` 可能仍显示 running，不能视为活动进程或成功；未取得最终完整门禁。后续有代码修改，不能复用该门禁，真实串行验收成功并重新冻结后须使用新 run ID。

真实运行与门禁的临时 30 分钟检查均已移除，无模型任务或长测试继续运行。本地 8090 服务保留供读取历史；launcher PID 32320，创建时间 2026-11-13 03:48:55 +08:00，数据目录 `artifacts/issue-168-work/live-data`，先核对 PID 和创建时间再操作。

继续在同一目录和 `feat/faithful-autonomous-service` 工作，不建 worktree、不重启旧 unknown、不领取后续票；先核对未提交差异、manifest 与本记录，解决真实 Planner→合法工作块→串行步骤的剩余阻塞后，补真实工具/答案/Evidence/恢复与最终门禁，再提交推送及关闭 #170。继续当前选择的同一模型；具体型号无法可靠确认，不猜测。

## 失败诊断后接续（2026-11-13）

用户授权按诊断顺序完成 #170。先保留公共接口红例，再收敛实际角色指令：Intake 不把工作流程当数学根义务，Planner 接收当前规格派生的目标依赖表及明确标记的示例，已知目标 ID 在 schema 中约束。没有代填、重排或删除模型计划。Intake 接入原有单次协议修复；Explore 补传原失败响应，非流式完整失败文本沿内部审计传递。预算、deadline、unknown 和严格解析边界不变。

`handoff-red.json` 复现六项缺口。`handoff-intern-green.json` 20 项及 `intake-public-final.json` 28 项通过。`resume-focused.json` 的 55 项中 54 项通过、一项检查原 checkpoint 提示标识失败；恢复该标识后包含该用例的 20 项通过。双轴复查指出 Intake 在失败落盘和修复失败落盘后的崩溃窗口；`intake-crash-red.json` 保留反例，修复后的 `intake-crash-green.json` 5 项通过，覆盖失败记录、修复预留、完成响应和失败修复恢复，不重复请求或计费。`standards-resume-final.md`、`spec-resume-final.md` 均无剩余阻塞。快速门禁、Ruff、diff 检查通过。

真实浏览器 `live-13-resume/`：Run `run_337f81de996997a912b16d172f94b1de`，4 次调用；Intake、Explore、Planner 均完成，第一次真实形成合法 plan_version=1、6 个 WorkUnit、1 条串行路线。首个 Reasoner 返回 `YIELD` 且 gaps=[]，提供方 schema 接受、checkpoint 解析器拒绝，以 `invalid_reasoner_checkpoint` 停止；工具 0，没有整题答案。失败源码及配置保存在目录内。浏览器驱动在失败后尝试等待编辑器超时，Job/Evidence 已保存；不把该截图当恢复成功。

此运行揭示 Reasoner schema 与已有解析规则不一致。`reasoner-yield-red.json` 在普通公共 Job、实际角色 port 和服务 checkpoint 配置下复现；schema 对齐现有状态/gaps、版本与非空字段规则，并在实际请求中约束当前 objective，不降低解析要求。Reasoner 说明当前步骤与后续步骤边界，并接收原有两轮上限及剩余轮数。`reasoner-yield-green-02.json` 验证一次修复后执行两个串行步骤及整题绑定；`checkpoint-public-final.json` 22 项通过，含状态/gaps 合同一致性。真实串行闭环仍待下一次验证，未以受控结果关闭 #170。

`live-14-reasoner/`：Run `run_2783d2063765b0e538f2033c192951f2`，5 次调用，Explore 的首次 schema 失败经一次修复完成；Planner 再次形成合法 6 工作块、1 路线。Reasoner 的非空 gaps/YIELD 本身有效，但完整调度响应多出运行时 `usage`。`calls._consume` 在流式结果经过提供方 schema 校验后附加计量，原 checkpoint parser 却把它作为模型额外字段拒绝；因此继续以 `invalid_reasoner_checkpoint` 停止，工具 0。此窗口同样存在于 live-13，不能把 live-13 的终止仅归于 gaps。此前公共反例采用非流式，漏掉该集成差异。

解析器现在仅分离这项内部计量，再严格校验 checkpoint payload；提供方 schema 仍拒绝模型输出的顶层 usage 和任意额外字段。新流式公共反例显式配置 loopback 的受控 stream-first profiles，覆盖实际四层 system 消息和动态目标 schema。早期 `reasoner-stream-red.json`、`reasoner-stream-green.json`、`reasoner-stream-green-02.json` 因测试 transport profile 不匹配在派发前停止，不是解析问题的有效红绿证据。`reasoner-stream-parser-red.json` 使用精确 HEAD 旧 parser 和纠正后的流式 fixture 失败；新 parser 的同一路线在 `reasoner-stream-green-03.json` 通过。失败、源码、配置及补证保持独立，不覆盖原 Run。

`checkpoint-stream-final.json` 23 项通过，包含真实 port 的流式公共 Job、一次协议修复、两串行步骤及整题检查；双轴报告 `standards-stream-resume-final.md`、`spec-stream-resume-final.md` 无剩余问题。`live-15-stream/` 的新 Run `run_31e16e16fecd0bcba004328c6e354300` 在 Intake/Explore 完成后，Planner 两轮返回相同无效计划，以 `invalid_problem_spec_work_units` 结束，4 次请求、工具 0。完整规格中 R3 要求独立枚举，G3 重复描述执行该枚举却声明依赖 R3；同一步 S4 同时归属两者产生自依赖。规格还把普通计数中的递推正确性标成 extremum_bound；这些是生成规格的语义问题，不能仅从 DAG 无环推断规格合适。

后续只补 Intake 的义务类型和辅助目标去重指引，不自动重写规格；Planner 在原有剩余轮数内收到结构化 `binding_errors`，明确 objective_id、prerequisite_id、owner_step_id 及 self/forward 关系。保留原 Plan 与异常，不代填或改排计划。`objective-feedback-red.json` 两项失败，`objective-feedback-green.json` 25 项通过；对 live-15 原始计划只读重放得到 `S4/G3 requires R3 owned by S4`。尚不据此声称真实 Planner 已能纠正。

`live-16-objectives/`：Run `run_d56bba5a5791f7eed24783d7e2b13360`，7 次模型调用；Explore、Planner 各经一次有界协议修复后形成合法 6 工作块、1 路线。首个 Reasoner 的 YIELD 经 Verifier ACCEPT，产生一条 Lemma；控制器为防止提前完成整步将步骤 verdict 标为 CHECKPOINT_ACCEPTED，图导入却与原始 ACCEPT 比较，产生 review_record_mismatch，路线以 route_requires_reevaluation 停止。工具 0，无最终答案。源码 manifest-04、原始状态与失败证据独立保留；临时观察任务已移除。

公共流式反例 `checkpoint-graph-red.json` 稳定复现同一误停。图来源现在绑定审查请求中的持久 checkpoint/report、对应 Reasoner 响应和原审查身份，识别嵌套 checkpoint 的 claims；旧检查点的分类成果不再依赖被后续报告覆盖的当前 step.verification。保留原有记录失效、版本、调用身份、引用、分类和真实回执校验，不绕过路线失效保护。`checkpoint-graph-green.json` 因 fixture 把第二步绑定到已完成根目标而错误送出后续响应，`green-02` 超出原 8 秒观察窗口，二者不计通过；修正 fixture 为两个有依赖的独立根目标后 `green-03` 通过。`checkpoint-graph-final.json` 26 项通过（含六组来源篡改拒绝断言），`checkpoint-graph-regression.json` 图、路线 guard 与 checkpoint 回归 29 项通过；均无 failure/error/skip，不能代替下一次真实验收。

`live-17-checkpoint-graph/`：Run `run_31247a671db40410326ea21920cecfe1`，源码 manifest-05；11 次模型调用，0 次实际工具，合法 6 工作块、1 路线。首步仅选择方法，却同时映射后续才证明的 O1；Verifier 两次 YES/PASS/ACCEPT，同时声明 general_proof、both_directions_proved=false。原控制器严格保留质疑，独立反例搜索两次 NOT_FOUND 均不作为证明。Meta 最后提出 CONTINUE，但路线前沿重复，以 route_duplicate_route_frontier 停止。图导入没有拒绝记录，不能将这次失败归于 live-16 已修复的来源错配；原 Run 不改写，定时观察已移除。

后续只补角色指引：Planner 的纯准备工作优先使用既有辅助目标，根证明留给实际证明步骤；Verifier 对纯选方法/定义省略可选 answer_claim，该字段不是通用审查摘要。实际数学断言仍须审查，缺失证明保持 false/CHALLENGE，true 仅用于实际满足全部适用证明义务；未来工作不能冒充 Lemma/Answer。`review-scope-red.json` 复现出站消息缺少这项说明，不是确定性复现真实模型行为；指引是否有效仍须独立真实新 Run，不能由字符串断言推断。

`review-scope-green.json` 的 27 项中 26 项通过、一项新增消息 fixture 遗漏原题而报 missing_original_problem；补齐原题后只复跑受影响项，`review-scope-green-02.json` 1 项通过。`review-scope-counterexample.json` 原有 12 项反例机制回归通过；Ruff 和 diff 检查通过。不将前一批报告写成 27 项全通过。

`live-18-review-scope/` 在服务尚未监听时连接失败，无 Job/模型调用；健康检查成功后另建 `live-19-review-scope/`，Run `run_091c7c753bd26e21bb085150b1722781`。新指引仍未改变子集题的首步混淆：规格将普通计数误标 extremum_bound，方法选择与后续证明重复映射；一次反例响应的 FOUND_COUNTEREXAMPLE 与自身最终承认没有反例的文字矛盾。12 次调用、0 次工具，最终 route_duplicate_route_frontier。严格状态和原失败保留，不能靠解析猜测改写裁决。

为区分复杂题的模型语义问题与串行工程可达性，使用更小的两阶段数值题：先用 Python 求 S=1²+…+100²，再以 S 为上界用 Python 求 T=1+…+S，最后用三角数公式核对。独立公式与直接求和事前交叉核对为 S=338350、T=57240530425，参考不传给模型，不将小题结果外推为子集题或准确率通过。`live-20-serial-numeric/`，Run `run_efc63fc8ba7b1a86455eef1c70c2e226`，源码 manifest-06，12 次模型调用、3 次成功 python_math；每次 executed=true、exit_code=0、cleanup_verified=true。合法 5 工作块，但模型把“制作另一份计划”作为 S1，Verifier 混淆该步骤和后续实际执行，最后 partial_budget_exhausted，无 accepted 串行步骤、无整题答案。定时观察移除。

最后一项增量只说明 Planner 的返回本身满足用户先计划要求，执行工作块不再次制作或复述计划，从首个未完成数学目标开始。仍由模型生成全部步骤，不自动删改其计划。`recursive-plan-red.json` 保留消息缺口；`recursive-plan-green.json` 因预期数量 8 与实际 7 不符在执行前拒绝，不计通过；修正数量后的 `recursive-plan-green-02.json` 7 项通过。消息断言仅证明指引存在，实际效果待真实复验。

live-20 的预算停止细因是 `route_expansion_budget_reserved`，不是用尽 48 次模型调用；12 次调用后仍受路线扩展准入与收尾预留约束，不能从计数推断可继续重规划，也不为验收重置限额。

`live-21-plan-execution/`：Run `run_e5effd610d570a09c1bc6ec700284adb`，源码 manifest-07。Planner 本次生成直接计算 S、计算 T、核对 T 的三个合法工作块，没有另设制订计划步骤。6 次模型调用、1 次成功 Python，但首个 YIELD 在 Verifier 通过真实工具续接接受后，分类账本仍保存工具执行前的审查 ID，图导入比较原回复，报 review_did_not_accept_record，以 route_requires_reevaluation 结束。尚无 accepted 完整步骤；失败、源码和数据不改写。

`review-lineage-red.json` 在公共流式 Job、实际 Registry 和图演化路径复现同因误停。最小修复只让步骤审查的派发闭包在成功后记录实际续接及显式 retry 链的最终调用 ID，分类、义务证据和反例来源随原路径使用该 ID；不改变工具回执中的请求发起者、不增加调用或放宽图来源检查。`review-lineage-green.json` 同一反例通过，要求最终 ledger.review_call_id 以 :tool-1 结尾，实际 Registry 调用一次，保留六组来源篡改拒绝断言。

`review-lineage-final.json` 共运行 61 项，0 failure/error、2 skip，即 59 项通过。两项未执行为 `StarFullReferenceVerifierComputeTest.test_reference_step_verifier_executes_own_isolated_computation` 和 `StarFullReferenceClassifiedOutcomeTest.test_reference_classified_computation_carries_real_isolated_receipt`，原因均为未设置独立验证的本地 Docker image ID；不计通过、不改变依赖。上述真实 Python 回执独立记录，不替代这两项测试身份。

`live-22-review-lineage/`：Run `run_e084f5c7cb1c9cd5110eb04ca370f99f`，源码 manifest-08，7 次模型调用、2 次真实 Python。模型仍另设制订计划的 S1，在其中提前计算 S/T，并填写与实际输出不符的预期值；两回执为成功执行但 comparison_status=mismatched，不计已验证断言。未发生图导入拒绝，最终 route_duplicate_route_frontier，无完整串行步骤/整题答案。

同源码用中文明确“规划本身不算执行步骤，第一步计算 S；每步只处理当前目标”，`live-23-chinese-serial/`，Run `run_11091bac1ea343f0b234056d1257400d`。实际形成计算 S、计算 T、核对 T、输出四步计划；3 次调用、工具 0，S3 方法名为 verification，被原字符串 schema 接受后归为 unknown，串行路由以 route_method_required 停止。失败保留，不自动猜测替换方法。`method-vocabulary-red.json` 复现 wire schema 接受非控制词表字符串；方法 schema 现枚举既有 METHOD_IDS，仍包含 unknown，unknown 在串行路径仍由原 guard 拒绝。没有扩充方法或放宽路线接受规则。

`method-vocabulary-green.json` 30 项通过、0 failure/error/skip；增量 Standards/Spec 报告无剩余问题，明确这是一项提供方 wire 合同收紧，其他路径原有 normalize_method 和 unknown 路线拒绝不变。

`live-24-method-vocabulary/`：Run `run_d52f1ee072957967262560592dbcfdfa`，源码 manifest-09，6 次模型调用、2 次真实 Python。Planner 又生成准备步骤；Verifier 在该步骤审查中正确保留两条 Conjecture，图拒绝以 conjecture_not_importable 导入，但路线刷新将新增未导入猜想当作支持损失，以 route_requires_reevaluation 停止。未完成串行步骤，失败保留。

`conjecture-route-red.json` 用公共流式 YIELD 的 Lemma 加新 Conjecture 稳定复现同因误停。路线刷新现仅容许从未作为旧图推导来源的新 conjecture_not_importable 记录；旧拒绝必须保留，任何其他新增拒绝、旧证据撤回、冲突、失效和支持损失仍保持原 hard stop。猜想不进入已证图，不改变根义务或最终验收。

`conjecture-route-green.json` 公共 31 项、`conjecture-route-regression.json` 图与路线 38 项全部通过，均零 failure/error/skip；增量双轴报告无剩余问题，不替代真实复验。

`live-25-conjecture-route/`：Run `run_3801ac7d98bbc0abab4228d83f7b7aa6`，源码 manifest-10，7 次模型调用、1 次成功 Python。首个计算步骤首次达到 ACCEPTED，实际得到 S=338350，图无拒绝记录；Verifier 将根义务的 evidence_category 写成 classified_outcomes 使用的 Computation，未满足 existence 根义务的既有类型准入，第二步以 work_unit_prerequisites_incomplete 停止。没有完整答案；失败与回执保留，不将步骤通过等同于根义务完成。

`obligation-label-red.json` 复现 wire schema 接受上述错误分类。提供方 schema 现在按当前规格的根 ID 及既有 `_EVIDENCE_TYPES` 逐项约束证据标签，并要求非空 claim_indexes；角色说明区分根义务证据标签与分类成果类型。控制器的实际论证、claim 引用、真实回执与义务准入保持原样，不将标签本身当证明，也不把 Computation 自动改写成 existence_witness。`obligation-label-green.json` 32 项通过，零 failure/error/skip；下一次真实执行仍须独立验收。

`live-26-obligation-label/`：Run `run_f84d9b4ea7001097abebbdf017bb7b3c`，源码 manifest-11，13 次模型调用、3 次成功 Python。S1 ACCEPTED 并满足根义务，S2 能实际派发；一次 T 的预期输出不符，独立核验工具重新执行得到正确的 57240530425。S2 报告仍把后续公式核对列为当前缺口而受到 CHALLENGE；纠正响应为 invalid_json（额外尾部内容），一次格式修复却返回 schema 文档而非实例，终止为 protocol_failure_unrepaired。两条不比较预期的回执分别得到正确 S/T；预期不符的回执只计真实执行，不计已验证断言。刷新 refresh_no_calls=true、0 新 POST、浏览器 errors=[]，未取得整题成功；临时检查已移除。

双轴收敛审查另发现空规格构造的兼容性退化：既有 `test_specification_protocol_fields_are_added_only_to_opted_in_requests` 使用 problem_spec={}，新 schema 曾直接索引 root_obligations。`empty-spec-red.json` 为 1 error；本次最小修复仅让缺失/空根列表的构造接受空声明数组（maxItems=0），不生成空 oneOf，也不授予未知根 ID。原 label 测试增加两种空构造断言；`empty-spec-green.json` 10 项通过。有效规格仍须原规范化，不改变真实运行准入。后续验收题缩为两个有依赖的 Python 计算步骤，不另设公式核对步骤；同样需要实际串行接受、独立整题检查与恢复，不能据此外推复杂数学能力。

`live-27-two-step/`：Run `run_ae4f9a95c3515743f2b15691bb5821c4`，源码 manifest-12。10 次模型调用、1 次实际 Python；核验器明确陈述当前 S1 已完成，却因为 T 和最终输出尚未完成给出 PARTIAL/CHALLENGE。纠正后路线前沿重复，严格以 route_duplicate_route_frontier 停止，未取得两个接受步骤或整题成功；刷新无新调用/POST、errors=[]，定时检查已移除。缩减题目步骤未解决核验范围混淆，不能将此失败继续归于题目难度。

后续将实际 WorkUnit 映射派生为只读 step_review_scope，传给步骤核验器；同一纯函数限定其 schema 可声明的根 ID，与控制器原有映射准入对齐。全题规格仍在上下文，独立整题检查继续负责后续目标和完整输出。说明仅在当前目标由有效论证和真实证据建立时接受，不自动改写模型的 PARTIAL 或伪造证明。`step-scope-red.json` 为缺少出站 scope 的 1 failure，`step-scope-green.json` 1 项通过；`step-scope-final.json` 35 项通过、零 failure/error/skip，覆盖两个真实 port 流式串行 fixture 和原 S03 义务/依赖合同。`standards-step-scope-final.md`、`spec-step-scope-final.md` 无新增阻塞；这些工程证据不保证真实模型遵循范围。
