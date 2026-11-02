# SP-13 完整预设运行路径公共验收记录

日期：2026-10-24。分支 `feat/star-sp13-presets`：实现提交 `2d64792`（基点 `25aaca1`），随后合并集成分支 `showcase-star-product`（tip `344449b`，合并提交 `db11fd1`）。权威合同：`docs/engineering/star-product-sp13-preset-contract.md`；spec 为 #56（SP-AC-22/23/24 最终责任在 #69，本记录只交付可验证的完整预设执行路径，不代表 #69 或真实发布验收通过）。

接缝沿用公共边界：认证 ChatSession/Job HTTP、公共 resume/report/Evidence/capabilities、现有 Intern Adapter、S3 `RunBudgetLedger`、现有 ToolRegistry + `DockerPythonExecutor` 与 LangGraph checkpoint。scripted HTTP 均穿过真实 `InternModelAdapter`/`InternChatClient`（仅 patch 传输层 `llm_client.requests.post`）；Docker 预检与 `python_math` 工具为真实容器执行。未新建求解循环；官方冻结文件（`user_agent.py`、`implementations/`、`BASELINE.json`、`requirements.txt`）零改动（合并前后 diff 均不含）。

真实环境事实：Docker Linux engine 29.6.1 运行中；固定镜像 `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d` 经 `docker image inspect` 确认本机存在且 `Id` 完全一致；`DockerPythonExecutor` 只接受 64 位十六进制 digest（tag 与主机路径在构造时即 `star_python_image_id_invalid`），并在每次执行前核对镜像 `Id` 与锁定 policy/library labels（`mathagent.python.policy/sympy/numpy/mpmath` 等）。

## 一、逐项合同验收：触发 → 决策 → 实际动作 → 持久状态 → 用户结果

测试均位于 `tests/test_star_product_full_modes.py`（Docker 门控用例以 `MATHAGENT_TEST_PYTHON_IMAGE=sha256:fc91…73a2d` 真实执行，无 skip/xfail 计 PASS；`StarFullUnavailableTest` 两条无 Docker 依赖，始终执行）。

