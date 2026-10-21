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

## 已实现边界

- `/dashboard/campaigns?campaign=<id>` 可刷新、分页并导出完整公共报告。归档 hash 对应 S5 不含自身 archive 字段的规范 JSON；导出保留 source、config、Run/Evidence hash、budget 和 attempt 字段。
- `/dashboard/run/<job_id>` 读取已有 Job/report，重连从最后实际消费的事件游标开始。取消复用同一个幂等 key；报告和 Evidence 导出都使用认证后的既有查询接口。
- 验证页面显示最终 artifact、binding、acceptance、checker 和范围；域外标签只来自结构化 checker 的 `in_domain=false`，不能从 unknown 猜测域外。
- Job 创建时持久记录真实执行模式；启动、完成、取消、deadline、通用失败和重启复核保留该身份。旧记录缺少身份时显示 unavailable，不按当前服务配置猜测 live。
- `tests/test_campaign_live_contract.py`、`tests/test_s6_report.py` 与前端 DTO/SSE/store 合同覆盖上述公开接缝。真实浏览器验收使用本地持久 SQLite、现有 pipeline 与拦截后的确定性假 HTTP；运行输入、脚本及产物留在 ignored artifacts，不提交题集或 raw。

浏览器检查应包括：campaign 全部 arm、子 Run 请求/工具/最终验证、域外、工具失败、timeout、cancel、needs_review、断开服务后刷新及恢复重连、两种 JSON 下载。fake HTTP provider 的 returned model 明确带 fake 标记；这些验收不证明真实 provider 或数学能力提升。

## 2026-10-21 浏览器验收记录

执行面：Codex in-app browser / CUA；本机 `127.0.0.1:8096`，内置 Flask 静态构建。fixture 通过既有公共 campaign/Job 接口提交，再从持久 SQLite 报告和 Evidence 读取；HTTP provider 由确定性 fake 拦截，真实 provider 请求为 0。脚本和 store 位于 ignored `artifacts/s6-browser/`，未提交运行输入或 raw。

| 场景 | 实际观察 |
| --- | --- |
| 成功配对 | baseline/candidate、attempt usage unknown、native 协议和 fake transport 可见；未标成真实模型能力 |
| 域外 | 显示“域外：候选不满足定义域”，保留最终 unknown 与范围限制 |
| 工具失败 / timeout | 公开失败类别可见，失败 pair 保留 |
| 取消 / 重启复核 | 实际慢任务通过 UI 取消，mode 始终 fake；待执行 pair 经真实服务重启后保留 canceled / needs_review |
| 服务断开和恢复 | 刷新显示“无法连接服务器。”且保留报告；恢复服务后重连清除告警，仍为 10 个节点 / 23 个事件，无重复 |
| 导出 | campaign JSON 保留完整公共来源和子 Run 字段；按 S5 规范计算 SHA 与 archive 一致；Evidence JSON 实际下载成功 |
| 布局 | 新审阅页在 320 / 768 / 1024 / 1440 宽度可读，768 / 1024 无水平溢出 |

浏览器验证了服务重启和终态重连；断开期间新事件的缺口回放另由前端 store/transport 合同验证：实际消费到 10 后，服务器快照为 20 也不能跳过 11–20。上述记录不代表对真实 live provider、数学正确率或既有 ChatWorkspace 全面重设计的验收。

验收期间发现首个 fixture 的注入 RunService 使用 `workspace.sqlite3`，而工厂默认配置使用 `showcase.sqlite3`，导致借用连接与预算账本不一致。旧 fixture 的终态时延/冻结结论无效。已改为同一显式数据库的全新 store-v3；工厂现在拒绝持久注入服务与配置数据库不一致（仅保留无 pipeline 的测试用 `:memory:` 服务注入；memory 服务与 pipeline 组合明确拒绝）。公开合同在模拟未来一小时后确认终态报告、预算时延和归档身份完全相同，`ended_at` 非空。

store-v3 浏览器复核：成功批次在异步结束后刷新，时延、归档和页面内容保持一致；下载后的 campaign 规范 hash 与 archive 一致，两臂 `ended_at` 非空，fake 与 usage unknown 标记保留。

进程中断合同：HTTP 预算预留的同一事务保存脱敏 attempt ID、逻辑调用、role、请求模型、序号和开始时间。worker 在假 HTTP 内 `os._exit(73)` 后，另一个进程重开同一 SQLite，公开报告 / Evidence 仍保留该 attempt 与未知 usage。`reserved_dispatch_unconfirmed` 仅证明本地预留，不能证明远端已接收或计费；正常返回后按 attempt ID 结算为 `transport_observed`，查询合并事件与账本时不重复计数。此合同使用真实子进程退出，未发真实 provider 请求。

## 最终代码评审

### Standards

固定范围 `ed45443` → `2c29822`。完整标准评审及 audit 增量无阻塞项；工厂 guard 微小增量经复核无新增问题。未执行运行时调用。

### Spec

固定范围 `ed45443` → `2c29822`。规格评审发现并解决 2 类 P1：真实 worker 退出后未决 HTTP attempt 身份丢失，以及注入服务与预算/checkpoint 数据库不一致。`1430cd5` 通过原子预留投影和真实子进程退出回归修复前者；`ef09466` / `2c29822` 通过工厂配置拒绝和终态冻结回归修复后者。最终复核无剩余可执行发现。评审本身为静态检查，未调用模型或运行时 provider。
