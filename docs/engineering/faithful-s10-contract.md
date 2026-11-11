# S10/F4/F5 工程验收合同

日期：2026-11-11（Asia/Shanghai）。状态：S10/F4/F5 工程退出通过（`engineering-preview`）；下阶段可按 #146 的 F6–F8 合同推进。真实 provider、自然题、容量/SLA 和独立数学效果保持未验证。

## 本轮完整退出实施计划

目标为 #130 地图的 S10 工程退出，而非单个记忆切片通过。当前工作树已接入 F4 原生 Solver checkpoint 子状态、持久暂停/恢复、公开失败来源与分臂预算；F5 已接入 Population Memory 同意、来源链、当前 Run advisory/APRS 成本，以及 Goal Cache 身份复核、漂移和用户控制。每个新增缺口均有先失败后修复的验收；135 项非 Docker S10 测试、前端完整检查及 9 项 F4/F5 浏览器用例通过。唯一成功最终门禁为 `faithful-s10-20261111-02`：6/6 阶段，1821 项、0 failure/error、42 skip，`source_changed=false`。首轮失败及修复经过见验收报告；跳过项不计通过。真实 provider、自然题、容量/SLA、独立数学效果仍单独标为未验证。

F4 原生动作合同：仅对显式暂停的串行 `STEP_EXECUTE` checkpoint 执行已登记的 `reasoning_method` 动作（仅一个受控 `method_id` 不同），两份隔离 SQLite 子状态继承完全相同的父数学身份、历史与配置，新调用/会话由 branch ID 隔离。原生 `run_step` 的报告先由分支 Verifier 裁决，再由同一配置的 Verifier 以新调用身份复核持久报告；复核是独立调用，不代表独立服务或外部审查。效果只计当前有效根义务增量。每次持久子状态独立保存；父状态不合并任何分臂成果。父账本对称预留调用、HTTP、token、工具和时间，并保留收尾 floor、原 deadline 及 unknown holds。读取时重新核对分臂当前证据、两次 Verifier 调用和实际 Reasoner/Verifier 账目；多 pair 保留全部已启动分母，比较身份或策略不同不混算均值，未预登记独立样本及区间方法时只提供描述统计与离线反馈待审标记，不在线修改当前策略。以上仍需对应公共入口、故障与恢复、审阅 UI 及最终门禁证明后才能验收。

