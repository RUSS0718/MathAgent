# 真实双循环先导 v3 · 2026-11-26

批次 `ricl-dual-loop-20261126-v3` 使用 `research-prototype` 源码 `556857aa1d5489d8b5cd67ab5179ec4d0a09b744`。同一 Python Runtime 配对执行 APRS+CCL 和 APRS，按题交替先后顺序。两条件使用相同模型、候选生成规则、独立精确核查及根预算。计划含 6 个核心配对和 2 个条件补充配对。题集由项目自编，题面版本 `dual-loop-radical-v3`，答案键在评价侧。正式比较和论文协议由 [#250](https://github.com/RUSS0718/RiCL/issues/250) 跟踪。

目录认证经本批进程直连返回 HTTP 200，目标模型 `deepseek-v4.1-flash` 可用。每 Run 上限 12 次请求、393,216 Token、900 秒、0 工具调用，Provider 超时 180 秒，单请求输出上限 16,384 Token。执行前复核的峰值估算按每百万输入 US$0.80、输出 US$3.20 计。预检上界 US$0.0663552/请求、US$0.7962624/Run，16 个计划项共预留 US$12.7401984。全任务授权为 384 次真实推理请求、US$30。[授权记录](https://github.com/RUSS0718/RiCL/issues/259#issuecomment-7164775665)。

## 实测账本

| 条件 | Run 结果 | 独立答案键 / 完备性 | 已证目标 / 冻结目标 | 已确认请求 | 输入 / 输出 Token | 费用估算 | 授权扣减 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| APRS+CCL | 等额请求预算耗尽 | 正确 / unknown | 2 / 4 | 12 | 11,282 / 10,043 | US$0.0411632 | US$0.7962624 |
| APRS | `invalid_output` | unknown / unknown | 0 / 4 | 2 | 643 / 2,172 | US$0.0074648 | US$0.1327104 |
| 合计 | 1 停止、1 失败、14 未执行 | 1 正确、1 unknown / 2 unknown | 2 / 8 | 14 | 11,925 / 12,215 | US$0.0486280 | US$0.9289728 |

首个配对为 DLV3-01。APRS 对照在候选生成后收到已结束的求解回复，Runtime 将回复判为 `invalid_output`。Runner 随即停止，另外 10 个核心 Run 和 4 个条件补充 Run 均保留为未执行。14 次请求的用量均由 Provider 返回，实付账单均为 `unknown`。计入历史批次后，全任务累计 183 次 / US$9.0497024。

两臂各生成候选并独立选路。复算确认实际派发为 4 次冷启动、1 次 fallback、3 次 gain 和 1 次 explore。所有冷启动后的派发出现在 APRS+CCL Run，配对对照提前失败。已执行规模支持真实派发观察，样本不足以比较条件效果。

## 同一 Run 的干预轨迹

以下请求序号属于 APRS+CCL Run `run_50ff99f2167b4555b354dcef624897bd`，Checkpoint 为 `checkpoint_231979ce0c20487bc0b4865a`。

| 请求 | 关联证据 |
| --- | --- |
| 003 | 本轮独立核查发现 4 个尚无有效支撑的目标失败。Runtime 准入干预并为诊断、双臂和父续接预留 4 次请求。 |
| 004 | Provider 返回诊断与策略。Trace 关联失败证据、诊断 ID 和策略 ID。本轮可交付的相关依赖列表为空。 |
| 005、006 | 两臂匹配 Checkpoint、失败证据、实际模型 `deepseek-v4.1-flash-1017`、预算和独立核查。处理臂收到 004 的策略。对照臂解决 4 个受影响目标，处理臂解决 1 个。 |
| 007 | 裁决为 `control_advantage`，回灌状态为 `withheld`。APRS 通过 `cold_start` 选择真实续接路线，Trace 关联决策 ID、实际请求和父路线行动。 |

#258 新增了自然触发、自主诊断、同源派发、独立裁决和拒绝回灌后的续接实证。成功回灌、回灌后派发以及涉及既有依赖的诊断仍缺本批证据。#259 仍缺同一真实 Run 内获准更新和后续调度读取该更新的链条。#256 本批为 0 次支撑撤销，常规 CLI 未配置独立撤销回调。

## 复算与文件完整性

在该受控归档目录使用仓库根目录的 `uv` 环境执行 `uv run python -B artifacts/ricl-dual-loop-20261126-v3/audit.py`。复算检查输入和答案键哈希、配置哈希、逐请求账本、APRS 决策及实际派发、同源干预和独立数学评价。原始 Run、Trace、独立预算和评价键存于受控 `artifacts/`。

| 文件 | SHA-256 |
| --- | --- |
| `budget.json` | `b7524e6eec73547ca802ae97302260c5eaccec6da72a8f415e0cd47d22f8083a` |
| `frozen-plan.json` | `bfcc0b8f4bc53b3b6e4636793f9b5333f747f5aa49b82ac8192b100a161bd24c` |
| `freeze-manifest.json` | `a544a9249f860b157e80fa2222e932b232b706c135439aab56841fe839aff2c4` |
| `summary.json` | `c04a19e9f10b3ca6a7278ec30c65991b2afc3b17ce089942c10d413c66864eed` |
| `audit.json` | `ecb36b110ef1f60585a9f6d3e09afb8dbfb7cbd85e044efe5912f5ac5bbc628e` |
| `archive-manifest.json` | `455aed29d80cef8ce554f7ac807355361fd3f290fe568f9b98314d01b348015b` |

| Run ID | `run.json` SHA-256 | `trace.jsonl` SHA-256 | 配置 SHA-256 |
| --- | --- | --- | --- |
| `run_50ff99f2167b4555b354dcef624897bd` | `a803866e34d441492fd40c4f3daa7f2ec2109c37b9db5de6770968abb8eb5083` | `afacce1ec024e755b0554d67f5d6adf01a835e357c50c038a0ce218169bc4be3` | `681bc4a7c1065122d0b589e94bfd9cdc5d605e120e79d77a8f7ab0324da0fc8f` |
| `run_a055983d32ea4dc8b4e3f65f7d3cd6c0` | `110f85758835e9eb8e0da5a13b7508d942759154da707e1217db4d187a465087` | `8b42b4cd2290b478f1c497def870d67db0f96bf5edc9af0ffcb8568b6f2005ac` | `0873ae3ca7917211cbfbbd3867e5b0340dcd6bdec7f597f9efeb67570f806478` |
