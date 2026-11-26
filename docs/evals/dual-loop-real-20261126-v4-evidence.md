# 真实双循环先导 v4 · 2026-11-26

`ricl-dual-loop-20261126-v4` 接续 [v3](dual-loop-real-20261126-v3-evidence.md) 未派发的五个核心配对。题面版本、配对顺序、APRS+CCL 和 APRS 条件与 v3 一致。冻结源码为 `556857aa1d5489d8b5cd67ab5179ec4d0a09b744`，每 Run 上限 12 次请求、393,216 Token、900 秒、0 工具调用，预检 US$0.7962624/Run。10 个计划项预留 US$7.962624。Provider 目录预检通过，模型 `deepseek-v4.1-flash`，实付账单为 `unknown`。

## 结算和独立评价

| 题目 | 条件 | 状态 | 答案键 / 完备性 | 证据覆盖 | 确认 / 结果未知请求 | 已知输入 / 输出 Token | 已知用量估算 | 授权扣减 |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| DLV3-02 | APRS | 完成 | 正确 / verified | 4 / 4 | 5 / 0 | 4,258 / 5,793 | US$0.0219440 | US$0.3317760 |
| DLV3-02 | APRS+CCL | 完成 | 正确 / verified | 4 / 4 | 12 / 0 | 20,363 / 14,193 | US$0.0617080 | US$0.7962624 |
| DLV3-03 | APRS+CCL | 对照臂超时 | unknown / unknown | 0 / 4 | 4 / 1 | 2,010 / 2,897 | US$0.0108784，加未知用量 | US$0.3317760 |
| 合计 | 两条件 | 2 完成、1 失败、7 未执行 | 2 正确且完备、1 unknown | 8 / 12 | 21 / 1 | 26,631 / 22,883 | 已知部分 US$0.0945304 | US$1.4598144 |

DLV3-02 每个条件独立生成 3 个候选，策略 ID 无交集。复算确认 8 次冷启动、3 次 gain、3 次 fallback 实际派发。DLV3-03 在干预控制臂的第 5 次请求报告 `timeout`，远端结果及用量未知。Runner 停止，保留该题 APRS 条件和后续 3 对共 7 个未执行项。

累计至 v4，全任务计 205 次请求上界及 US$10.5095168 授权扣减。费用估算以每百万输入 US$0.80 和输出 US$3.20 计算，未知请求按单次预检上界入账。

## 自然触发、双臂与裁决

- DLV3-02 APRS+CCL 的第 002 次请求产生可独立核查的关键失败。第 003 次请求提出自主诊断与策略。第 004 和 005 次请求来自同一 Checkpoint `checkpoint_56e2fcd6a7b178d5adb90147`，两臂同模型同预算，均完成独立核查。处理臂策略 ID 与诊断输出匹配。裁决为 `tied`，回灌被拒。第 006 次请求由 APRS 的 `cold_start` 决策派发，随后记录父路线行动。
- DLV3-03 APRS+CCL 在 `checkpoint_39340e47233d9794d2d5f90f` 自然触发。第 004 次请求返回自主诊断。第 005 次请求的控制臂报告超时，裁决为 `arm_timeout`。处理臂和父续接均未派发。
- 两次诊断的相关依赖列表为空。v4 记录两次明确的已有推导引用、零次实际撤销、零次成功回灌。#256、#258 和 #259 保持开放。

## 复算与完整性

在实验源码工作树运行 `uv run python -B artifacts/ricl-dual-loop-20261126-v4/audit.py`。受控归档包含原 Run、脱敏 Trace、冻结计划、独立预算、评价侧答案键和复算报告。

| 文件 | SHA-256 |
| --- | --- |
| `budget.json` | `9f1b781ab658cd150b031d3ce3cdb7eb28a7ffdc94faed08edeacd0dcc5bd766` |
| `frozen-plan.json` | `fa41eaea9f3a57357e24a790c137952e6cc3b58da4d6c5aa7406e1283cff7557` |
| `freeze-manifest.json` | `556b95cf9cacebd21bdd452e211a0ba5ef0c195158c45f62386d7b2aa202f888` |
| `audit.json` | `dcb520cfbb5523af323e0aacbd946ca07cecad55e9e53e9735b338d9d2def982` |
| `archive-manifest.json` | `50a6ea4ab91118b59cee41b36ed42ac1c71d4530e977be6ea48626e5230a9765` |

| Run ID | `run.json` SHA-256 | `trace.jsonl` SHA-256 |
| --- | --- | --- |
| `run_7d407f0349b94150887b06b679c1fbd1` | `e05667ebc02f91ee6eaafebf2100ee114a015be46699dec291e68caec3255e2a` | `12e7f4d6c05e8dfda4cccd206ade6be8b7c45badca880edd334882e0965ed0b4` |
| `run_470ed73daa644e4fa205689c45712a70` | `0dd05498604823b4bfb3cbce0a05169794c8596ffa6e5841748472e18203fc73` | `a78978f841e659bcf5594bc22735bab0436d5c9a8f1e1897f20d6fb1a6bb6e07` |
| `run_a97ca5cf87bf4e60b30e3acbee737f38` | `9ec900296e1a0ea8d62f3bbfb0727fcfdb956bcaf0767d5c268ee0d41c1e63f5` | `fb47171c9ac60d37d51d62f77a12b6f1c5f02b0996e62079bb49676ff09f9bc2` |

APRS 配置 SHA-256 为 `0873ae3ca7917211cbfbbd3867e5b0340dcd6bdec7f597f9efeb67570f806478`，APRS+CCL 为 `681bc4a7c1065122d0b589e94bfd9cdc5d605e120e79d77a8f7ab0324da0fc8f`。
