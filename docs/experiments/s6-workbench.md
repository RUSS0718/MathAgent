# S6 Workbench 审阅合同

范围：#23 / #31；复用 S5 持久 campaign 查询、Workspace Job、报告、事件和 Evidence，不执行第二套循环。

## 设计与计划

1. 增加 `/dashboard/campaigns` 列表和详情，读取现有 HTTP 持久投影；保留所有 pair，按 baseline / candidate 并列展示状态、质量、usage unknown、时延、失败与归档身份。
2. 增加 `/dashboard/run/<job_id>` 审阅页，使用现有 JobController、取消幂等 key、公开 report 和 Evidence URL。仅展示公开白名单字段，最终验证范围和工具 continuation 显式可见。
3. 运行离线公开接口测试及前端检查；由浏览器验收核对持久数据、刷新、故障、取消、重连与导出。测试通过只证明工程合同。

## 已确认验收 seam

- Flask campaign/Job/report/Evidence 公共接口：覆盖持久身份、状态及脱敏，沿用 S1–S5 测试。
- 前端 DTO 与导航合同：覆盖 unknown/null 保留、非法响应拒绝及 campaign/Run 深链；不替代浏览器交互验收。
- 浏览器：从持久 fake provider/store 进入 campaign/Run，检查成功、域外、工具失败、timeout、cancel、needs_review、断线重连及导出。fixture 只在 ignored artifacts 或临时目录生成。

模式始终显示原始 live/fake/replay/unavailable/planned 名称及中文说明；fake/replay 不证明真实模型能力。金额为 null 时显示未知，不推算 0。completed 批次不代表数学正确。缺失报告/请求失败显示可重试提示，不显示空白成功。R1–R5 标为 planned。
