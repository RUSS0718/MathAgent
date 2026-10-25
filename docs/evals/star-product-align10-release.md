# ALIGN-10 来源复核、真实批次与发布判断记录

状态：ALIGN-10（#80）第 1+2 轮实际执行记录。完成声明以本文件证据为准；真实非快通道闭环两轮共 29 批仍未取得，ALIGN-AC-18 记 not_covered（见 §3、§3.2），不因其余门禁通过而升级。日期：2026-10-25。固定基点：分支 `fix/star-align-10-source-release`（基 `showcase-star-align` 尖端 `96a1c29`，ALIGN-01..09 全部合入），本票提交：第 1 轮 `0abf438`（null 候选协议）、`f9861b3`（探索有界格式修复，含 star_routing 特性门）、`f1512e2`（zod 升级）、`0d6e9ff`（文档）；第 2 轮 `c73561d`（步骤/审查修复属主）、`20ed31e`（禁回声 schema 指令）、`96d5cec`（枚举与待决计算指令）、`b1624b7`（非法转义救助重析）、`439dd2c`（隔离执行预算校准）、`b3d55e1`（修复指令长度约束）及文档提交。

本记录不宣称数学正确率、论文成绩复现或所有题型可解；LLM 接受不是形式化证明。父 Issue #70 与历史 #56/#69 不由本票关闭或改写。

## 一、全量门禁（ALIGN-AC-19）

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| 离线合同与全量套件 | `uv run python scripts/check.py --offline` | 第 1 轮终跑 PASS：599 tests/29 跳过；第 2 轮全部提交后终跑 PASS：**605 tests，OK（30 跳过，965.9s）**；独立 `uv run python -m unittest discover -s tests -p "test_*.py"` 第 2 轮复跑 PASS：605 tests，OK（30 跳过，968.8s）。跳过全部为镜像 env 门控，归因见 §1.1 |
| 固定镜像真实 Docker 全量 | `MATHAGENT_TEST_PYTHON_IMAGE=sha256:fc913659…31673a2d uv run python -m unittest discover -s tests -p "test_*.py"` | 第 1 轮 PASS：596 tests **0 跳过**（1261.6s）；第 2 轮全部提交后终态复跑 PASS：**605 tests，0 跳过**（1301.3s），30 项镜像门控用例全部真实执行 |
| 产品发布检查 | `uv run python scripts/check_showcase_release.py` | 第 1、2 轮各一次 PASS（`showcase_release=PASS`，含 `SHOWCASE_RELEASE_GATE=1` 全量套件、workspace 干净契约、`check_solver_release`、BASELINE.json 逐文件 sha256、`import user_agent` 导入边界、replay 凭证扫描、发布证据链） |
| 前端依赖安装 | `npm ci --no-audit --no-fund` | 两轮各一次 PASS：66 packages |
| 前端依赖审计 | `npm audit --audit-level=high` | 初次 FAIL：zod 4.1.5 命中 GHSA-mrhx-c7xc-m3w5（high）。升级 `zod` 至 4.6.7（精确锁版，依赖合同 allowlist 不变，commit `f1512e2`）后 PASS：0 漏洞 |
| 前端合同 | `npm run check` | 两轮多轮 PASS：依赖合同/类型检查/14 unit/构建 |
| 真实公共浏览器回归 | `npx playwright test -c playwright.product.config.ts` | 两轮各一次 PASS：12/12（第 2 轮 38.8s） |

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



## 三A、第 2 轮真实批次（ALIGN-AC-18 续）

目标：在第 1 轮修复（null 候选、探索修复属主）之上取得完整非快通道闭环。批次硬预算随证据校准并逐批预登记：26/26/6 调用、1100s、262144 tokens（≤完整预设包络），单响应输出上限 12288，提供方 timeout 300→420s，thinking 模式默认开启（一次关阀实验 `94135a30` 证明关阀使格式纪律显著恶化，两连发 schema 回声）。

