# S09/F3 受限形式化工程合同

日期：2026-11-10（Asia/Shanghai）。状态：实现和验收映射已完成，最终门禁、双轴复核和 issue 交接待完成。

权威要求：[F3 实施票 #149](https://github.com/RUSS0718/MathAgent/issues/149)、[Lean 发布决议 #141](https://github.com/RUSS0718/MathAgent/issues/141#issuecomment-6702384094)、[阶段门禁 #144](https://github.com/RUSS0718/MathAgent/issues/144#issuecomment-6703147321)。本合同只细化验收入口，不改变这些要求。

起点为唯一集成树 `faithful-integration/Challenge-Cup-2026`，分支 `mathagent-faithful`，基线 `dab403489a6e07b9b06ba74a52f2cfd0ad7cfc82`。相对审计基线 `b7038798`，官方 `user_agent.py`、`implementations/` 和 `requirements.txt` 无差异。S01–S08 的退出证据见[文档索引](../README.md)。2026-11-08 的 Lean unavailable 只描述当时的环境。本轮已固定并实测 Lean 环境。

## 验收映射

| 合同 | 公共入口 | 持久状态及断言 | 验收证据 | 结果 |
| --- | --- | --- | --- | --- |
| #149 AC23 后端选择 | `POST /api/agent/jobs` 的 `formal_policy`、现有 ToolRegistry 和 BackendRegistry | Run 显式选择白名单中的 `lean_tactic_prover`；目标类型、最高等级、环境、协议格式和确定性登记在真实后端元数据中。唯一登记后端时，显式切换到未登记后端返回 409，不写入 attempt、不派发工具。 | `test_faithful_s09_backend.BackendRegistryContractTest`；`test_faithful_s09_public_job.FaithfulS09PublicJobTest.test_public_runtime_registers_backend_capability_and_rejects_out_of_scope_target`；`test_explicit_backend_switch_without_a_selectable_backend_is_rejected` | 通过；不注册 AlphaProof 或其他占位后端。没有第二个真实服务，因此正向跨后端切换保持未验证。 |
| #149 固定环境与 L2 | `LeanTacticProver` → `LeanDockerExecutor` | ProofArtifact 绑定镜像、部署和构建清单、Lean/Mathlib、模板、公理、依赖、目标、源码、内核输出、资源与 attempt 身份。 | `artifacts/faithful-s09-environment-final-02/deployment.json`；`dependency-audit.txt`；4 个公共 Job 的 `public-jobs/<job_id>/{job,report,evidence}.json` | L2 真实通过。镜像为 `sha256:ee09c4046b8edace6a8a8ae9cb9ff620ae576595c4f22f64b19b1faa36636101`，Lean 4.19.0，Mathlib v4.19.0，依赖审计 8/8。 |
| #141/#149 AC24 三层规格与 L3 | `IndependentSpecificationReviewer`；公共 Job、Report、Evidence | 独立审查绑定原题、ProblemSpec、形式目标、六项对应字段、证明环境和 attempt。内核通过只给 L2；独立审查通过后才给 L3。LLM_REVIEWED 单独保留。 | `artifacts/faithful-s09-public-real-final-02/public-acceptance.json` 和对应公共 Job 文件 | L3 真实通过，六项字段均确认。范围仅为固定有理数多项式模板，不外推为一般题目的自动形式化能力。 |
| #149 错误、未知和等级边界 | Policy、Specification、Kernel、Job、Report | 错误目标、额外假设、定义域、量词、方向、结论不符、`sorryAx`、未登记公理、环境漂移、PARTIAL、TIMEOUT、ERROR、UNAVAILABLE、UNKNOWN 均不得升级；未知不自动换后端或重发。 | `test_faithful_s09_backend`、`test_faithful_s09_correspondence`、`test_faithful_s09_kernel`、`test_faithful_s09_public_job`、`test_faithful_s09_public_integration` | 56 项 F3 聚焦测试通过。回执 attempt 身份不匹配记为 UNKNOWN，保留已测成本且不保留伪造证明；非 Mapping policy 返回结构化 400。 |
| #149 重试、lineage 与预算 | `/api/agent/jobs/{job_id}/formal-attempts` 与 Solver CAS | 用户显式重试创建子 attempt，保留父 lineage、累计成本、unknown、原 deadline 和幂等 action。CAS 冲突与写入失败均不丢失 attempt 或留下半提交状态。 | `test_faithful_s09_public_job`、`test_faithful_s09_public_recovery`、`test_faithful_s09_public_integration` | 通过。单工具预算耗尽标为 unavailable，不再派发第二个工具调用。 |
| #141 普通答案兼容与旧 Run | Job result semantics、Report、Evidence | 默认关闭；无 formal policy 的旧结果不迁移；失败不覆盖已有答案或 LLM_REVIEWED。只有用户显式要求形式化验证时才标记该要求未满足。 | `test_old_result_without_formal_policy_keeps_formal_requirement_absent`、`test_require_formal_failure_keeps_answer_and_marks_requirement_unmet`；桌面/移动真实 Job 浏览器测试 | 通过。旧答案与普通审查级别保持独立。 |
| #146 公共产品接线 | Job GET、Report、`/api/runs/{id}/evidence`、RunReview | Job、attempt、等级、答案与 Evidence 使用同一持久记录；刷新为只读，不新增求解 POST；服务重启后仍可读取。 | `artifacts/faithful-s09-public-real-final-02/browser-l2-report.json`、`browser-l3-report.json`、`restart-public-reads.json` 和 final-02 SQLite | L2 桌面/移动 2/2，L3 桌面/移动 2/2；JSON 报告均为 0 skip、0 flaky。重启后同一 SQLite 的 L2、L3 Job、Report 与 Evidence 一致。 |
| #144 工程退出 | 唯一最终门禁 | F3 聚焦、相关回归、前端检查、Standards/Spec 双轴复核、修复复查及冻结源码门禁全部留证。 | `artifacts/final-gates/faithful-s09-01/`（待生成） | 进行中。最终门禁通过后更新本行和源码 SHA。 |

## 范围与退出边界

首批仅覆盖固定模板可表示的有理数多项式恒等式。L2 要求固定隔离 Lean 环境真实接受指定目标，并通过登记公理与传递依赖审计。L3 还要求独立确认原题到 ProblemSpec、ProblemSpec 到形式目标的定义域、变量、量词、假设、方向和结论。LLM_REVIEWED 不是 L2 或 L3。

受控表达式按其语法树直接生成 Lean 目标。Python 不对表达式作数学化简，也不替代 Lean 内核。错误、超时、不可用或未知只描述验证状态，不解释命题为假。形式化不可用时保留原答案。

本轮不调用付费 provider，不实施 S10/F4/F5，也不把 F6、F7 或 F8 的基础接线视为整票完成。真实 provider、容量/SLA、自然题和独立数学效果保持 `not_run`。工程测试与固定模板 L2/L3 通过不构成数学能力提升证据。

独立规格检查只接受可完整解析的固定模板。LLM 子代理不代表人工审核。客户端 `reviewed=true` 不会获得独立审核权限。语法未知、题意有歧义、根义务不完整或字段不一致时不得标 L3。

最终门禁遵循[工程门禁](development-gates.md)。单次运行的自动检查不可用，因此在当前会话持续观察唯一后台进程；不创建或声称创建定时任务。运行产物只写入忽略的 `artifacts/`。`tests/test.md` 不读取、不搜索、不快照、不修改、不提交、不删除。
