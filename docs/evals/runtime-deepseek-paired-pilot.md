# DeepSeek 真实配对先导

2026-11-25，集成分支在 `f748d4bc78a0388a7f0f2c4907f6d67514a38e89` 完成一批获批的真实配对请求。九个矩阵条件使用同一道公开整数加法题，回退对照使用同一合成失败 Checkpoint。请求模型为 `deepseek-v4-flash`，26 个响应均报告 `deepseek-flash`，thinking 关闭，工具调用为 0。[配对规格 #243](https://github.com/RUSS0718/RiCL/issues/243)、[DeepSeek 定价与模型版本](https://api-docs.deepseek.com/quick_start/pricing/)

| 项目 | 记录 |
| --- | --- |
| 请求数 | 26 / 47，全部返回 |
| 单次上限 | 4096 字节输入、256 生成 Token、30 秒 |
| Provider 报告用量 | 输入 2974 Token，输出 291 Token |
| 金额 | 批次上限 US$0.10。按峰值费率预留 US$0.0479232。实际账单未知 |
| 矩阵 | 9 / 9 完成，9 / 9 通过整数加法校验 |
| 搜索 | 普通搜索与 APRS 均扩展 `direct`、`regroup`。普通搜索选择 `direct`，APRS 选择 `regroup` |
| 共享证据 | 8 个矩阵 Run 的后续完成请求引用了已验证结果 |
| 随机／诊断干预 | 同一 Checkpoint，分别选择 `regroup`、`recalculate`，两边各执行对照和处理分支。父路线反馈消费 0 次 |
| 回退 | 两个条件完成，同一 Checkpoint 和诊断。Baseline 申报未引用证据，RiCL-State 引用一条保留的证据。显式引用审计均未发现沿用失效依据 |
| 返工 Token | Baseline 39，RiCL-State 33。计量口径为 Provider 报告的修复请求输出 Token |

回退回复都用自然语言给出了 4。两份原始 Run 的自动校验为 `unknown`，因为回复缺少可由整数校验器识别的独立答案行。配对结论只覆盖显式引用。真实 Provider 的自由文本回复缺少可独立核验的路线或动作变更信号，本批也没有使用独立干预审计器。干预证据覆盖同源分支与修复机会，真实父路线采纳仍待验证。

本机产物位于 `artifacts/deepseek-approved-paired-pilot/`，其中 `plan.json` 记录批准边界，`requests.jsonl` 记录每次预留和返回，`pilot.json` 索引矩阵、回退及脱敏 Trace。已核对 27 个 JSON 和 JSONL 文件的凭证、完整题目和内联推理标记。

从真实先导的源码提交导出到独立本地目录，复跑了离线单题、18 个离线矩阵 Run 和两个离线回退条件。独立 Provider 复跑需新的题目与请求额度批准。

```powershell
uv run python -m ricl_runtime.experiments --order-seed 17
```

真实复跑入口如下。每批使用新的输出目录，并使用该批批准的配置和源码提交。

```powershell
uv run python -m ricl_runtime.live_pilot --output-root artifacts/deepseek-paired-reproduction
```
