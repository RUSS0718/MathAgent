# ALIGN-10 来源复核、真实批次与发布判断记录

状态：ALIGN-10（#80）第 1 轮实际执行记录。完成声明以本文件证据为准；真实非快通道闭环本轮未取得，ALIGN-AC-18 记 not_covered（见 §3），不因其余门禁通过而升级。日期：2026-10-25。固定基点：分支 `fix/star-align-10-source-release`（基 `showcase-star-align` 尖端 `96a1c29`，ALIGN-01..09 全部合入），本票提交 `0abf438`（null 候选协议）、`f9861b3`（探索有界格式修复，含 star_routing 特性门）、`f1512e2`（zod 升级）与文档提交。

本记录不宣称数学正确率、论文成绩复现或所有题型可解；LLM 接受不是形式化证明。父 Issue #70 与历史 #56/#69 不由本票关闭或改写。

## 一、全量门禁（ALIGN-AC-19）

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| 离线合同与全量套件 | `uv run python scripts/check.py --offline` | PASS（最终复跑，含本票全部提交）：599 tests，570 通过/29 跳过（949.3s），workspace 合同、测试接缝、`demo_server --help`/`showcase_server --help` 与 repository_check 全 PASS |
| 固定镜像真实 Docker 全量 | `MATHAGENT_TEST_PYTHON_IMAGE=sha256:fc913659…31673a2d uv run python -m unittest discover -s tests -p "test_*.py"` | PASS：596 tests（两笔修复提交前基点），**0 跳过**（1261.6s）；29 项跳过全部为该镜像 env 门控，归因见 §1.1 |
| 产品发布检查 | `uv run python scripts/check_showcase_release.py` | PASS（`showcase_release=PASS`，含 `SHOWCASE_RELEASE_GATE=1` 全量套件、workspace 干净契约、`check_solver_release`、BASELINE.json 逐文件 sha256、`import user_agent` 导入边界、replay 凭证扫描、发布证据链） |
| 前端依赖安装 | `npm ci --no-audit --no-fund` | PASS：66 packages（15s） |
| 前端依赖审计 | `npm audit --audit-level=high` | 初次 FAIL：zod 4.1.5 命中 GHSA-mrhx-c7xc-m3w5（high）。升级 `zod` 至 4.6.7（精确锁版，依赖合同 allowlist 不变，commit `f1512e2`）后 PASS：0 漏洞 |
| 前端合同 | `npm run check` | PASS：依赖合同/类型检查/14 unit/构建（升级前后各跑一次均过） |
| 真实公共浏览器回归 | `npx playwright test -c playwright.product.config.ts` | PASS：12/12（40.3s） |

### 1.1 跳过逐项归因（修复前离线套件 29 项）

全部为 `MATHAGENT_TEST_PYTHON_IMAGE` 门控，不含 xfail：`test_star_product_full_modes` 11、`test_python_executor_docker` 6、`test_star_product_python` 3、`test_star_product_protocol_failure` 2、`test_star_product_explore_compute` 1、`test_star_product_classified_outcomes` 1、`test_star_product_verifier_compute` 1、`test_star_product_continue_identity` 1、`test_star_product_guidance_consumption` 1、`test_star_product_replan_decision` 1、`test_star_product_align_recovery` 1。上表镜像全量以同一套件把 29 项全部真实执行（0 skip）。

### 1.2 官方冻结与导入边界

`check_showcase_release.py` 内含 BASELINE.json 逐文件 sha256、`import user_agent` 不引入 showcase、replay 凭证扫描与发布证据链检查；本票两笔代码提交（`0abf438`/`f9861b3`）只触及 `showcase/solver_harness/` 与 `tests/`，官方冻结入口、`implementations/`、默认预算与 JSON 合同零改动（diff 复核）。

## 二、旁路敏感性检查汇总执行（ALIGN-AC-16）

全部在本轮真实执行；每项故意绕过时对应公共验收失败（"bypass detected by public acceptance failure"），无一项以自报成功、非空引用或白名单代替：