| 批次 | 结果 | 调用/tokens/工具 | 判定与保留 |
| --- | --- | --- | --- |
| `…T071935Z-6f62aea8` | failed（partial_budget_exhausted） | 11 / 145,651 / 4 | **最接近闭环**：NEED_PLAN→Plan(v1)→步骤 1 报告并审查通过、4 次真实回执；死于本票自设 180k token 批次硬预算（随后提高到 262144） |
| `…T072935Z-aab5ffb7` | failed（interrupted） | 8 / 64,016 / 3 | 探索修复 live 生效；reasoner 修复 live 生效；一次 reason_noncoding 调用 180s 超时→真 unknown 保留 |
| `…T073938Z-58d260ae` | failed（interrupted） | 3 / 61,293 / 2 | 工具沙箱超时→unknown（推动 §四-3 预算校准） |
| `…T074620Z-867a48f9` | **succeeded** | 6 / 32,586 / 1 | **第 2 次 live 快通道工具闭环**：自然计算真实回执→润色→整题审查 ACCEPT→S4 same_artifact |
| `…T075149Z-86af2e74` 至 `…T090836Z-94135a30`（14 批） | failed | — | 逐批暴露并修复第 2 轮五类缺陷（见 §四A）；失败形态：整题审查 schema 回声×2、修复回复枚举外 `PENDING`、非法转义 invalid_json×2、整题审查 6.8k token 长文破坏 JSON、多次模型调用 420s 超时→真 unknown 保留、快通道整题审查诚实 REJECT（`5f25cd6f` completed_unverified） |
| `…T0913xxZ`（squaresum21，收尾批） | failed（interrupted） | 2 / 31,842 / 1 | 工具回执成功后，续接模型调用 420s 超时→真 unknown 保留 |

第 2 轮合计：18 批、97 次真实调用、约 1,013,322 charged tokens、22 次真实工具调用（其中校准后多批全部成功执行）、9 次 unknown（全部为模型调用或工具超时，零自动重发、预留保留）。两轮累计 29 批：116 调用 / 1,281,244 tokens / 37 工具 / 11 unknown。

### 3.2 第 2 轮结论与仍存的 not_covered

- **新增取得（live）**：reasoner 修复属主触发并救回步骤报告（`aab5ffb7`、`9b2862f0`）；探索修复属主多次触发救回；非法转义救助重析生效（`f2778974` 之前同类批次全部终止，修复后同类回复继续前进）；隔离执行 20s/15s CPU 预算下模型自然脚本（含 sympy）全部真实完成；`867a48f9` 第二次快通道工具+S4 闭环；`5f25cd6f` 快通道整题审查对可疑候选诚实 REJECT（completed_unverified，非接受）。
- **仍未取得（ALIGN-AC-18 维持 not_covered）**：非 Explore 快通道完整闭环。两轮最接近批次 `6f62aea8` 已实证 NEED_PLAN→合法 Plan→步骤审查通过→自然计算回执的全前置链路，其后未走完仅因当时批次 token 硬预算与两类残余方差：①提供方 thinking 长尾——单次模型调用偶发超 420s（全部按真 unknown 保留、零重发）；②长文本回复破坏 JSON——整题审查偶发 6.8k token 长文（修复指令已加长度约束，样本尚不足以证明消除）。产品侧已无已知阻断缺陷；不以 29 批中的片段证据或 scripted 验收冒充完整 live 闭环。
- live 自然 Challenge/Trace-Back/Replan 与分类账本/证明传递的 live 观察维持 not_covered（同第 1 轮口径）。

## 四A、第 2 轮发现并修复的产品缺陷（RED→GREEN）

1. `c73561d` **步骤与整题审查无协议修复属主**：reasoner/step_verifier/final_generator/whole_solution_verifier（终路与快通道两处）的一次 star_routing 门控格式修复（统一 `protocol_repair` 模块、`:repair-1` 独立身份）；CallInterrupted 显式捕获、不可修复原样上抛；S4 配套 `review_record` 解析完成态修复子调用。四条公共用例 RED→GREEN；149 项相关回归 + Docker 门控 31 项通过。
2. `20ed31e`/`96d5cec` **回复协议指令歧义**：live 证据（schema 回声、枚举外 PENDING）驱动的指令明确化——填值实例而非 schema 定义、待决 tool_request 仍带临时枚举裁决。
3. `439dd2c` **隔离执行预算系统性过紧**：8s 墙钟/3s CPU 使 sympy 导入级脚本普遍被杀为 unknown；校准 20s/10-15s（上游 600s，仍远低于），SP-09 合同补记校准；80M 求和公共 Docker 用例 RED（tool_error）→GREEN（成功、清理核验）。**复审更正：** 该校准当时未真正到达产品路径——`full_config`/`limited_config` 都没有 `tool_timeout_seconds`，`tool_precheck` 落回默认 3s，`container_tool` 的 `min()` 又把它压住，执行器声明的 20s 永远轮不到；配套 Docker 用例直接构造执行器、绕开了这条 seam，因此抓不到。见 §四B 修复。
4. `b1624b7` **完整回复内非法转义整体报废**：严格解析恰为 Invalid \escape 时仅对该类别加倍非法反斜杠重析一次；其他畸形仍失败、schema 仍严格。公共用例 RED→GREEN；"not json"等真畸形反例不变。
5. `b3d55e1` **修复回复长文再失败**：修复指令约束字符串 600 字符纯文本、无反斜杠/LaTeX。