| 合同点 | 触发与决策 | 实际动作与持久状态 | 结果 |
| --- | --- | --- | --- |
| 1. 服务端显式开关 | 默认配置启动（无 `SHOWCASE_STAR_FULL_ENABLED`） | capabilities 中 `star_reference`/`star_best_effort` `enabled=false`、`missing_capabilities=["full_mode_not_enabled"]`；HTTP 请求两模式 503，模型 HTTP 0 | `test_default_server_flag_keeps_full_presets_closed` PASS |
| 1. HTTP 不能设置特性/镜像/验收状态 | `solver_mode=star_reference` 附 `solver_options={"skills": false}` | 入队前 400 `solver_options_unsupported`，零出站；镜像/预算/特性只能经服务端 config（`SHOWCASE_STAR_FULL_FEATURES/FULL_BUDGET/PYTHON_IMAGE_ID`），Job 创建无对应字段 | `test_full_options_and_disabled_review_reject_before_model` PASS |
| 2. 核心固定开启、缺项拒绝 | 九个核心特性逐一置 false 或整体删除（18 组合，服务端配置层构造） | 每组均在入队前 503 `star_prerequisites_unverified`，`missing_capabilities` 精确含 `feature:<name>`；活动 Job 列表为空、模型 HTTP 0；capabilities 同步显示 `enabled=false` 与同名缺口。不改名、不静默补回 | `test_each_core_feature_missing_or_disabled_rejects_before_enqueue` PASS |
| 3. 真实 Docker 预检（fail-closed） | 启动时与每次完整 Job 入队前，经现有 Registry 在独立预检 Run（`star-preflight-<uuid>`）与独立内存 S3 账本（max_tool_calls=1）执行固定无模型代码 `sympy.factor(x**2-1)` | 核对 executed、exit_code=0、stdout 恒等 `(x-1)*(x+1)`、cleanup_verified、`image` 与 `environment.image_id` 等于固定 digest；code/input/stdout/stderr/receipt 以内容寻址落盘于 `tool_artifacts/<run_id>/<sha256>`。探针不计入 Job 工具用量（Job 报告 tool_calls 只含用户题目动作） | `test_reference_runs_same_public_job_with_real_tool_and_whole_review` 内含真实预检；专用反例见下两行 |
| 3. 预检失败/unknown 关闭 | patch `DockerPythonExecutor.execute` 返回 `status=unavailable` 或 `unknown_outcome` | 两种情况入队前 503，`missing_capabilities` 含 `isolated_python_preflight_failed`，零出站、零活动 Job；legacy/受限不受影响 | `test_runtime_isolation_failure_after_startup_rejects_without_model_or_job` PASS |
| 3. 无隔离 Registry 关闭 | 服务端只给主机 Python Registry（无 `container_python_executor`） | 两完整模式 `missing_capabilities=["isolated_python_required",…]`，请求 503；legacy 同服务器正常完成且零出站 | `test_no_isolated_registry_keeps_full_closed_and_default_legacy_available` PASS |
| 3. 预检产物可核验 | 完整 Job 成功入队后读取 `/api/capabilities` | 完整模式记录含 `last_preflight={run_id,image_id,receipt_ref}`（仅准入状态，非验收标记）；经 `ToolArtifactStore.read` 校验 sha256 取回 receipt JSON：status=success、stdout 匹配、executed/cleanup_verified=true、image_id 为固定 digest | `test_capabilities_expose_verifiable_preflight_artifact_reference` PASS（本切片唯一真 RED→GREEN，见下节） |
| 4. 预算映射 | 完整 Job 默认预算 | 公共 report `limits`：48 model/48 http/8 tools；tokens 262144 与总 deadline 1100s 取自 `RunBudgetLimits` 默认；单次 Intern 180s/一次物理 attempt（pipeline 默认 `InternModelAdapter(client_timeout=180, client_retry=1)`）。`full_config` 固定 explore 2/challenge 5/replan 3/最终重写 2；计划 1..20 步沿用 `solver_harness/plan.py` 既有校验。`SHOWCASE_STAR_FULL_BUDGET` 仅服务端注入（BE 用例以 `max_model_calls=1` 实证） | reference 用例断言 48/48/8；BE 用例断言 1 次调用耗尽后零新增 PASS |
| 5. capabilities 准确区分 | 三种状态分别触发 | 默认关闭=`full_mode_not_enabled`；依赖缺失=`isolated_python_required`/`isolated_python_preflight_failed`/`model_configuration_unavailable`/`intern_s2_required`；运行可用=gaps 空。完整记录不含任何“能力已验收”布尔（断言无 `acceptance_passed`）。受限缺项按实际配置列出（如 `feature:skills`），不沿用历史静态 `FULL_MODE_GAPS`（已删除） | 上述各用例 + `test_full_flag_does_not_upgrade_limited_mode_or_default_legacy` PASS |
| 6. 完整参考全链 | 认证公共 Job `star_reference`（scripted 6 次模型回复） | 同一 Job/Run 完成 Explore→Plan→Step→真实 Docker `python_math` 工具→整题审查：report logical_calls=6、tool_calls=1（真实容器回执 executed/cleanup_verified、image=固定 digest）；S4 binding=`same_artifact`；首个出站含 `active_skill_ids` 含 exploration-protocol；Evidence mode=`star_reference`；Job 状态 succeeded | `test_reference_runs_same_public_job_with_real_tool_and_whole_review` PASS |
| 6. BE 硬预算后零新增 | `star_best_effort` 预算 1 次调用，Explore 成功后额度耗尽 | 纯选择交付 `final_response="2"`（`candidate_selected`），出站恰 1 次、tool_calls=0；两次 `candidate-replay` 逐字节一致且零派发 | `test_full_best_effort_selects_after_one_call_and_replays_without_dispatch` PASS |
| 6. BE deadline 终止 | 完整 BE 预算 runtime 1s，第二次调用被人为延迟 | deadline 到期后迟到回复仅结算用量，交付已提交候选、无整题 Verifier 出站（2 次出站、tool_calls=0、`candidate_selected`） | `test_full_best_effort_deadline_selects_only_previously_committed_candidate` PASS |
| 6. unknown 显式新身份重试 | 完整 reference 首调用 `requests.Timeout` | Job failed 进 needs_review；无决策 resume 409（含 `/api/runs/{id}/resume` 旁路 409）；带新 `new_call_id` resume 202 续算完成，原 deadline 保留、unresolved_attempts=1、总出站 4 | `test_full_unknown_call_requires_new_identity_and_preserves_shared_deadline` PASS |
| 边界：不升级受限/legacy | 同一服务器（full 开启）请求 `star_limited` 与默认无模式 | 受限仍按受限配置（缺项 `feature:skills` 实际列出）；legacy 正常完成；受限默认预算维持 3/3/0 或镜像 8/8/2 原值 | `test_full_flag_does_not_upgrade_limited_mode_or_default_legacy` PASS |

