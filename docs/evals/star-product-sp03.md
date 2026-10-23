# SP-03 共享资源与取消验证记录

日期：2026-10-23。规格[#59](https://github.com/RUSS0718/MathAgent/issues/59)，合同见[SP-03执行合同](../engineering/star-product-sp03-contract.md)。开发基点为集成`2abc642`（含SP-02）。本记录只证明指定工程行为，不证明数学正确率，也不解除完整参考模式的恢复/隔离发布门槛。

## 实际修复与失败先例

| 公共反例 | 修改前真实失败 | 修改后 |
| --- | --- | --- |
| 一次HTTP timeout后重试再完成三角色 | 固定3HTTP导致第四attempt无法发出，STAR失败 | 可信S3限额显式接线，3logical/4HTTP；旧unknown预留保留，已知usage30 |
| 整题Verifier返回后、数学CAS前cancel | Job已canceled，实际Solver仍写completed_llm_reviewed | 数学事务内检查Job/deadline，原Solver未接受；公开Run读实际脱敏数学状态 |
| 数学CAS窗口首次发现deadline | 抛RunStopped后worker静默返回，Job一直running | deadline终态在事务退出后投影为failed/checkpoint sealed |
| 真实Registry precheck线程 | 实际handler执行1次，S3工具计数0 | precheck复制ContextVar，S3工具1次，无重复预留 |
| Registry内部handler线程 | handler看不到原RunBudget | 第二线程入口也复制上下文，实际handler收到原job_id |
| 初始计划要求重规划 | 公共路径只执行4个角色，停在META_DECIDE，未派发Meta/research | 有界调用既有controller.advance，12次实际角色调用累计同一S3 |

以上均以真实STAR bridge、InternModelAdapter/InternChatClient和Registry执行；只用有限scripted HTTP替换外部提供方，不使用fake pipeline或私有SQL种入数学状态。

## 同一Run的角色与资源证据

`tests/test_star_product_research_budget.py::test_meta_and_threaded_research_share_one_cumulative_job_ledger`从公共Job启动：

```text
Explore → Planner → Reasoner → StepVerifier(PROPOSE_REPLAN)
→ Meta(APPROVE_REPLAN) → Meta(delegate_research_task) → Researcher(线程)
→ Planner(v2) → Reasoner → StepVerifier → FinalGenerator → WholeVerifier
```

独立requests.post记录12次、S3 logical=12、HTTP=12、provider已知tokens=120；每个请求关联相同job_id。研究请求allowed_tools及tool_policy均为空，未新增账本。`test_registry_precheck_thread_charges_original_run_once`覆盖另一条6角色计划路径，实际Registry工具1次、S3工具1次，Verifier看到实际有限计算回执。SP-02的同会话Explore润色另覆盖explore_polish。

| 角色/动作 | 本票实际公共覆盖 | 不作的扩大声明 |
| --- | --- | --- |
| Explore / polish / whole review | 正常路径、retry、token拒绝、cancel和late usage | 不声明真实Intern数学能力 |
| Planner / Reasoner / StepVerifier / FinalGenerator | 六调用合法计划路径；工具超额时后续Verifier出站0 | 机制语义全面验收归SP-04/10 |
| Meta / research delegation | 原计划审查后实际批准重规划并生成研究任务 | 不宣称所有MetaGuidance故障分类通过 |
| 异步Researcher | 相同S3身份、12调用全链；cancel后usage累计70但后续Planner未发出 | 线程超时不等于撤销远端请求；全部研究语义归SP-07 |
| Registry precheck / handler | 两层线程同上下文；1工具额度下第二claim未执行；cancel后无Verifier | 不包含SP-09生成Python隔离器 |
| 禁用代码权限 | 真实server配置关闭local_code_tool、tool额度0时，合法六模型调用仍完成，实际工具0 | MetaGuidance实时切换reason_noncoding仍由SP-07公共触发验收；本票仅修正有效授权预算谓词，不冒称该切换已完成 |

S3 logical与attempt继续原身份；公开attempt增加脱敏`solver_call_id`关联，不新增logical动作。一个角色的两次HTTP retry共享logical_call_id和solver_call_id，其他角色身份不同；unknown在重启前就有原调用身份，不等响应后再伪造。

## 取消、期限与敏感性

所有取消/截止断言同时看真实出站及公开Run数学状态，不能只看Job终态。实际覆盖：

- 在途HTTP取消后迟到usage10可结算，已知部分预留释放，后续角色0次，数学phase不推进。
- 真实工具运行中取消，handler仅1次；late_result审计可查，数学停在STEP_VERIFY，Verifier0次。
- Researcher运行中取消，原7次HTTP均结算到70tokens，没有research_finished数学投影或下一个Planner。
- 模型限额4次时Meta未派发；token预留不足时真实HTTP=0；工具限额1时第二claim handler不执行。
- 数学CAS在SQLite写事务中与cancel竞争；迟到calls审计只能更新calls，不能回写业务phase/status。原S3的并发、重开、retry与unknown合同继续回归，不把本票当作SP-08恢复已通过。

对三个关键栅栏分别临时注入最小旁路，仅运行对应公共用例，再还原mock。每次均为**1个断言失败、0个执行错误**，不是通过更换预期获得PASS：

| 旁路 | 失败证据 |
| --- | --- |
| 移除precheck线程context传播 | 实际handler失去原Run，公共工具用例失败 |
| 跳过数学事务control predicate | canceled后Solver仍completed_llm_reviewed，公共Run断言失败 |
| HTTP token准入把预留量强制为0 | 实际发生未经额度允许的HTTP，零出站断言失败 |

ignored原始日志：`artifacts/sp03/sensitivity-*.log`、`sensitivity.json`。这些负例是故障注入，不是live/replay，也没有把原始payload提交。

## 检查与成本

真实API调用0、费用0。每个用例显式设置S3硬预算，有限scripted回复，等待上限8秒；研究任务timeout2秒。完整计划最大14logical/14HTTP，无生成Python执行；没有读取凭证或连接真实提供方。未触发的Challenge/Trace-Back完整机制不计作本票能力证据。

已执行的聚焦回归53项通过（30.387秒），随后调用身份/HTTP历史等24项通过（13.953秒）。`uv run python scripts/check.py --offline`在实现提交`1858fa2`通过：359项、237.238秒，workspace_contract/contract_test_seams/服务help/repository_check均PASS。之后仅补充未响应attempt的solver_call_id保留及禁用代码权限用例，聚焦3项通过（3.719秒）；未重复全量来掩盖先前结果。最终代码`cb56e52`执行必需产品发布检查`uv run python scripts/check_showcase_release.py`：`showcase_release=PASS`（含其自己的全量发现、Solver映射、baseline及入口检查）。

一次组合回归的旧`tests.test_tools`冷启动出现2个3秒子进程超时；立即独立重跑7项通过（1.783秒），未修改旧工具超时或放宽断言。Ruff全仓现有`tests/test_solver_harness_review_fixes.py`两处历史import-order问题未在本票顺手修改；本票所有变更文件Ruff通过。官方冻结文件、requirements及前端源码无变更。

最终diff检查通过，已包含集成`2abc642`。独立维护者复核共享谓词与数学事务检查未提出阻塞项。ignored日志绑定如下；不把日志哈希当作未来重复运行需字节相同的要求。

| 原始文件 | SHA-256 |
| --- | --- |
| `artifacts/sp03/offline.log` | `f31485ba42870a3386083e2545e9d487e4e4c4e8032f874a268b9638de7f3e9d` |
| `artifacts/sp03/release.log` | `4daf8e28a40c1fa01555cbbc6cde91459dd08f90cea5dc3f2a56696b445851c9` |
| `artifacts/sp03/sensitivity.json` | `2369abc1d053c4bb03ebbfaf6247df7b39f8dec28d75a4df6e785170d133b808` |

## 后续责任

SP-04/05/06/07负责机制本身与故障分支的完整产品验收；SP-08负责已完成响应/步骤的幂等续算、显式未知请求重试及原账本身份复用；SP-09负责真正生成Python、外部有界输出监督器及可核验计算产物；SP-10/11负责最终审查绑定与零调用Best-Effort。完整reference/best_effort当前仍拒绝启动，本票不改变已知缺口或声称#56整体完成。