权威要求：[F4 #150](https://github.com/RUSS0718/MathAgent/issues/150)、[F5 #151](https://github.com/RUSS0718/MathAgent/issues/151)、[同源干预决议 #142](https://github.com/RUSS0718/MathAgent/issues/142#issuecomment-6702797011)、[记忆决议 #143](https://github.com/RUSS0718/MathAgent/issues/143#issuecomment-6702958359)、[阶段门禁 #144](https://github.com/RUSS0718/MathAgent/issues/144#issuecomment-6703147321)。F2/S08 与 F3/S09 的工程退出见[文档索引](../README.md)。

实施起点：`mathagent-faithful` 的 `f7d9c530978fbcbf453e06ba0a24500cb9593721`，指定集成工作树。旧 `PairedRunner` 的双独立 Run 配对不能满足 F4 的运行中同源分叉；其结果不得写为 AC17 通过。S09 的形式化结果已具备真实固定 Lean 环境证据，但普通答案、L1 或模型审查均不得进入 F5 的形式缓存。

| 合同 | 公共入口 | 持久状态及关键断言 | 最小验证 | 当前结果 |
| --- | --- | --- | --- | --- |
| #150 AC16 失败假设 | `/api/agent/jobs/{job_id}/interventions/hypotheses` 与同 Job 投影 | 仅接受公开 Solver 事件别名；校验真实 `step_reviewed` 失败、revision 和原始 root obligation。诊断字段限 `event_type/verdict`，额外自述字段拒绝；unknown/传输类失败不登记 | `tests.test_faithful_s10_intervention_control_api.FaithfulInterventionControlAPITest.test_hypothesis_requires_owned_source_event_and_structured_failure`；`tests.test_faithful_s10_intervention_product_path.FaithfulInterventionProductPathTest.test_hypothesis_diagnostic_is_bound_to_public_source_event` | 已实现并通过公共入口验收；来源为本 Job 权威 Solver 事件，不把调用方附加 JSON 当作证据。 |
| #150 AC17 同源原生分叉 | 暂停 Job 的 `/pause`、`/hypotheses`、`/actions`、`/pairs`、`/pairs/{id}/execute`、`/reports`、`/resume` | 两臂从同 revision/hash/problem/config 克隆，branch/call/session 身份隔离；仅变更一个已登记 `method_id`；原生 `run_step` 后由 Verifier 裁决，再以新逻辑调用身份复核持久报告；父 checkpoint 保持不变，显式恢复仍使用原 Run | `tests.test_faithful_s10_intervention_product_path.FaithfulInterventionProductPathTest.test_public_api_runs_native_pair_projects_effect_and_resumes_parent`；native checkpoint/fault/recovery tests | 工程路径已实现并通过受控模型/Verifier fixture；证明接口与账本流程，不证明真实 provider 行为或数学收益。 |
| #150 AC17 预算和顺序 | 父 `RunBudgetLedger`、原生 `NativeArmLedger` | 可复现 seed/order；逻辑调用、HTTP、token ceiling、工具与时间的对称预留/逐臂结算；deadline、closing floor、unknown holds 保留；报告读取不阻塞结算 | `tests.test_faithful_s10_native_budget`、`tests.test_faithful_s10_native_faults`、`tests.test_faithful_s10_pair_recovery`、原生公共路径重复 10 次 | 已实现并通过定向预算、故障、恢复和高频报告读取回归；并发容量与生产 SLA 未标定。 |
| #150 AC18 效果、恢复与证据边界 | `/reports` 持久 pair 投影及父 Run `/resume` | started pair 保留分母；unknown/incomplete 不插补；单对只给描述差值、不报区间、不更新 policy；UI 分列显示分支裁决、新调用身份复核裁决及持久子状态一致性；分臂证据不并入父 Run | execution/recovery/product-path tests；`faithful-intervention.spec.ts` | 每臂两次 Verifier 调用均须 ACCEPT、复核调用绑定同臂父账本且子状态一致才可评估；未知、拒绝或身份不符保持分母但不产生效果。复核使用当前配置的 Verifier 调用身份，不宣称外部独立服务；不提供 branch-to-parent 证据合并，父 Run 显式恢复至原 checkpoint。 |
| #151 AC21 Run Memory | `--faithful-memory-review` 下 `/api/agent/jobs/{job_id}/memory` | 从权威 Solver snapshot 和预算只读投影；有效证据保留 `result_id/category/evidence_level`；不建第二份可清理副本 | `tests.test_faithful_s10_run_memory`；前端 `faithful-memory.test.ts` 和浏览器 spec | 已实现并通过。Run Memory 是即时只读投影；清理由 Run/Job 保留策略负责，不通过删除权威状态实现。 |
| #151 AC21 Population Memory 与 APRS | `/api/sessions/{session_id}/population-memory`；`/memory/{kind}/{scope_id}`；独立 `/injection` 控制 | 会话显式同意；终态观察幂等捕获；同域、当前身份、导入来源链与祖先撤销校验；advisory 内容进入当前 Solver/Verifier 上下文但不进入 proof/verified_gain/policy；APRS 记录 route memory hits 和来源成本；成本按 versioned UTF-8 字节估算，unknown 保持 unknown。成功路线必须唯一满足 `completed + final_answer_bound` | `tests.test_faithful_s10_memory_*`、`tests.test_faithful_s10_route_observations`；前端 memory unit/browser tests | 离线工程合同已覆盖并通过。只将 terminal route transition 中绑定当前交付的唯一路线记录为 success；其他 completed 路线和多重/缺失绑定保持 unknown。观察、控制及审计读取均为 `no-store`。token 数是字节估算，非 provider 实测用量；导入观察仍须当前 Run 重审；不证明路线命中率或数学收益。 |
| #151 AC22 Goal Cache | 显式会话启用后的正式 Lean 尝试；`/api/sessions/{session_id}/goal-cache` | 身份键覆盖目标/假设/声明/import/环境/template/公理/spec/证明身份；只收可信 L2+，命中再次执行当前 Lean；L3 admission 的存储上限仍为 L2；身份漂移、Lean 拒绝/unknown 和清理形成可见 stale/invalidated 原因及墓碑 | identity/drift/control tests；`test_real_l2_receipt_survives_restart_only_after_current_lean_recheck`；`test_real_lean_admission_and_current_recheck_use_one_execution_each`；`test_real_l3_lean_and_independent_review_admit_with_l2_ceiling` | 当前最终门禁中，上述 3 个固定 Lean L2/L3 集成用例未列入 42 项 skip，且全仓测试 0 failure/error，故均执行并通过。身份漂移矩阵拒绝旧 receipt；该矩阵不代表每种漂移都执行真实 Lean 重跑。命中当前仍重跑 Lean，不宣称计算复用收益。 |
| #151 AC22 用户控制与读取 | 已认证、CSRF 保护的 session GET/PUT/DELETE | 同用户/会话隔离；公开来源 Run/Attempt/等级、拒绝理由、状态和审计墓碑；清理不删除 Run ledger；GET `Cache-Control: no-store` | `tests.test_faithful_s10_goal_cache_api`、`tests.test_faithful_s10_goal_cache_controls`；浏览器 Goal Cache spec（含移动布局） | 已实现并通过公共 API、浏览器和响应缓存头回归；尚无外部生产后端部署验收。 |
| #146 / #130 S10 阶段退出 | Job、Report、Evidence、F4/F5 桌面与移动界面、唯一最终门禁 | baseline/default budget 不变；旧 Run 不迁移；源码 manifest、命令、跳过项、分层证据完整归档 | 135 项非 Docker S10 回归、46 项前端单测/构建、9 项 F4/F5 浏览器用例、最终双轴审查、`run_final_gate.py` | S10 `engineering-preview` 退出通过。门禁 02 为 6/6、1821 项 / 0 failure / 0 error / 42 skip、`source_changed=false`；01 的前端并发竞态失败保留并已修复。真实 provider、自然题、容量/SLA、独立数学效果及 42 项 skip 不作为通过证据。下一阶段按 #146 的 F6–F8 合同推进；#130 已追加本次路线进展评论（issuecomment-6784751677），#146/#150/#151 未关闭或评论，S10 源码仍未提交。 |

本轮 AC16 诊断字段、SQLite 报告读取竞争、Goal Cache/Memory 缓存头、Run Memory 公开 evidence schema、暂停状态刷新、单条路线交付绑定和分支 verdict 命名均先以失败验收或重复运行复现，再最小修复。135 项非 Docker S10 回归、完整前端 46 项、F4/F5 浏览器 9 项、快速工程检查及相关 Ruff 均通过。F4 复核调用身份与 obligation evidence 及父账本 ID 一致，并验证复核请求绑定确切分支报告；账本 ID 与报告内容篡改均被拒绝。门禁 01 的前端并发失败已通过串行测试文件调度修复，成功门禁 02 冻结源码 `source_hash=421b9face1da7e8aa687a67ceecc4ff31fd0db495b24ebe707136ce1398e71c6`，6/6 阶段通过，1821 项、0 failure、0 error、42 skip，`source_changed=false`。门禁后的更改仅为本合同、验收记录和文档索引同步，未改变该门禁覆盖的代码。真实 provider、自然题、容量/SLA 和独立数学效果仍未验证；受控 fixture、单 pair 描述差值和工程门禁不构成能力提升证据。F6–F8 与完整并发 #156 按各自合同继续；#130 已发布路线进展评论，#146/#150/#151 GitHub issue 未改动或关闭，源码未提交。

路线观察增量合同：终态捕获在同一事务中为有身份和前沿摘要的每条串行路线保存独立观察，沿用显式同意、作用域和 Run 幂等边界；未知请求或路线 unknown 不得成为成功，只有完成且整题交付已绑定的路线可记为成功。记录路线身份、前沿摘要、状态、来源及其创建时的图、计划、尝试和策略版本；失败原因按受控集合记录，集合外为 `other`。没有可核实的路线成本时保持未知，不能填入整 Run 成本。观察不进入 APRS 分数、证明或策略。验证多路线、未知、禁用、重复捕获与回滚；本切片不宣称路线成本、路线命中或 F5 阶段完成。

路线观察工作树检查（2026-11-10，基于 `1a81f898baf270ca89360026cbee7fd064e1ac7b` 的未提交改动）：新增测试先因缺少路线记录失败；补充公开 Job 的串行路线终态及绑定检查时，首轮因测试 SQLite 连接未关闭导致 Windows 临时目录清理失败，关闭连接后复跑通过。`tests.test_faithful_s10_route_observations` 与记忆、S08 路线相关回归共 43 项通过，修改文件 Ruff 通过，快速工程检查通过。此记录不代表干净源码 SHA 的阶段验收；路线级成本、当前 Run 路线匹配与 APRS 集成仍未完成。

记忆作用域禁用测试原先使用不可注入样本且删除控制行，未实际验证禁用；改为先断言有效样本可注入，失败复现后显式写入 `enabled=0`，随上述回归通过。

### 显式导入来源链修复（2026-11-10）

依据 #130 开发地图转交的 #151/AC21 作用域与导入合同，本切片修复原始来源 Run 与中间容器身份混淆：Run A → Run B → Population 及跨会话 Population 连续导入均须可见并可用于同域 advisory。注入逐层校验用户、会话、作用域、active 状态、scope 控制、导入者及观察/来源内容一致性，最终回溯到所属会话的终态来源 Run；祖先清理、禁用、所有者变化或内容篡改后拒绝注入，重复来源环拒绝。显式导入不提升观察权限，仍需当前 Run 重审。历史观察保留的视图与当前可注入性分别处理。

验收源码基点为 `1a81f898baf270ca89360026cbee7fd064e1ac7b` 的未提交工作树。新增 `tests.test_faithful_s10_memory_import_chain` 先复现合法链被拒绝及跨会话 Population 来源视图为空；最小修复后 6 项通过，记忆与路线相关回归 56 项通过、0 skip。公共 API 测试夹具最初因未结束前一 Job 触发 `active_job_conflict`，调整夹具后通过。修改文件 Ruff、快速工程检查及 diff 格式检查通过；本切片不构成 #151 或 S10 阶段退出。

双轴审查：规范轴无确认问题；规格轴指出祖先撤销后管理列表仍可查看历史副本。该行为按本切片合同保留，管理列表的 `observations_only` 不表示可注入；原始非终态观察也可供历史管理。新增公共断言确认祖先清理后历史副本仍可见而注入为空，6 项专项复跑通过。Run 范围清理不连带清除其他 scope 的已导入副本；如需删除目标副本须清理目标 scope。两种行为不得混称为当前有效证明。

```powershell
uv run python scripts/run_unittest_report.py --expect-count 56 tests.test_faithful_s10_memory_core tests.test_faithful_s10_memory_capture tests.test_faithful_s10_memory_context tests.test_faithful_s10_memory_control_api tests.test_faithful_s10_memory_injection tests.test_faithful_s10_memory_injection_api tests.test_faithful_s10_memory_pipeline tests.test_faithful_s10_memory_import_chain tests.test_faithful_s10_route_observations tests.test_faithful_s08_routes tests.test_faithful_route_projection
uv run ruff check showcase/faithful_memory_control_api.py showcase/solver_harness/faithful_memory_injection.py tests/test_faithful_s10_memory_import_chain.py
uv run python scripts/check_fast.py
```
