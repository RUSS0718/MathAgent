# Demo 使用说明

Demo 是主观评测的展示入口，不是官方提交入口。它使用同一个根 `ReasoningAgent`，便于展示实际 trace 和失败回退；它不会读取题集或答案库。

## 启动

```shell
$env:INTERN_API_KEY = "..."
python demo_server.py --host 127.0.0.1 --port 8080
```

打开 `http://127.0.0.1:8080/`，输入题目后点击“求解”。

## HTTP 合同

- `GET /health`：返回 `{"status":"ok"}` 类健康信息，不访问模型。
- `POST /solve`：接收 `{"problem": "...", "metadata": {}}`，返回官方 `solve()` 字典。
- 非法 JSON、空题目和非对象 metadata 返回 400；模型或配置错误返回脱敏的 502。

访问日志不记录题目、答案或请求头。凭证只由 `llm_client.py` 从环境变量或未跟踪 `.env` 读取。

## Showcase MVP

主观评测使用独立的 `showcase_server.py`，不会改变上面的 official `/solve`
合同。它提供 `GET /health`、`POST /api/runs`、Run snapshot、追加式 events、
脱敏 Evidence Pack，以及保留失败事件的 `POST /api/runs/{id}/resume`。

没有凭证时，使用 `docs/replay/showcase-replay-v0.1.json` 进行回放，并在 Demo
中标记 `replay`、`experimental` 和 `unavailable` 状态，不把回放当作实时模型调用。

## v0.2 Workbench 与 CLI

从仓库根目录启动数学工作台。使用实时模式时先配置本机模型凭证，`--mode fake` 可体验模拟后端。

```powershell
uv run --no-project python scripts/start_showcase.py web --mode live --data-dir artifacts/showcase-v0.2
```

长题的 live 预算默认按 Showcase 长槽运行（总运行 1100 秒、单次 Intern 请求 180 秒、2 次重试、16384 输出 tokens）；需要临时调整时使用 `.env` 中的 `SHOWCASE_*` 变量。官方 `user_agent.py` 的打榜预算不随之改变。

浏览器打开 `http://127.0.0.1:8090/dashboard`。手动输入数学题可提交给服务，首页示例用于模拟演示。已保存会话通过原 `/dashboard/session/<id>` 地址读取。求解过程展示该任务的公开事件，刷新时从已保存的记录恢复。

CLI 与网页共用身份、Job、SSE 和报告接口。默认 `probe` 拒绝 fake 或未配置凭证的服务，避免把离线结果当成真实 API 证据：

```powershell
uv run python showcase_cli.py capabilities
uv run python showcase_cli.py probe "求解 x^2-1=0，并检查候选根。"
```

也可以逐步调试：`session list|create|load`、`job submit|watch|status|events|report|cancel|resume|polynomial-check` 和 `file list|upload|delete`。CLI 的 cookie 默认保存在被忽略的 `artifacts/showcase-v0.2/cli.cookies`。