## 二、RED→GREEN 过程（如实记录）

- 工作树遗留的完整预设 WIP（`star_product_readiness.py`、modes/config/pipeline/runtime/workspace 等 16 文件与 10 条公共用例）在本切片开始时**未经任何验证**。本次首先在基点 `25aaca1` 以真实 Docker 镜像执行 `tests.test_star_product_full_modes`：10/10 直接 PASS。即：WIP 的实现行为已满足合同上述各点，本切片对其做的是复核、聚焦回归与如下补缺，不把它当作“已验证完成”跳过重跑。
- 真正的 RED 缺口一处：合同要求预检“留下可核验产物”，但探针的 `run_id/receipt_ref` 只存在于 pipeline 内部 `readiness` 字典，任何公共接口不可见，无法从产品面核验。先写公共失败断言（`test_capabilities_expose_verifiable_preflight_artifact_reference`：经 `/api/capabilities` 取 `last_preflight` 并用 `ToolArtifactStore.read` 按 sha256 取回 receipt JSON 核对 status/stdout/executed/cleanup_verified/image_id）——RED 确认（`last_preflight` 为 None）。最小实现：`showcase/star_product_modes.py::capabilities` 在完整模式记录附加缓存的 `last_preflight={run_id,image_id,receipt_ref}`（仅准入状态观察，receipt 为可独立核验字节）——GREEN。
- 其余用例对照合同逐项核对后无需新实现：核心缺项拒绝、fail-closed 反例、预算映射、BE 零调用与回放、unknown 新身份重试在 WIP 中已有断言与实现，本次以真实执行确认。

## 三、与集成 tip 的合并与门禁重跑

`git merge showcase-star-product`（`344449b`，含 SP-12 Workbench 生命周期与恢复缺口四切片）**无文本冲突**，自动合并后逐文件核对重叠处双方语义共存：

- `showcase/evidence.py`：本切片 `_mode` 白名单新增 `star_reference`/`star_best_effort` 与集成的 `stream_metrics` 计数字段/receipt 脱敏并存（不同 hunk）。
- `showcase/star_product_pipeline.py`：完整预设 `full_config`/`full_gaps`/`budget_for_mode` 与集成的 `projection` 附加 `progress_summary` 并存。
- `showcase/star_product_recovery.py`：本切片 `STAR_MODES` 扩展与集成的幻影 revision/任务不匹配 409 守卫并存。
- `workspace.py`/`run_service.py`/`run_control.py`/`product_control.py`/`star_product_hints.py`：集成分支未改动这些文件，仅本切片的 `STAR_MODES`/`BEST_EFFORT_MODES` 统一替换生效。

合并后聚焦与相关门禁（全部真实执行，2026-10-24）：

| 命令 | 结果 |
| --- | --- |
| `MATHAGENT_TEST_PYTHON_IMAGE=sha256:fc91…73a2d uv run python -m unittest tests.test_star_product_full_modes tests.test_star_product_jobs tests.test_star_product_runtime tests.test_star_product_python` | PASS，22 项（full_modes 11 + jobs/runtime 8 + python 3，Docker 用例真实执行，无 skip），43.2 秒 |
| `uv run python -m unittest tests.test_star_product_recovery tests.test_star_product_streaming_recovery tests.test_star_product_summary tests.test_star_product_candidate_counterexamples tests.test_star_product_best_effort tests.test_star_product_final_binding tests.test_star_product_control tests.test_star_product_budget` | PASS，62 项，96.8 秒 |
| `uv run python -m unittest tests.test_flask_showcase tests.test_star_product_counterexample tests.test_star_product_challenge tests.test_star_product_guidance tests.test_star_product_skill_context` | PASS，40 项，62.7 秒 |
| `uv run python -m unittest discover -s tests -p "test_evidence_history.py"` | PASS，2 项 |
| `uv run ruff check showcase tests` | 本切片触碰文件全部通过；仅存 2 个 I001 于 `tests/test_solver_harness_review_fixes.py`，该文件在集成 tip `344449b` 上即如此且本分支未改动（预存，非本切片引入） |

