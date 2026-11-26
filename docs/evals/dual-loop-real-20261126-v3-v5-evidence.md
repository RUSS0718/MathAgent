# 真实双循环先导 v3–v5 · 2026-11-26

本记录归档 v5 并对齐 [v3](dual-loop-real-20261126-v3-evidence.md) 与 [v4](dual-loop-real-20261126-v4-evidence.md) 的结算记录。三个批次使用同一实验源码 `556857aa1d5489d8b5cd67ab5179ec4d0a09b744`。v4 与 v5 只首派前批未执行的核心条件。冻结题面、答键和配对顺序由 v3 继承，答键留在评价侧。六个核心配对各比较 APRS+CCL 和 APRS，模型、候选生成规则、独立核查和根预算匹配。自然触发已经出现，四个条件补充 Run 未启用。

## 六个核心配对

| 题目 | 批次 | 条件 | 状态与停止原因 | 独立答案键 / 完备性 | 证据覆盖 | 确认 / 未知请求 | 输入 / 输出 Token | 峰值估算 / 授权扣减（US$） |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| DLV3-01 | v3 | APRS+CCL | 预算停止 · `model_request_budget_exhausted` | 正确 / unknown | 2 / 4 | 12 / 0 | 11,282 / 10,043 | 0.0411632 / 0.7962624 |
| DLV3-01 | v3 | APRS | 失败 · `invalid_output` | unknown / unknown | 0 / 4 | 2 / 0 | 643 / 2,172 | 0.0074648 / 0.1327104 |
| DLV3-02 | v4 | APRS | 完成 · `answer_generated` | 正确 / verified | 4 / 4 | 5 / 0 | 4,258 / 5,793 | 0.021944 / 0.3317760 |
| DLV3-02 | v4 | APRS+CCL | 完成 · `answer_generated` | 正确 / verified | 4 / 4 | 12 / 0 | 20,363 / 14,193 | 0.061708 / 0.7962624 |
| DLV3-03 | v4 | APRS+CCL | 失败 · `timeout` | unknown / unknown | 0 / 4 | 4 / 1 | 2,010 / 2,897 | 0.0108784（已知部分） / 0.3317760 |
| DLV3-03 | v5 | APRS | 完成 · `answer_generated` | 正确 / verified | 4 / 4 | 5 / 0 | 6,272 / 8,958 | 0.0336832 / 0.3317760 |
| DLV3-04 | v5 | APRS | 完成 · `answer_generated` | 正确 / verified | 4 / 4 | 7 / 0 | 7,308 / 6,803 | 0.027616 / 0.4644864 |
| DLV3-04 | v5 | APRS+CCL | 预算停止 · `model_request_budget_exhausted` | unknown / unknown | 0 / 4 | 12 / 0 | 12,807 / 14,700 | 0.0572856 / 0.7962624 |
| DLV3-05 | v5 | APRS+CCL | 完成 · `answer_generated` | 正确 / verified | 4 / 4 | 7 / 0 | 6,913 / 3,219 | 0.0158312 / 0.4644864 |
| DLV3-05 | v5 | APRS | 完成 · `answer_generated` | 正确 / verified | 4 / 4 | 6 / 0 | 4,886 / 4,750 | 0.0191088 / 0.3981312 |
| DLV3-06 | v5 | APRS | 完成 · `answer_generated` | 正确 / verified | 4 / 4 | 11 / 0 | 11,334 / 7,407 | 0.0327696 / 0.7299072 |
| DLV3-06 | v5 | APRS+CCL | 完成 · `answer_generated` | 正确 / verified | 4 / 4 | 12 / 0 | 10,698 / 8,052 | 0.0343248 / 0.7962624 |

核心条件结算 8 个完成、2 个预算停止、2 个失败及 0 个未执行。独立答案键 9 个正确，0 个错误，3 个 unknown。完备性 8 个 verified，4 个 unknown。条件效果缺少正式协议与统计支持。

## 费用、候选和调度

每 Run 上限为 12 次请求、393,216 Token、900 秒、0 工具调用。绑定模型 `deepseek-v4.1-flash`，Provider 传输超时 180 秒。单次预检上界 US$0.0663552，每 Run US$0.7962624。v5 启动前为 7 项预留 US$5.5738368。实付账单均为 `unknown`。

三批累计 95 次确认请求、1 次远端结果未知，已知 187,761 Token。已知用量按活跃定价上界估算 US$0.3637776，本系列按请求预检上界扣减 US$6.3700992。全任务累计 265/384 次、US$14.4908288/US$30。

实际派发汇总为 `cold_start` 33 次、`explore` 5 次、`fallback_round_robin` 13 次、`gain` 16 次。配对候选由各 Run 独立生成。

