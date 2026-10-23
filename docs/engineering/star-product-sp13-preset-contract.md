# SP-13 完整预设运行路径合同

状态：准备实施；仅交付可验证的完整预设执行路径，不代表 #56/#69 或真实发布验收通过。

## 目标和边界

复用已有公共 Job、Solver、S3、Registry、S4 和恢复，不新增求解循环。默认 legacy、官方冻结入口和预算不变。服务端显式设置 `SHOWCASE_STAR_FULL_ENABLED=True` 才能请求 `star_reference` / `star_best_effort`；HTTP 不能设置特性、镜像或验收状态。

完整核心固定开启 `star_routing`、`persistent_sessions`、`stream_recovery`、
`final_generation`、`final_solution_review`、`local_code_tool`、`meta_guidance`、
`reexplore_after_replan`、`skills`。Best-Effort 另启用 `candidate_registry` 和 `best_effort`；保留受限模式名称与缺项说明。完整模式配置缺失任一核心条件即拒绝入队，不用改名或静默补回显式关闭的特性。

## 环境准入

完整模式要求真正 `DockerPythonExecutor`、精确镜像 ID 和真实隔离预检。启动时、每次完整 Job 入队前，通过现有 Registry 在独立预检 Run/S3 账本执行固定无模型数学代码，检查镜像/版本、执行成功、stdout 以及清理回执。探针不是用户题目工具动作，使用独立身份与预算并留下可核验产物；不计入 Job 的工具用量。调用不可用、失败或 unknown 均关闭完整模式，legacy/受限路径继续可用。capabilities 展示已观察的运行准入状态，不含“能力已验收”标记。

固定数学镜像初始来自 SP-09：`sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d`。实际 executor 已核验完整 ID 与锁定 policy/library labels；不允许 tag 或主机 Python 工具替代。

## 预算与配置映射

完整默认上限：48 logical calls、48 HTTP attempts、8 tools、262144累计tokens、1100秒总deadline；单次 Intern 默认180秒/一次物理attempt。它是本项目显式上限，不声称复现上游成本；总deadline和token额度可先耗尽。服务端可传 `SHOWCASE_STAR_FULL_BUDGET=RunBudgetLimits(...)` 作为每批硬预算，HTTP 不接受覆盖。受限默认预算维持原值。

Explore最多2轮，Challenge最多5轮，replan最多3次，最终重写最多2次，计划最多20步（既有校验）；每个请求、研究、重试和工具仍受同一S3约束。未配置通用“验收已通过”布尔字段；最终完整/受限/未完成发布结论由SP-13真实证据报告判断。

## 公共验收与退出

采用 TDD：先认证公共 Job 测试失败，再接通最小完整预设、入队准入和现有读接口白名单。scripted HTTP 穿过真实 Adapter；Registry 和固定镜像隔离预检真实执行。

- 完整参考经公共 Job 完成 Explore/Plan/Step/工具/整题审查且同Run/S3/S4可观察。
- 任一核心缺项、未显式启用、无隔离工具、Docker失败/unknown、关闭审核或HTTP配置覆盖，入队前拒绝且模型HTTP为0。
- Best-Effort 在硬预算耗尽后使用已有候选、零新增模型/工具，读取与replay不再派发。
- capabilities 准确区分默认关闭、当前依赖缺失、运行可用；受限缺项按实际配置列出，不沿用历史静态缺口。
- 只跑聚焦与相关回归，不执行全量或真实 Intern；提交规范中文主题，交付前同步最新集成。