## 四、边界与未声明事项

- 本记录只证明完整预设运行路径的公共准入、真实隔离预检、预算映射与受控执行；模型回复仍为 scripted/故障注入，不是 live 数学效果，也不是 SP-AC-24 真实 Intern 批次。
- 未执行全量 offline/release、前端与依赖门禁（属 #69 最终门禁，非本切片）；未调用真实 Intern 云端；未 push、未关闭 issue（`Refs: #69`，由父流程在最终门禁+真实批次后关闭）。
- 受限与 legacy 行为回归由上表第二、三栏套件覆盖；受限默认预算维持原值未变。

## 五、终审修复轮（2026-10-24，分支 `fix/star-final-review`，基点 `ef92490`）

两轴最终审查（Spec 轴 4 项必改 + Standards 轴 6 项判断题）由本轮统一修复；行为修复 `f107d78` 与纯重构 `c15cd51`、证据补记分开提交。官方冻结文件与未跟踪文件零改动。

### Spec 轴（行为变化，全部先 RED 后 GREEN）

| 发现 | RED 测试（`tests/test_star_product_full_modes.py`） | 修复 |
| --- | --- | --- |
| reference 配置强制 `candidate_registry: True` 违反"reference 核心=恰 9 项" | `test_reference_preset_is_exactly_nine_core_features_and_registry_inactive`：RED 时公共 `solver.config_hash` 不等于 9 核心预期配置的哈希（生效 features 含 candidate_registry/best_effort） | `StarProductPipeline.run` 仅对非 reference 模式附加 `candidate_registry`、仅 Best-Effort 模式附加 `best_effort`；reference 运行注册表不激活（公共 `candidate_history=[]`、`best_effort=None`）。`star_limited`/`star_limited_best_effort` 保持 SP-11 已验收行为不变；reference 恢复/S4 路径核对后不依赖注册表（`run_best_effort` 特性关闭时为 no-op） |
| 无 STAR pipeline 时受限模式 `core_gaps({})` 列出全部 9+1 缺口 | `test_capabilities_without_star_pipeline_do_not_enumerate_limited_feature_gaps`：RED 时 `star_limited.missing_capabilities` 为 10 项特性缺口 | `mode_identity` 无 preset 配置（pipeline 为 None）时受限模式表达 `["star_not_enabled"]`（与 validate_mode 同名拒绝原因一致），不逐项枚举；有 pipeline 时仍按实际配置列（既有用例覆盖 `feature:skills` 等） |
| 预检内存 `RunBudgetLedger` finally close，S3 计量不可事后审计 | `test_capabilities_expose_verifiable_preflight_budget_ledger`：RED 时 `last_preflight` 无 `budget_ref` | 探针把账本序列化（`{run_id, summary, actions}`，含 limits `max_tool_calls=1` 与实际 tool 用量）以内容寻址 JSON（kind=`preflight_budget`，call_id=`isolation-probe`）随 receipt 落盘于同一 `tool_artifacts/<run_id>/<sha256>`；capabilities 的 `last_preflight` 增加 `budget_ref`，经 `ToolArtifactStore.read` 按 sha256 校验取回；探针异常路径补脱敏日志（仅异常类型名，无凭证/prompt） |
| 合同镜像指纹未在代码内锚定 | `test_contract_python_image_id_is_pinned_in_code`：RED 时 `CONTRACT_PYTHON_IMAGE_ID` 不存在（ImportError） | `showcase/star_product_runtime.py` 增加代码内固定常量 `CONTRACT_PYTHON_IMAGE_ID = sha256:fc913659…73a2d`，不依赖 Docker 的断言测试直接核对。**边界（如实记录）**：该常量仅锚定合同值，不作为运行时默认接线——镜像仍必须由操作者经 `SHOWCASE_STAR_PYTHON_IMAGE_ID` 显式提供（若把指纹设为隐式默认，会让未配置镜像的服务器自动构造容器执行并改变受限默认预算，破坏 SP-09/SP-13 显式 opt-in 与 fail-closed 语义，并迫使离线门禁起 Docker）。Docker 用例保留 `skipUnless(MATHAGENT_TEST_PYTHON_IMAGE)` 门控 |