| 机制 | 检查（命令） | 实际输出 |
| --- | --- | --- |
| 裁决消费 | `uv run python -m unittest tests.test_star_product_guidance_consumption.StarGuidanceConsumptionTest.test_bypassing_the_consumption_gate_reproduces_stale_preemption tests.test_star_product_replan_decision.StarReplanDecisionTest.test_bypassing_the_approval_gate_reproduces_the_stale_guidance_archive` | 2 用例 OK：绕过当前转换门/审批门时旧裁决抢占复现（检查有效） |
| 独立工具执行（Verifier/Explore） | `uv run python -m tests.verifier_compute_mutations`；`uv run python -m tests.explore_compute_mutations` | skipped isolated execution、replaced receipt output（#75）；skipped isolated execution、replaced receipt output、exploration finding without adopted computation（#76）——各旁路均被公共验收识别 |
| 分类账本 | `uv run python -m tests.classified_outcomes_mutations` | dropped classifications、unverified receipts and dependencies、promoted conjectures 三旁路均被识别 |
| 证明传递 | `uv run python -m tests.final_proof_mutations` | dropped proof delivery、archived derivation resurrection 被识别（第三项见下行） |
| S4 绑定 | 同上（`tests.final_proof_mutations` 第 3 探针） | S4 text binding bypass 被识别 |
| 已知协议失败栅栏（配套） | `uv run python -m tests.star_protocol_failure_mutations`；`uv run python -m tests.star_recovery_mutations` | 4 旁路（误归 unknown、未修复不终止、关 schema 伪造成功、绕过 unknown 决策门）+ 2 旁路（unknown 决策守卫、completed 复用）均被识别 |
| 回执恢复栅栏（配套） | `tests.test_star_product_align_recovery.StarAlignChainRecoveryTest.test_bypassing_receipt_recovery_reexecutes_the_computation` | OK：绕过回执恢复栅栏时重复执行被公共验收识别 |

## 三、真实 Intern 公共批次（ALIGN-AC-18）

启动器：仓内 ignored 产物 `artifacts/star-align10-live-runner.py`（sha256 记录于各批 `preregistration.json`），只经 `create_app`、认证会话与公共 Job/Run/SSE/report/Evidence 端点；无 mock、无私有求解循环；`SHOWCASE_STAR_FULL_ENABLED`+合同镜像真实预检，`star_reference` 模式，真实 `InternChatClient`→`InternModelAdapter`（intern-s2）→控制器/S3/Registry/S4。每批先落 `preregistration.json`（硬预算、题面 sha256、runner sha256、commit、镜像、`automatic_unknown_retry=false`）再提交；产物含 events/evidence/report/run/usage/job-acceptance/hashes，全部在 `artifacts/star-align10-live-*/`（ignored，不入提交）。

批次硬预算（预登记）：模型调用 14–18、HTTP 14–18、工具 3–6、运行 480–650s、tokens 131072–180224（均≤完整预设 48/48/8/262144/1100s）；单响应输出上限 4096–8192；提供方 timeout 180s、retry=1。真实 API 授权沿用既有验收授权；该授权不代替产品内单个 unknown 的人工重试决定——本轮所有 unknown 零重发，两批 unknown 工具调用保持 needs_review 原样。

| 批次 | 题 | 结果 | 调用/tokens/工具 | 判定与保留 |
| --- | --- | --- | --- | --- |
| `…T043352Z-51875bc2` | poulet_numbers | failed（partial_budget_exhausted） | 5 / 25,913 / 3 | 探索自然提出并真实执行 3 次隔离计算（回执可核），整题审查又提出计算时工具硬预算耗尽：诚实终止，unknown=0 |
| `…T043729Z-6a1828b2` | divisor_pair_count | failed（partial_aborted） | 4 / 16,973 / 1 | Explore 快通道 SOLVED+真实回执；整题审查回复为 schema 回声（invalid_json，完整接收）→ 已知协议失败诚实终止 |
| `…T044038Z-07187983` | zeckendorf_counts | failed（partial_aborted） | 1 / 4,585 / 0 | 探索散文式回复 invalid_json；当时无修复属主（催生本票修复 f9861b3） |
| `…T044231Z-d6812cac` | square_sum_parity | failed（partial_aborted） | 1 / 1,991 / 0 | 探索 NEED_PLAN+自然 tool_request，但 `solution_candidate: null` 被 invalid_role_schema 拒绝（催生修复 0abf438） |
| `…T044757Z-be6133c3` | square_sum_parity（修复 null 后） | failed（partial_aborted） | 1 / 2,134 / 0 | NEED_PLAN+null 已接受前进到 tool_request；回复内代码字符串含非法 JSON 转义 → invalid_json（催生探索修复属主） |
| `…T045710Z-5efacb82` | square_sum_parity（两修复后） | failed（interrupted） | 3 / 65,783 / 2 | NEED_PLAN 达成、2 次正确 DP 回执（秒级）；第 3 个自选脚本超沙箱时限 → 工具 unknown_outcome(timeout)，保留预留、零重发 |
| `…T050232Z-0829975e` | digit_sevens | **succeeded**（completed_llm_reviewed） | 6 / 22,162 / 2 | **live 快通道工具闭环**：探索自然计算 2 次（真实隔离回执、镜像匹配）→润色→整题审查 ACCEPT→S4 `same_artifact` 绑定交付；unknown=0。Explore 快通道，不满足 AC-18 非 Explore 要求 |
| `…T050507Z-8b994f49` | zeckendorf_counts | failed（interrupted） | 3 / 29,603 / 1 | **探索格式修复 live 生效**（invalid_json→`:repair-1` 独立身份完成）；修复回复的验证脚本超时限 → 工具 unknown，保留 |
| `…T051010Z-fbafee6d` | zeckendorf_counts | failed（interrupted） | 2 / 25,314 / 1 | 同上形态（运行器改题失误，题面未按预期缩小验证范围，如实记录） |
| `…T051423Z-7dc33b55` | zeckendorf_counts（验证范围 n≤1000） | failed（partial_aborted） | 2 / 7,574 / 0 | 探索与修复回复均为散文式 invalid_json（完整接收），修复耗尽诚实终止 |
| `…T051634Z-c39ab987` | square_sum_parity | failed（partial_aborted） | 2 / 3,978 / 0 | 探索两次回复均为 schema 回声（invalid_json），修复耗尽诚实终止 |