| 题目 | 冻结条件顺序 | 实际候选数 | 策略 ID 交集 |
| --- | --- | ---: | ---: |
| DLV3-01 | APRS+CCL → APRS | 3 / 3 | 0 |
| DLV3-02 | APRS → APRS+CCL | 3 / 3 | 0 |
| DLV3-03 | APRS+CCL → APRS | 3 / 3 | 0 |
| DLV3-04 | APRS → APRS+CCL | 3 / 3 | 0 |
| DLV3-05 | APRS+CCL → APRS | 3 / 3 | 0 |
| DLV3-06 | APRS → APRS+CCL | 3 / 3 | 0 |

## 真实干预链

| Run ID | Checkpoint | 自主诊断 | 同源双臂 | 裁决 | 真实续接 |
| --- | --- | --- | --- | --- | --- |
| `run_50ff99f2167b4555b354dcef624897bd` | `checkpoint_231979ce0c20487bc0b4865a` | 已派发并提出策略 | 完成匹配派发 | `control_advantage` | `cold_start` |
| `run_470ed73daa644e4fa205689c45712a70` | `checkpoint_56e2fcd6a7b178d5adb90147` | 已派发并提出策略 | 完成匹配派发 | `tied` | `cold_start` |
| `run_a97ca5cf87bf4e60b30e3acbee737f38` | `checkpoint_39340e47233d9794d2d5f90f` | 已派发并提出策略 | 未取得完整双臂 | `arm_timeout` | 未派发 |
| `run_8cc5fa8a6b114c929db2031d2aace797` | `checkpoint_7b4f97c6e9d5092a510ce4f9` | 已派发并提出策略 | 完成匹配派发 | `independent_comparison_unknown` | `cold_start` |
| `run_3e785f40cfe64384b96c1e433f6acb9b` | `checkpoint_622850840393f3210deb6374` | 已派发并提出策略 | 完成匹配派发 | `independently_resolved_failure` | `cold_start` |
| `run_6379552c8bcb457fb72e33565147c6e7` | `checkpoint_d683b9265b14d6232ca0097e` | 已派发并提出策略 | 完成匹配派发 | `tied` | `cold_start` |

- `run_3e785f40cfe64384b96c1e433f6acb9b` 在独立裁决后回灌 `evidence_299fc029258d73296d0b8291`。APRS 选择 `cold_start`，实际派发 `run_3e785f40cfe64384b96c1e433f6acb9b_request_006`，并送达回灌证据。父回复明确引用为 `evidence_299fc029258d73296d0b8291`。决策输入中的回灌证据信用已复核为 `true`。

唯一成功回灌的 Run 在冷启动完成时结束。回灌后有两次实际冷启动派发，APRS 的决策输入包含回灌信用。回灌后的 gain 派发为 0，因此本系列没有给出回灌改变选中路线的实测证据。全系列记录 20 次明确证据引用和 0 次撤销。

## 票据验收

