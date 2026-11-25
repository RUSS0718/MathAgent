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

后续实现加入了整数加法修复等式的独立检查。有效等式需对应原题，并显示对照与处理分支使用了不同方法。父路线回复需显式引用同一证据 ID、给出匹配的修复等式并通过整数校验，Trace 才记录采纳。该调整先通过离线协议测试，再用于第二批先导。

## 干净检出的独立 Provider 复跑

2026-11-25，从干净检出的 `61da313203ad8bf1b5cc63a479961e478c8a49cc` 完成第二批获批请求。27 个请求与首批请求 ID 互不重叠，均返回 `deepseek-flash`，最长请求用时 1.5 秒。Provider 报告输入 3587、输出 535 Token，预留费用 US$0.0497664，账单金额未知。九个矩阵与两个回退条件全部结束。[DeepSeek 官方定价](https://api-docs.deepseek.com/quick_start/pricing/)

- 回退两臂都通过原运行的整数校验。Baseline 的显式引用含失效证据，RiCL-State 的显式引用中未发现失效证据。Provider 报告的返工输出分别为 96 和 51 Token，统计范围限于本对合成 Checkpoint。
- 随机修复经独立等式检查观察到 `direct` 至 `regroup` 的变化。父请求确实携带处理证据，Provider 回复给出了匹配的重组等式和显式证据引用。诊断修复的两臂均为 `direct`，独立审计拒绝将该处理结果送入父路线。
- 原运行记录矩阵校验通过 7 个、`unknown` 2 个、自动计入的采纳 0 次。原始回复使用了多行 LaTeX 展示式，或在答案后同时给出证据 ID 和结果 ID。补齐这两种格式后，对原始产物离线复核，九个矩阵答案均通过校验，随机修复的父回复通过引用和重组等式检查。原始运行记录保留原值。

采纳证据对应 Provider 请求 `25d16662-6a9e-4f99-9ddf-4fceb73facea`、证据 `evidence_1167fff770a5d258c6e4df88` 和结果 `result_887c34986fbcbb67f7f99948`。核对了回复 SHA-256、请求关联、两个 ID 和重组等式。该观察支持父回复实际引用了补充证据并采用了同一公开路线。

第二批产物位于 `artifacts/deepseek-independent-paired-pilot/`。原始清单及请求账本是 `pilot.json` 和 `requests.jsonl`。本批 27 个 JSON 与 JSONL 文件已核对脱敏。

```powershell
uv run python -m ricl_runtime.experiments --order-seed 17
```

真实复跑入口如下。每批使用新的输出目录，并使用该批批准的配置和源码提交。

```powershell
uv run python -m ricl_runtime.live_pilot --output-root artifacts/deepseek-paired-reproduction
```