### Standards 轴（行为保持的重构，`c15cd51`）

- a（收敛）：`star_product_modes` 的 validate 5 元素字面量与 capabilities 模式元组统一由 `MODE_ORDER`/`STAR_MODES` 单一来源派生（展示顺序固定，不随 frozenset 迭代漂移）；`evidence._mode` 白名单改由 `STAR_MODES` 派生。前端 zod enum（`reports.schemas.ts`）**保持现状**：前后端无共享代码生成来源，改写 TS schema 只会引入新的漂移面；当前两端枚举一致且后端已稳定。
- b：`run_service.py` 中重复 3 次的 `(snapshot.get("result") or {}).get("solver_mode") in STAR_MODES` 收敛为局部变量 `result`。
- c（部分采纳）：`intern_port.py` 非流式与流式路径重复的 invocation record 字典与请求 metadata 组装提取为纯数据 helper `_invocation_record`/`_request_metadata`；计量与流式协议路径未动。`adapters.py` 的流式 attempt envelope 为单处使用且与计量交织，**不强行提取**（提取只增加间接层并触及高风险流式路径）。
- d：pipeline 新增显式小方法 `dependency_gaps()`/`readiness_state()`/`preset_config()`，`full_gaps` 不再调用 `adapter._get_client()`（adapter 暴露 `ensure_configured()`），`star_product_modes` 不再 `getattr(pipeline, ...)`；返回值与 fail-closed 语义逐分支保持。
- e：`star_product_recovery.py` 的 `import hashlib` 移至模块顶部；`star_product_readiness.py` 裸 except 的脱敏日志已随 Spec#3 修复提交（仓库此前无 logger 先例，采用标准库 `logging.getLogger(__name__)`，仅记异常类型名，沿用 `AdapterError` 类别+类型名的脱敏惯例）。
- f：`tests/star_recovery_worker.py` 的 `TRACE_WINDOWS`/`STREAM_WINDOWS` 常量移至 `config()` 之前（纯移动）。
- g（构造期真实 Docker 探针）：合同覆盖，未改动。

### 终审修复轮聚焦重跑（真实执行，Docker 用例无 skip）

| 命令 | 结果 |
| --- | --- |
| `MATHAGENT_TEST_PYTHON_IMAGE=sha256:fc91…73a2d uv run python -m unittest tests.test_star_product_full_modes tests.test_star_product_jobs tests.test_star_product_recovery tests.test_star_product_streaming_recovery tests.test_star_product_summary tests.test_star_product_best_effort` | PASS，65 项，121.7 秒（full_modes 15 项含 4 条新增 RED→GREEN 用例） |
| `uv run python -m unittest tests.test_star_product_gates tests.test_star_product_runtime tests.test_star_product_control tests.test_star_product_budget tests.test_star_product_candidate_counterexamples tests.test_adapters tests.test_solver_harness_streaming` | PASS，31 项 |
| `uv run python -m unittest tests.test_graph_service tests.test_flask_showcase tests.test_worker_death_attempt tests.test_star_product_guidance tests.test_campaign_live_contract` | PASS，33 项 |
| `uv run python -m unittest discover -s tests -p "test_evidence_history.py"` / `-p "test_sync_evidence.py"` | 各 PASS，2 项 |
| `uv run ruff check showcase tests` | 本轮触碰文件全部通过；仅存 2 个 I001 于 `tests/test_solver_harness_review_fixes.py`（集成 tip `ef92490` 上即预存，本分支未改动该文件） |

本轮仍未执行全量门禁与真实 Intern 批次（属 #69）；未 push、未关闭 issue。
