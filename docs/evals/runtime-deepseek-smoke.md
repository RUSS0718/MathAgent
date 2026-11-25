# RiCL Runtime 首轮 DeepSeek smoke

2026-11-25，RiCL Runtime 在源码版本 `2b291cc67c657f47cd3846aa5b0bcb6e62bdc2b6` 上完成一次获批的真实请求。[首 Provider 验收 #238](https://github.com/RUSS0718/RiCL/issues/238)

| 项目 | 记录 |
| --- | --- |
| 请求模型 | `deepseek-v4-flash` |
| 返回模型 | `deepseek-flash` |
| 请求 ID | `089fc53b-8422-47c3-bc3c-98d33c218c30` |
| 请求数 | 1 |
| Thinking 和工具 | Thinking 关闭，工具 0 次 |
| 供应商用量 | 输入 11 Token，输出 7 Token |
| 资源上限 | 256 输出 Token，30 秒，US$0.05 |
| 费用 | 预检上界 US$0.0055296，实际账单金额 `unknown` |
| 阶段耗时 | ModelPort 947.975 毫秒，独立验证 0.009 毫秒 |
| 终止原因 | `answer_generated` |
| 独立验证 | `verified`，范围为本题的整数加法 |

DeepSeek 将旧的 `deepseek-v4-flash` 名称映射到 V4.1 Flash。此记录只覆盖单题单路线的调用、记账和整数加法验证。[DeepSeek 模型与定价说明](https://api-docs.deepseek.com/quick_start/pricing/)

原始本机产物位于 `artifacts/deepseek-first-approved-smoke/run_1d5d588952fa4f079c6e2ec5a7cf8d7c/`。目录内的 `run.json` 和 `trace.jsonl` 已检查，未包含凭证或发送的完整提示词。

复跑需要新的真实请求批准。配置本机 `API_KEY`、`BASE_URL` 和 `MODEL` 后，使用获批的输出目录和参数。[真实运行边界](../engineering/development-gates.md#真实运行与实验边界)

```powershell
uv run python -m ricl_runtime --provider deepseek --thinking disabled --problem "Compute 2 + 2." --problem-id public-integer-addition-smoke --condition-id deepseek-first-approved-smoke --model-request-limit 1 --tool-call-limit 0
```
