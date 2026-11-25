# RiCL Runtime MiniMax smoke

2026-11-25，RiCL Runtime 在源码版本 `1ffc06f28a1e4c586e44f81db404c23f096618d1` 上经配置的 OpenAI 兼容网关完成一次获批请求。使用的题目和整数加法判据与首轮 DeepSeek smoke 相同。[第二模型系列验收 #244](https://github.com/RUSS0718/RiCL/issues/244)、[DeepSeek smoke](runtime-deepseek-smoke.md)

| 项目 | 记录 |
| --- | --- |
| 网关 | `cn2.ezaigc.cn` |
| 请求模型和返回模型 | `minimax-m3.1-flash` |
| 请求 ID | `4be4115ee9584131a2b27177db55d13e` |
| 模型请求数 | 1 |
| 推理与工具 | 推理开启，`effort=low`，工具 0 次 |
| 网关报告用量 | 输入 209 Token，输出 3 Token |
| 批准上限 | 256 生成 Token，30 秒，US$0.05 |
| 费用 | 按网关公布的适用分组最高倍率，预检上界 US$0.000154650。实际账单金额 `unknown` |
| 阶段耗时 | ModelPort 7620.086 毫秒（含网关费用预检），独立验证 0.014 毫秒 |
| 终止与验证 | 正常结束，独立整数加法验证 `verified` |

MiniMax M3.1 Flash 要求启用推理。适配器在 OpenAI Chat Completions 请求中指定低档推理，保存最终回答。费用预检使用网关公共价格表及配额单位。[MiniMax 模型调用文档](https://platform.minimax.io/docs/guides/text-generation)、[New API 倍率计费文档](https://docs.newapi.pro/zh/docs/guide/console/settings/rate-settings)

本机的 `run.json` 和 `trace.jsonl` 保存在 `artifacts/minimax-second-approved-smoke/run_10a1ae2247434a6996d585c8cbfffeab/`。产物已核对凭证、完整输入和推理内容的脱敏情况。

复跑需要新的真实请求批准。在 Windows PowerShell 中，将用户级配置导入当前 shell，再执行同一 CLI 命令。

```powershell
foreach ($name in 'API_KEY', 'BASE_URL', 'MINIMAX_MODEL') {
    $value = [Environment]::GetEnvironmentVariable($name, 'User')
    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
}
uv run python -m ricl_runtime --provider minimax --thinking enabled --problem "Compute 2 + 2." --problem-id public-integer-addition-smoke --condition-id minimax-smoke --model-request-limit 1 --tool-call-limit 0
```