合计：11 批、31 次真实逻辑调用、208,194 charged tokens、8 次真实工具调用、2 次 unknown（均为工具沙箱超时，预留与原文保留）、0 次自动重试、0 次人工 unknown 决定。模型身份 intern-s2（提供方返回一致）；成本字段缺失记 `cost=null`（`cost_missing_is_not_zero`）。

### 3.1 结论与 not_covered

- **取得**：live 自然受控计算（Explore 与整题审查双侧）、真实隔离回执、S4 绑定快通道闭环、已知协议失败与 unknown 的 live 区分、探索修复的 live 触发与独立身份、每批身份与用量对账（preregistration→usage→hashes 可核）。
- **未取得（ALIGN-AC-18 记 not_covered）**：非 Explore 快通道完整闭环的 live 证据。受阻原因是真实模型侧协议方差的三种形态（嵌入代码的非法 JSON 转义、散文式回复、schema 回声）与自选脚本超沙箱时限；产品侧对每种形态的行为（已知失败、有界修复、诚实终止、unknown 保留）均被 live 证实并已有公共验收。NEED_PLAN+自然计算+回执的 live 片段已在两批中出现，缺的是其后 plan→步骤→整题审查→S4 的完整链路。不以 scripted 验收或快通道成功冒充该证据。
- **live 未触发的 Challenge、Trace-Back、Replan：not_covered**；其适用行为由 #71/#73/#77/#72/#78 的可控分支公共验收支撑（scripted/故障注入），不强迫模型表演。
- 后续轮次可循的方向（本轮如实记录，不预支结果）：为整题审查与步骤回复评估同型有界修复属主（与 planner/explore 同一 #70 决策线）、以更小验证范围降低脚本超时方差后重试。

## 四、本轮发现并修复的产品缺陷（RED→GREEN）

1. `0abf438` **探索/步骤回复协议拒绝显式 null 候选**：真实 NEED_PLAN 回复（`solution_candidate: null`）被 invalid_role_schema 拒绝并在 Planner 前终止。公共用例先失败（`test_need_plan_reply_with_null_candidate_enters_the_plan_path`）后通过；explore/STEP schema 接受 OPTIONAL_TEXT，下游归一化原本就只认字符串，行为不变。
2. `f9861b3` **探索阶段无协议修复属主**：完整接收但非法 JSON 的探索回复（转义/散文）直接终止，#74 的有界修复只覆盖 Planner。按 #70 有界恢复决策补一次独立身份（`:repair-1`）修复，经同一 counters/S3 预留；耗尽仍诚实终止；真 unknown 人工栅栏不变。两条新公共用例先失败（去掉实现时 FAIL 2 项）后通过；既有 streamed 反例改驱动修复耗尽，保持原不变量；相关回归 88 项通过。

两笔修复均由 live 批次证据触发、有唯一责任归属（本票）与 RED→GREEN 记录；官方冻结文件零改动。

## 五、模式身份实际复核（reference / Best-Effort / 受限 / 消融）

