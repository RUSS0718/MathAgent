# 目标依赖路由：#189 上下文与 #190 最小实施合同

2026-11-17；集成基点 `1307aab40b8788cc408ef65fc94dfc7f2b1dc1f8`。
本设计先于产品实现提交；验收结果另见交接记录。仅显式 Showcase 串行自主路径，official/baseline 不变。

## 要求与分工

权威要求：[父规格 #189](https://github.com/RUSS0718/MathAgent/issues/189)、
[#190](https://github.com/RUSS0718/MathAgent/issues/190)、
[#191](https://github.com/RUSS0718/MathAgent/issues/191)、
[#192](https://github.com/RUSS0718/MathAgent/issues/192)、
[#193](https://github.com/RUSS0718/MathAgent/issues/193)。这些链接的全要求持续适用，以下是分工而非删减。
设计依据为已保存的 Issue 正文和审阅候选，不依赖 root 未跟踪合同。

- #189：显式目标依赖先规划，无依赖一次有界探索；独立整题审查、原预算/deadline/来源/Unknown Outcome 边界，真实事件解释路线，不以角色数证明收益。
- #190：确认依赖的 ProblemSpec 经真实 Planner→有序 WorkUnit→Reasoner→Step Verifier；SOLVED 不能短路；无依赖双根可直接整题审查；旧 Run/official 无新增调用。
- #191：登记自然题、真实 Intake/模型、步骤裁决的实际影响与数学核对。#190 仅受控 HTTP 公共 Job，不重复 provider 派发。
- #192：首次 Explore 语义轮次、独立输出 cap、已知不完整/截断与 unknown 区分；cap 数值未决，旧样本 usage 未知，字节/时间不换算 token。后续独立容量 policy 只冻结新 Run，不迁移 #190 已建 Run。
- #193：在 #191/#192 后组合验收、真实角色与普通用户文案，内部 ID/用量/hash 不进普通界面。

## 最小字段和控制合同

可信 faithful JSON 可选 `routing_policy_version: "objective-dependency-routing-v1"`，映射
`SHOWCASE_STAR_ROUTING_POLICY_VERSION`；不接受 HTTP 用户覆写。缺席关闭，未知版本/null/false 拒绝。
启用须有 adaptive_solving、problem_spec、auto_problem_spec、star_routing、final_generation、final_solution_review 和 strict 模式；population/配对不自动启用。
仅新 Run create 前冻结 `routing_policy = {name: "objective-dependency-routing", version: 1}`；恢复不回填。

配置规范化保留字段，config hash 严格比较：关闭不输出新键，不修改 CORE_FEATURES 默认集合。
Pipeline 构造执行 Harness 前按持久 policy 只还原这个新增配置键；其他配置 hash 继续严格核验。
A 无 adaptive 旧 Run、B adaptive185/resource/search 但无新 policy 旧 Run、C 冻结新 policy Run 分别保持语义；
旧 hash 不改，新 policy 进入新 hash。预算、预留、deadline、call lineage 不重置；不支持版本停止，不降级。

服务端统一资格函数消费当前已规范化 ProblemSpec：任一 root.prerequisite_ids 或 aux.dependencies 非空即需规划。
复用 schema/引用/环/WorkUnit 校验，不按根数量或文本猜依赖，不新增状态机。
入口和恢复在控制/unknown 守卫之后、首次深度求解及直接整题审查之前复评当前 specification_version。
已有当前合法 Plan 继续步骤；spec 改动沿原失效规则；终态不重写，已完成调用复用。
CAS 提交既有 adaptive_planning_required 后进入原 PLAN 调度，不伪造角色事件。
Planner 生成 WorkUnits，原 prerequisites_satisfied 和 Verifier 决定步骤推进，最终沿原独立审查绑定。

新公开 reason 仅 `objective_dependencies`，沿既有事件白名单投影；不统一旧 reason 或建路由 DTO。
内部事件保存 policy/spec 版本，公开关联复用原 event ID/revision；reason 不含题干/候选/自由文本。
新材料来源用既有调用身份和 revision，不能核实则 unknown/unverified，不写已证账本。
旧 Run/finding 不重建或迁移来源，不建审计查询系统。
Reasoner 材料只在父规格和公共验收证明实际输入缺失时补齐，不重构所有角色上下文。

## Owner 与公共红绿映射

预计配置、Harness、路由、恢复、投影和上下文等约 15 文件只是可能影响面；仅修改公共红例证明必要的接缝。
#190 独占这些必要生产者修改及独立测试文件。#191 负责自然输入/角色提示和登记验收；
#192 负责 Explore 请求容量、adapter/transport；共享文件顺序集成，由主控分配 owner，不并发重写。
#193 消费最小公开 reason 与真实事件。#190 公共合同通过后接下游，集成建议 #191 后 #192。

| AC/风险 | 先留红例的公共入口 | 绿例与证据要求 |
| --- | --- | --- |
| AC1 依赖先规划 | POST Job，受控 Intake 依赖 Spec | Planner 首派、依赖 WorkUnits、Reasoner/Verifier 顺序、真实输出/事件/次数 |
| AC2 SOLVED 防短路 | Run/恢复，已有完成 SOLVED | 当前 spec 依赖仍 PLAN，原 finding 未验证，unknown 零派发 |
| AC3 简单题/兼容 | 双根无依赖 Job；配置/Run 恢复 | Explore→whole review；A/B/C hash、原预算/身份，GET 零调用 |
| AC4 可复核 | Job/report/events 与验收记录 | 源码 SHA、精确命令、计数、红绿和未验证项 |
| 当前 spec/崩溃 | Run 事件提交/恢复 | 按当前版本判定、CAS 幂等、控制/unknown 优先，不重发完成调用 |

复用 tests/star_product_support.py::StarJobFixture；test_adaptive_solving_job_185、
test_faithful_s03_job、test_faithful_auto_intake、test_faithful_auto_intake_budget、
test_faithful_s03_specification 和 test_adaptive_solving_185 的公共接缝/响应 fixture。
不 mock 内部协作者，不验证私有函数调用；只在 provider HTTP/时间等系统边界受控。
每切片先保存稳定公共失败，再最小实现与受影响回归；证据写 artifacts/issue190。
所有 Python 使用共享环境的 uv run --no-sync。仅聚焦回归；整仓门禁/双轴独立审阅由阶段退出安排。
不运行 paid/provider/浏览器，不读取 tests/test.md，不提交运行产物。
