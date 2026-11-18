# Faithful 后端闭环审计（2026-11-12）

审计起点 `1ca4fea64e72635b58b6720f32de3508be4d3527`，结合本地源码、当前文档索引与本机 8090 的能力响应。不是独立数学能力评测。实施要求见 [服务入口合同](faithful-service-entry-contract.md)。

## 起点事实

8090 声明 live/configured，但只有 legacy、star_limited 及其 Best-Effort 可选；完整参考、并发、表达、F7 均未启用。浏览器提交 `x^2-1=0` 明确发出 legacy 请求，Run `run_0ca96907d8468ef86d04c7d565c00020` 于约58秒完成，4次模型请求、1次工具调用，刷新可读答案 ±1。仅证明这一条旧流水线真实可达。新协作视图在此 Run 中仍显示“计划尚未生成”，不能把它当作新架构执行证据。

## 能力链矩阵

“已有工程证据”引用 [文档索引](../README.md) 对应阶段记录，未在本轮重新认定数学能力。默认开关关闭不等于模块未实现。

| 能力 | 实现及公共接缝 | 当前断点/结论 |
| --- | --- | --- |
| S01 调用生命周期 | `solver_harness/calls.py`、`intern_port.py`，公开 Job/恢复 | 已有工程证据；常规 CLI 未装配完整 transport 配置；新增调用必须沿用 unknown 规则 |
| S02 上下文 | `context_pack.py`、运行时 context_capacity | 已实现未默认接线；未知容量必须明示，不得编造 provider 硬上限 |
| S03 规格/工作块 | `specification.py`、`harness.py`、Job problem_spec | 缺普通文本自动生产接缝；仅打开 problem_spec 会拒绝前端输入 |
| S04 进展/停滞 | `controller.py`、progress_scheduling | 已实现；依赖规格和显式特性，不能靠旧 legacy 事件推导 |
| S05 工作台与持久产物 | Job/SSE/Report/Evidence、workbench projection | 工程可达；先前新前端验收为受控/fake，真实新架构尚缺联调 |
| S06/F6 表达 | `presentation_api.py`、独立产物与来源绑定 | 已实现未启用；表达不升级数学等级 |
| F1 依赖图 | `proof_graph.py`、公开图投影 | 已实现未默认接线；须跟随真实命题及版本更新 |
| F2 串行/APRS | `routes.py`、serial_routes | 已实现；适用路线由现有控制器执行，非普通 CLI 默认能力 |
| 完整并发 | `population_config`、population runtime | 独立预设与容量准入；未继承串行所有特性，不能无条件与 F4 叠加 |
| F3 形式化 | `formal.py`、`formal_docker.py`、formal_policy/target | 有真实后端及受限模板证据；普通文本到目标及自主调用入口未闭环，不支持任意数学题自动形式化 |
| F4 同源干预 | intervention API/runtime、NativeCheckpointExecutor | 已实现串行 checkpoint 双臂；仍依赖外部假设/动作/触发，不能称已能自主选择，也不支持 population 路线 |
| F5 记忆与缓存 | memory 控制、advisory 注入、Goal Cache 当前复核 | 已实现，注入另受会话同意与来源约束；打开管理 API 不等于每次都可用记忆 |
| F7 系统视图 | `faithful_system_api.py` | 已实现只读展示及深链；不负责创建求解 |
| F8 真实评测 | faithful_eval、独立冻结实验 | 真实实验未完成；工程门禁不替代 provider/自然题/数学正确性证据 |

## 自主能力的验收要求

普通用户只输入题目。Agent 应能看到实际能力和限制，选择适用机制并通过真实执行器执行；选择理由、执行结果、跳过/不可用原因与来源留在公开边界内。单纯注册开关、显示星图或把全部机制机械串行执行均不满足要求。

实施顺序：统一配置与准入 → 同 Run 自动规格与恢复 → 前端默认自主入口 → 并发/形式目标/干预的自主选择及执行合同 → 真浏览器与真实模型验收。每步独立证明，未通过项保持未完成。