- [#255](https://github.com/RUSS0718/RiCL/issues/255) 与 [#257](https://github.com/RUSS0718/RiCL/issues/257) 已关闭。M2 的配对结果见 [独立归档](m2-real-20261126-v2-evidence.md)。本系列的两条件均使用 APRS，其冷启动后派发用于观察实际机制。
- [#256](https://github.com/RUSS0718/RiCL/issues/256) 的真实证据覆盖有效成果送达及明确引用。当前 CLI 没有独立撤销回调，本系列没有可用于验收的真实支撑撤销。
- [#258](https://github.com/RUSS0718/RiCL/issues/258) 的 AC4 由 DLV3-05 的触发、双臂、回灌及父续接验证。六个真实 CCL Run 均自然触发并取得自主诊断。每个自然触发的相关依赖列表均为空。AC5 中相关依赖存在时的请求送达与隔离由 [受控 Runtime 验收](https://github.com/RUSS0718/RiCL/blob/556857aa1d5489d8b5cd67ab5179ec4d0a09b744/tests/test_runtime_online_intervention.py#L78) 覆盖。真实 Run 的诊断与策略由 Provider 生成，Trace 关联失败证据、诊断和处理臂收到的策略。
- [#259](https://github.com/RUSS0718/RiCL/issues/259) 已取得同一真实 Run 的回灌、APRS 决策输入和实际请求送达。仍需观察回灌在冷启动结束后影响真实路由选择。五组离线消融和正式研究协议各沿用既有验收与 [#250](https://github.com/RUSS0718/RiCL/issues/250)。
- [#254](https://github.com/RUSS0718/RiCL/issues/254) 依赖 #256 与 #259 的剩余证据。[#248](https://github.com/RUSS0718/RiCL/issues/248) 记录当前验收状态。

## 复算与哈希

在实验源码工作树通过 `uv run python -B artifacts/ricl-dual-loop-20261126-v5/audit.py` 复算 v5。对 v3 和 v4 执行同名脚本后，用 `artifacts/dual-loop-series-audit.py` 按批次顺序汇总。受控归档保存每请求账本、配置快照、答键和脱敏 Trace。以下 SHA-256 可核对文件版本。

| 文件 | SHA-256 |
| --- | --- |
| v5 `budget.json` | `04613a76b3d1d72115eea3e14972a0edd21fc524413523aba21945448ea92537` |
| v5 `frozen-plan.json` | `0e48fb1ed0d34bcbf73ec5b1891efb53cd5ccfe79d3a0966e181550dcdafc9f1` |
| v5 `freeze-manifest.json` | `3097088caf47b68c717a65f7defd80619257a2928d54ac3916ca2d0643ab8cb2` |
| v5 `preflight.json` | `31f0fc2c2f08b55e89270189fe32b0b5ab28d425ff9e57aaf162a4b6b437a624` |
| v5 `audit.json` | `16134b9f71b7d6a34d4c15796e169401d816050b757c3430a0df0af76d02d70e` |
| v5 `archive-manifest.json` | `1b3b6b2797bb7aa6c31bba80625dd0d6366530b3e876001983c9ab476ad7644d` |
| 三批 `dual-loop-series-audit.json` | `7b68ba3262fa0ab123ee6fecb41cd52a5eaa79cbec52cee7c1d91e48f4450cad` |

| v5 Run ID | Run SHA-256 | Trace SHA-256 | 配置 SHA-256 |
| --- | --- | --- | --- |
| `run_f2185636d5d743438a0b576828d08c22` | `78a0c5bef0b96b6e927d10261b1fec1f3cddba9a7ae9a2ad62d43f9e64e14f34` | `f47841285954d41ae69cd0db887e98156dcc4267f7532b5faa55824577ab7acf` | `0873ae3ca7917211cbfbbd3867e5b0340dcd6bdec7f597f9efeb67570f806478` |
| `run_8941d6a92f9c41f7b00393f0336d5f0f` | `c132949845a48c6cb04dc99c4ce79e95262db389fa5139a24f50f88b29dc46f3` | `6057cb84d747fbb228632143a143d3ef65c9dbabb980b4925003aa9aaf7a1f59` | `0873ae3ca7917211cbfbbd3867e5b0340dcd6bdec7f597f9efeb67570f806478` |
| `run_8cc5fa8a6b114c929db2031d2aace797` | `a97e44c8f10288adef7d8bbe7de52a6203bff3ca23a1f8b2d6f35d705ccd82ff` | `e249b60dc4dee0626e1edb9d6d3084e36e6e810f89857810241190d80ca76b7d` | `681bc4a7c1065122d0b589e94bfd9cdc5d605e120e79d77a8f7ab0324da0fc8f` |
| `run_3e785f40cfe64384b96c1e433f6acb9b` | `bd901e3ad206b4ca46314bfec46368bfeae2aeb9be22062f707bbc6e3fcbdbfb` | `ffa062d5ad24119132a28cc43fe2d960cc283e1426d23c879f6e7d2ba8e7e920` | `681bc4a7c1065122d0b589e94bfd9cdc5d605e120e79d77a8f7ab0324da0fc8f` |
| `run_997fd3e536984568baebd11733542e1d` | `37caf95eb807605376456c6fa9b2855f22ef6df42953955b8a099d3d609b3627` | `8ae965cb39b1d3c33c3bd64cd4b50ae334cf9cdf74a5a35131c32586b1f21c92` | `0873ae3ca7917211cbfbbd3867e5b0340dcd6bdec7f597f9efeb67570f806478` |
| `run_f4daf41ca2ba4245ba744fdbfd9b89df` | `804e18ae9d0716284b4e399bce4e8db168799dc6e2b0d31201d568980794236c` | `12cb0bf1f05cb3a1b67d666e4070bebe95cf34b7e0f0fc02adb2ea1deac72a58` | `0873ae3ca7917211cbfbbd3867e5b0340dcd6bdec7f597f9efeb67570f806478` |
| `run_6379552c8bcb457fb72e33565147c6e7` | `1f8d5a564515c631c7926e5664c7cab7ab112e98dc3227abe00a81a25855296c` | `8c5a47a78dd3bb0518583733f0ad3c387b8c0f6affb93d2662695b286bdba642` | `681bc4a7c1065122d0b589e94bfd9cdc5d605e120e79d77a8f7ab0324da0fc8f` |