## 四B、复审轮发现并修复的缺陷（RED→GREEN）

独立代码评审（标准轴 + 规格轴）在集成分支 `showcase-star-align` 上复核本轮交付，发现并修复：

1. **隔离执行预算未到达产品路径（最高优先级）**：`showcase/star_product_pipeline.py` 现在从已注册执行器继承 `tool_timeout_seconds` 写入 `config`/`full_config`，使 `tool_precheck` 下发的界与执行器声明一致。新公共用例 `test_product_config_carries_the_executor_tool_timeout_for_precheck` 先失败（键缺失）后通过，并在该键再次缺失或被压回 3 秒时失败。
2. **旁路探针把「注入造成崩溃」当成「识别成功」**：六份 `tests/*_mutations.py` 原先用 `not failures and not errors` 判定，注入一个抛 `TypeError` 的补丁同样会打印 "bypass detected"。新增 `tests/mutation_support.py` 的 `require_assertion_failure`，要求失败必须是断言失败、探针崩溃则明确报错；`tests/test_mutation_support.py` 用崩溃/断言失败/通过三种情况锁住该判定。
3. **旁路敏感性检查未接入门禁（AC-16）**：`scripts/check.py` 现在逐个执行六份探针，任何一项未识别即让仓库检查失败。
4. **AC-09 缺回执完整性与「不存在的审查」核验**：`showcase/solver_harness/classified.py` 新增 `_complete_receipt_ids`（回执须带 code/stdout 引用、输入与已结算状态）与 `_review_call_exists`（裁决所指审查调用必须真实存在且角色为审查者），拒绝原因分别为 `damaged_tool_receipt`、`unknown_review_source`；公共用例 `test_damaged_receipts_and_absent_review_source_are_rejected` 覆盖。
5. **AC-05 缺 easy-verify 独立重算覆盖**：新增 `test_verifier_independently_recomputes_an_easy_verify_claim`，验证审查者用不同参数独立重算并拿到自己的回执，而非复用 Reasoner 的 precheck。
6. **Definition 分类无正向用例**：新增 `test_definition_classification_is_established_and_reusable`，Definition 作为已证类别进入账本与 SSE。
7. **文档计数矛盾**：§八 的「599 项 / 29 跳过」改为最终态「605 项 / 30 跳过」，与 §1 一致。

以上修复不产生新的 live 证据，ALIGN-AC-18 仍维持 not_covered。

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
| ALIGN-10 #80（本票） | §1 门禁、§2 旁路汇总、§3/§3A live 批次（29 批）、§4/§4A 七笔 RED→GREEN 修复、§5 模式复核、来源映射文档 | live + scripted + 故障注入 + replay | AC-18 live 闭环 not_covered（产品侧阻断已清零，残余为提供方差差）；live Challenge/Trace-Back/Replan not_covered | 两轮 29 批 live（116 调用/1,281,244 tokens/37 工具/11 unknown 全保留）+ 两轮全量门禁机时 |

## 七、来源映射入口

全机制映射与七类修复来源复核见 [ALIGN-10 来源映射](star-product-align10-source-mapping.md)（固定论文 arXiv:2605.19338v1 + 上游 commit `5f2a86b5…`，逐项标一致/缺失/有意适配/项目扩展/冲突）。

## 八、发布判断

- 工程合同面（ALIGN-AC-19）：门禁全过（含最终离线复跑 605 项 30 跳过全部归因、镜像全量 0 跳过、发布检查 PASS、前端审计修复后 0 漏洞、浏览器回归 12/12）；官方冻结字节与导入边界不变。
- 语义修复面（ALIGN-AC-16/17）：旁路敏感性检查全部实际执行且有效；来源映射完成并有逐项证据。
- 真实能力面（ALIGN-AC-18）：**未完成**。两轮 29 批后非 Explore 快通道 live 闭环仍未取得（最接近批次 `6f62aea8` 已实证前置全链路，残余为提供方 thinking 长尾超时与长文回复破坏 JSON 两类方差，见 §3.2）；产品侧全部已知阻断缺陷已修复并有 live 逐项验证。本票整体保持未完成状态；快通道 live 工具闭环（两例，含一例诚实 REJECT）与全部失败路径的真实记录不升级为完整能力结论。
- 不自动关闭父 Issue #70；历史 #56/#69 记录不改写。
