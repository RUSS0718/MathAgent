# S5 同题配对 Runner 合同

范围：GitHub #23 / #30 的工程基础设施；不实现 R1–R5，也不证明数学能力提升。

## 入口与默认值

- `POST /api/experiments/campaigns`：沿用 loopback 身份、CSRF 和 UUID v4 `Idempotency-Key`；返回 202。相同 key / 相同输入只返回既有批次，相同 key / 不同输入返回 409。
- `GET /api/experiments/campaigns?offset=0&limit=20`：按创建顺序倒序返回摘要，limit 为 1–100。
- `GET /api/experiments/campaigns/<campaign_id>`：查询所有 pair 和 child Job 的持久投影；不调度或重试执行。
- CLI：`uv run python showcase_cli.py campaign create <外部输入.json> --idempotency-key <UUID>`，以及 `campaign list` / `campaign detail <campaign_id>`。输入题集仅来自运行时外部文件，不随 Git 提交。

输入对象包含 `schema_version: 1`、`dataset_version`、`problems: [{id, problem}]`、`model: intern-s2`、`allow_network: false`、`budget`、`conditions` 和 `strategies`。最多 100 题；每题创建 baseline 和 candidate 两个独立 ChatSession / Workspace Job。独立会话满足既有每会话只允许一个活动 Job 的合同。

`budget` 必须明确提供 RunBudgetLimits 的五个字段：`max_model_calls`、`max_http_attempts`、`max_tool_calls`、`max_tokens`、`max_runtime_seconds`。Runner 在提交 worker 前把同一配置写入 S3 账本，实际执行使用该账本；不是只在报告中展示计划预算。

`conditions` 包含 `thinking_mode: true` 和 `max_tokens`。`strategies` 仅允许 baseline / candidate，各自仅接受实际传入 Job 的 `verification_mode: auto|required|off`（默认 auto）。报告记录 applied_fields、strategy_hash 和 strategy_status。R1–R5 策略尚未实现，传入这些字段会被拒绝，不能用标签冒充算法差异。

默认 `allow_network=false`，只能进入没有 pipeline 的 fake Workspace；即使注入 pipeline，也不能从离线配置调度它。联网需要请求显式设为 true、服务运行在 live 模式，以及服务配置显式 `SHOWCASE_CAMPAIGNS_LIVE_ENABLED=True`。同时核对 Adapter 与实际 client 的正式模型、thinking_mode 和输出上限；不自动切模型或修改公共 pipeline。服务开关表示执行权限，计划配置本身不授权 live 预算。当前验证只使用假 HTTP，未执行真实模型请求。

## 结果、恢复与归档

创建时先持久保存完整批次及每个 arm 意图，然后经既有 WorkspaceService.create_job 调度。各 arm 共享题目 hash、数据版本 / hash、正式请求模型、条件与预算。只允许验证模式不同。所有执行、取消、deadline、HTTP attempts、checkpoint 和最终 Evidence 均沿用既有 Run/Job 路径。

查询保留 succeeded、failed、canceled、unknown 和 incomplete。启动中断后未关联的 arm 保持 incomplete，重启不会自动补跑；已关联 Job 遵循 S3 的 needs-review 恢复语义。批次 completed 表示所有 arm 已进入终态，不能解释为所有题成功。质量来自最终验证 Evidence，默认 unknown；不是答案正确率。

列表和详情只派生当前投影，不回写创建记录，因此另一个服务实例的旧查询不能覆盖正在建立的 child Job 关联。归档先写入同目录临时文件、flush / fsync，再原子发布；已有内容必须与预期字节一致，损坏文件由可重建的同一内容恢复。有效旧版本不会被修改。

#23 / #30 没有要求 `max_inflight=1`。Runner 沿用 Workspace 的 worker 并发，不接受或声称应用计划文件中的 calibration 并发参数。`experiments/campaign.json` 是独立的计划预检合同，不是这个运行入口的配置或 live 授权。

每个 arm 返回请求 / returned 模型、逐 attempt、provider 已知计量与未知字段计数、账本、时延、失败类别及既有 report / evidence URL。未知 usage 不补成 0；金额和确定性工具金额保持 null。批次消耗只覆盖本批次；项目总消耗与部署总消耗未经核对时保持 null。

配置、数据、源码提交、官方 baseline 提交 / 文件 hash、child Run 和 Evidence 形成可复核身份。产物写入既有 ignored `artifacts/<workspace>/campaigns/<campaign_or_run_id>/`。文件名包含内容 SHA-256；report 的 hash 针对不含自身 archive 字段的精确 UTF-8 JSON 字节。查询可生成追加的内容版本，绝不覆盖旧报告。配置归档包含运行时输入题目；公共报告仅保留题目身份。不得提交题集、答案库、完整 prompt、凭证或运行 raw。

## 验收接缝

`tests/test_campaigns.py` 从 Flask 与 CLI HTTP 接口覆盖 fake 成功、失败 pair、deadline、取消、重启保留、配置拒绝、幂等和归档 hash。`tests/test_campaign_live_contract.py` 使用显式假环境、真实 Adapter、假 HTTP 与确定性 Registry，检查 unknown usage、实际预算限制、每个 Run 的 attempt 关联和离线禁止联网。公共子报告在另一个 SQLite writer 预留期间仍能读取已提交预算，预算查询不取得写事务。

测试中公开小题内联，外部 JSON 只在临时目录生成。工程合同通过不替代 live 能力或独立数学评测。
