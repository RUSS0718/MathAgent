# #191 自然 Intake 依赖表达与公共验收合同

日期：2026-11-17。当前：live04 S2/D 自然正向验收已通过，CHALLENGE 沿受控公共证据；退出记录832b33f已推送，#191已关闭并重读确认。
初始基点 `975560a9bd9c546d7e7b1ae7e8133071c3a41cf4`，工作树 `D:/project/mathagent-191`，分支 `feat/natural-intake-191`，初始干净。继承当前模型，不覆盖设置；不猜测具体型号。

## 当前状态

自然源码 `aac4cf6498cefb9b8761976f479b90e52303537f`：S2/D 自然正向验收通过，CHALLENGE 仅沿 I191-3 既有受控覆盖，建议主控审核 #191 退出；GitHub 关票待主控提交。实际因果链、测量、I191 兑现所需证据见[本票验收](../evals/natural-intake-191-20261117.md)，跨票状态见[#189 映射](../evals/dependency-routing-189-20261117.md)。以下保留实施时范围、验收要求和准备合同；NOT_RUN、待执行及独占时序均为历史状态。

## 历史实施范围与已确认缺口

采用仓库外 `191-natural-intake-design-candidate-20261117.md` 及已提交的 [#190 设计](dependency-routing-189-design.md)、[#190 交接](dependency-routing-190-handoff.md)。#190 已由主控验收 closed，本票不重写其路由、controller、恢复、配置、adapter、预算或来源合同。

实际 Intake 已说“依赖是逻辑前提”，schema 已有 root.prerequisite_ids / aux.dependencies，但 system 指令尚未明确把自然题中的“使用前一结果”映射到这两个字段。最小修改仅在 `showcase/solver_harness/intern_instructions.py` 的 Intake 段增加字段映射、声明 ID 与无依赖保护。该文件本票独占至提交/集成；不复制指令到 roles.py，不新增分类器，不强制每题 Planner。

Planner 的 objective_dependencies、owner 顺序与不同 WorkUnit、Reasoner 的 current_goal/valid_sources/异议及独立送审语义已充分；不为本票改动。Harness.dispatch 注入当前 spec/version，再由 InternModelPort 构造实际 system + user messages；测试必须观察 provider HTTP outbound messages，不能仅观察中间请求字典。

写范围：上述指令文件、独立 `tests/test_natural_intake_job_191.py`、本票合同/证据。复用原 fixture，禁止修改全局 fixture。不动 root/README/用户未跟踪合同，不读取 tests/test.md，不回退他人修改。所有 Python 用 `uv run --no-sync` 和共享 UV_PROJECT_ENVIRONMENT；不启动真实 provider/live/服务、整仓或浏览器。

## 执行与可验证退出条件

| 编号 | 切片 / 公共接缝 | 验证与证据 |
| --- | --- | --- |
| I191-1 | POST Job 的题干输入经受控 HTTP Intake 响应走真实 Job；检查实际 system 消息 | 先留失败：缺自然依赖到 root.prerequisite_ids / auxiliary.dependencies 的指引；最小补充后转绿。不把受控响应当自然识别证据。 |
| I191-2 | 无依赖双根及解释/完整性 | 同一实际 Intake 指令明确不从难度、长度、解释或列出全部解制造依赖；无依赖规格仍 Explore→whole review，独立对照。 |
| I191-3 | Planner→WorkUnit→Reasoner→StepVerifier | ACCEPT 门控引用 #190 公共顺序用例与最终证据；具体 CHALLENGE 影响后续请求优先复用 tests/test_star_product_challenge.py，若依赖后继未执行缺关键反例，仅补一个受控公共用例。不得修改生产状态机来造红。 |
| I191-4 | 同一 Job/Run / sources / unknown / budget | 复跑 #190 聚焦公共 Job 合同及受影响角色提示回归；公共 GET 不增派发。旧 Run/unknown/预算沿 #190 已有证据，不重做全套恢复测试。 |
| I191-5 | S/D 真实自然运行准备 | 复用现有 showcase_cli.py，忽略目录准备独立题干文件/摘要与命令入口；主控接管真正 prereg、冻结配置和唯一运行/监控。自然结果一律 NOT_RUN，D 未识别依赖为 not_triggered，不补 spec 或计划。 |

先提交本合同 → 一个公共失败断言 → 最小指令修改 → 聚焦红绿与相关回归 → diff 规范/规格两轴自查 → 中文规范提交 → 在本 worktree 合并 dependency-routing-189 最新 tip 并检查干净。集成回 root 由主控处理，不在其工作树写入。

本次只完成受控代码切片与运行准备，不构成 #191 真实验收或 #189 阶段退出；整仓、浏览器与独立阶段门禁由主控安排。实现若只需原有充分约束可零生产修改；不得为 ticket 扩大范围。新测试中的固定响应不取自 S/D 参考答案。

## 真实运行与隔离交接

S/D 来源：`C:/Users/CQX/.codex/tmp/189-natural-cases-preregister-candidate-20261117.md` 的两个原样题干；题集、答案、raw、运行配置/凭证均不得提交。运行输入仅题干，参考答案只由主控独立人工核对，不进入任何模型、验证器、Job 或附件。

输入与运行材料放被忽略的 `artifacts/issue191/`；docs 只记录题号、题干 SHA256、命令和证据入口。实际执行使用现有 CLI 的 session create、job submit、status/events/report；不新造通用运行器，不复用测试 reviewer 注入或 full_gaps patch。独立 Job/Run，服务端既有自主入口采用 #190 冻结策略与 #192 集成后的容量，具体预算/cap 不猜测，不覆盖模型。

登记由主控 accepted 后填写：源码 SHA/差异、输入摘要、可信配置版本/冻结 policy、原预算/deadline、Job/Run、实际 Attempt/roles/duration、spec/Plan/WorkUnit/step 关系、StepVerifier 裁决与下一动作、最终绑定及独立整题审查和人工数学核对。自然 D 未识别依赖记 not_triggered；失败/耗尽/unknown 按实际状态另记，不补 spec/plan、不为凑角色重跑。#193 复用同一组证据。

共享文件顺序：#191 提交并由主控集成后，#192 才编辑 intern_instructions.py；#191 不修改其 cap/adapter/stream 接缝。全程不协调催促其他 owner。

执行结果与命令见 [验收与 HANDOFF](../evals/natural-intake-191-20261117.md)。合入的主控交接已记自然题 registered_not_run；本票只准备可核对摘要的输入物料，不另建正式 prereg、不替代主控登记。