在固定镜像下真实执行 `tests.test_star_product_full_modes` 全组（含 11 项镜像门控用例）：reference 恰 9 核心特性且 `config_hash` 逐字段一致（`test_reference_preset_is_exactly_nine_core_features_and_registry_inactive`）；任一核心特性缺失/关闭在入队前 503 拒绝且零出站（`test_each_core_feature_missing_or_disabled_rejects_before_enqueue`，18 组消融组合）；reference 公共 Job 真实工具+整题审查+S4 绑定（`test_reference_runs_same_public_job_with_real_tool_and_whole_review`）；Best-Effort 硬预算后纯选择零新增调用且回放零派发（`test_full_best_effort_selects_after_one_call_and_replays_without_dispatch`、`…_deadline_selects_only_previously_committed_candidate`）；受限模式不因 full 开关升级、默认 legacy 不受影响（`test_full_flag_does_not_upgrade_limited_mode_or_default_legacy`）；无隔离 Registry 时完整预设关闭（`StarFullUnavailableTest`）。核心缺项不能经关闭开关、改名或测试专用路径掩盖的合同由上述消融组直接覆盖。

## 六、各子工单公布（实际检查、证据类型、已知缺口、成本）

| 子工单 | 实际检查（本轮执行的公共验收） | 证据类型 | 已知缺口 | 成本 |
| --- | --- | --- | --- | --- |
| ALIGN-01 #71 | `tests.test_star_product_guidance_consumption`（含旁路反例、镜像门控 reference 用例） | scripted/fault_injection；恢复窗口为真实子进程退出 | live Trace-Back/旧裁决抢占未触发（not_covered） | 计入离线套件；无 live 调用 |
| ALIGN-02 #72 | `tests.test_star_product_continue_identity`（含进程退出恢复、reference 用例） | scripted + 真实子进程退出 | live PROPOSE_REPLAN→CONTINUE 未触发 | 同上 |
| ALIGN-03 #73 | `tests.test_star_product_replan_decision`（三分支、旁路反例、恢复一次、reference 用例） | scripted/故障注入 | live Replan 未触发 | 同上 |
| ALIGN-04 #74 | `tests.test_star_product_protocol_failure` + `star_protocol_failure_mutations` | scripted/故障注入；本轮 live 批次实证区分与修复触发 | 整题审查/步骤回复修复属主未设（见 §3.1 方向） | 同上 + 本轮 11 批 live |
| ALIGN-05 #75 | `tests.test_star_product_verifier_compute` + `verifier_compute_mutations` | scripted | live Verifier 自然计算未在步骤审查中触发（快通道整题审查侧已见计算请求） | 计入离线套件 |
| ALIGN-06 #76 | `tests.test_star_product_explore_compute` + `explore_compute_mutations` | scripted；live 批次实证自然探索计算与回执 | live 计划路径消费探索计算未走通（AC-18 not_covered） | 同上 + live |
| ALIGN-07 #77 | `tests.test_star_product_classified_outcomes` + `classified_outcomes_mutations` | scripted | live 分类裁定未观察到（批次未进入步骤审查） | 计入离线套件 |
| ALIGN-08 #78 | `tests.test_star_product_final_proof` + `final_proof_mutations` | scripted | live 证明正文传递未观察到（同上） | 同上 |
| ALIGN-09 #79 | `tests.test_star_product_align_recovery`（五窗口真实退出、镜像 reference 链） | 真实子进程退出 + scripted | live 恢复未触发 | 计入离线套件 |
| ALIGN-10 #80（本票） | §1 门禁、§2 旁路汇总、§3 live 批次、§4 两笔修复、§5 模式复核、来源映射文档 | live + scripted + 故障注入 + replay | AC-18 live 闭环 not_covered；live Challenge/Trace-Back/Replan not_covered | 11 批 live（31 调用/208,194 tokens/8 工具）+ 门禁机时 |

## 七、来源映射入口

全机制映射与七类修复来源复核见 [ALIGN-10 来源映射](star-product-align10-source-mapping.md)（固定论文 arXiv:2605.19338v1 + 上游 commit `5f2a86b5…`，逐项标一致/缺失/有意适配/项目扩展/冲突）。

## 八、发布判断

- 工程合同面（ALIGN-AC-19）：门禁全过（含最终离线复跑 599 项 29 跳过全部归因、镜像全量 0 跳过、发布检查 PASS、前端审计修复后 0 漏洞、浏览器回归 12/12）；官方冻结字节与导入边界不变。
- 语义修复面（ALIGN-AC-16/17）：旁路敏感性检查全部实际执行且有效；来源映射完成并有逐项证据。
- 真实能力面（ALIGN-AC-18）：**未完成**。非 Explore 快通道 live 闭环未取得，本票整体保持未完成状态；快通道 live 工具闭环与全部失败路径的真实记录不升级为完整能力结论。
- 不自动关闭父 Issue #70；历史 #56/#69 记录不改写。
