# 回灌后 APRS 选路后续先导 · 2026-11-26

[v3–v5](dual-loop-real-20261126-v3-v5-evidence.md) 已验证一次真实回灌和父回复引用。后续先导寻找同一 Run 在冷启动结束后出现的实际 gain 派发，并检验新增证据信用是否改变选中路线。两条件均运行同一精确根式核查，使用 APRS+CCL 和 APRS。题面由项目自编，答键在评价侧。这些批次用于机制观察，正式比较归 #250。

每批启动前冻结判定。对已确认派发的 gain 决策重算收益与实际 Token 比值，只移除已采纳干预带来的信用并保持其他已记录输入。若无可比较收益，按已记录轮转位置重算。这个单步复算用于判断特定决策对该信用的依赖。

| 批次 | 源码 | 计划 Run | 输出 Token／请求 | 共享 Token／Run | 费用预检／请求（US$） | 整批预留（US$） |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| ricl-dual-loop-20261126-v6 | `556857aa1d5489d8b5cd67ab5179ec4d0a09b744` | 8 | 16,384 | 393,216 | 0.0663552 | 6.3700992 |
| ricl-dual-loop-20261126-v7 | `e33b4ffe6f22362203c5aa62cafa7a8e74e86d9a` | 4 | 24,576 | 524,288 | 0.0925696 | 4.4433408 |

v6 的四个核心配对为新题。归一化比较平方约束与符号阈值，未与既有 14 道留出输入重复。
v7 原样复用 v6 首两个两臂均已确认截断的配对，保留 v6 的每条记录。v7 两条件同步启用扩大后的上限。
v7 首个 Run 确认 3 次派发，第 4 次回访在本机预检拒绝，未发送。回访草稿超限路径由 [PR #270](https://github.com/RUSS0718/RiCL/pull/270) 的正常入口夹具复现。

## ricl-dual-loop-20261126-v6

| 题目 | 条件 | Run 状态／停止原因 | 末次 Provider finish | 独立正确性／完备性 | 确认／未知请求 | 已知输入／输出 Token | 估算／授权扣减（US$） |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| DLV6-01 | APRS+CCL | `failed` / `budget_exhausted` | length | unknown / unknown | 2 / 0 | 635 / 16,486 | 0.0532632 / 0.1327104 |
| DLV6-01 | APRS | `failed` / `budget_exhausted` | length | unknown / unknown | 3 / 0 | 1,055 / 19,847 | 0.0643544 / 0.1990656 |
| DLV6-02 | APRS | `failed` / `budget_exhausted` | length | unknown / unknown | 3 / 0 | 1,064 / 25,151 | 0.0813344 / 0.1990656 |
| DLV6-02 | APRS+CCL | `failed` / `budget_exhausted` | length | unknown / unknown | 6 / 0 | 4,160 / 17,573 | 0.0595616 / 0.3981312 |
| DLV6-03 | APRS+CCL | `stopped` / `model_request_budget_exhausted` | stop | unknown / unknown | 12 / 0 | 20,885 / 20,851 | 0.0834312 / 0.7962624 |
| DLV6-03 | APRS | `completed` / `answer_generated` | stop | correct / verified | 8 / 0 | 12,318 / 9,482 | 0.0401968 / 0.5308416 |
| DLV6-04 | APRS | `stopped` / `model_request_budget_exhausted` | stop | unknown / unknown | 12 / 0 | 11,151 / 15,870 | 0.0597048 / 0.7962624 |
| DLV6-04 | APRS+CCL | `stopped` / `model_request_budget_exhausted` | stop | unknown / unknown | 12 / 0 | 13,968 / 8,202 | 0.0374208 / 0.7962624 |

状态为 completed 1、failed 4、stopped 3。实际 APRS 派发为 cold_start 19、explore 2、fallback_round_robin 14、gain 6。
本批已观察到 3 个自然触发 Run，裁决记录为 `independent_comparison_unknown` 1、`tied` 2。采纳 0 次。回灌后实际 gain 派发为 0 次，单步移除回灌信用后改变选路为 0 次。
批次请求上界 58，已知用量峰值估算 US$0.4792672，按预检上界扣减 US$3.8486016。

| 文件 | SHA-256 |
| --- | --- |
| `budget.json` | `302785924e541e3df6be0a5c6c49e40f0927b41b824af4eba9981939f01e856f` |
| `frozen-plan.json` | `a9a7702e0507985127d06b0326681fd38e3e0fd52dd49453ff44a4229fab0def` |
| `preflight.json` | `cbfbedc15a9fb2f5514ade8191cea1b9b3e3045d3fa5df04478ac410e75276c4` |
| `archive-manifest.json` | `06ecef65f0b13096068d60b69e82ebdf3bf10eec9befb5932bef1445fcc79e66` |
| `audit.json` | `fbe8a73bcb633e459f5e473d43bf2adad67136a8e5300f8b401e0be9ed43acff` |
| `selection-audit.py` | `a96d6be7a1209e99bf4a6731be975d7bf402e33bfd4fb53ba30ba2f60d1eaf15` |
| `selection-audit.json` | `e2f0ce34b7e9b32505ac510e8da095a72c72f00029961588771027c407728ceb` |

| Run ID | Run SHA-256 | Trace SHA-256 | 配置 SHA-256 |
| --- | --- | --- | --- |
| `run_7c4429ca56384973815b565dae4fa217` | `d8f1ff2882956918d74e14254ffeaef49aa19449f2408b0fef0d572972c4414a` | `449c0e655608049be6c54f8f17086584a1041a7a9b41217728078da386aff833` | `681bc4a7c1065122d0b589e94bfd9cdc5d605e120e79d77a8f7ab0324da0fc8f` |
| `run_6b0c6c2b688e41eea2eec701c91756ee` | `bf98d28984a0830e344549a5a7df2a855d867d2407edc63c6155ba8c94b93b20` | `5a70a80fd2a3ef15d7a4cedf209b1a958404892fa3bab946e04f7f8a2d3be607` | `0873ae3ca7917211cbfbbd3867e5b0340dcd6bdec7f597f9efeb67570f806478` |
| `run_6d1b162160d34aaf9bbf637dae7ccc2d` | `6e4582353f2668d0fe1cae494844a9649bd93565c4234d1e0105bed8b262c77d` | `46909f4b150c69c06d56047110f798d0990353fe37e74b3195a685972d908557` | `0873ae3ca7917211cbfbbd3867e5b0340dcd6bdec7f597f9efeb67570f806478` |
| `run_1b6efa7be2cc414281e2db8aebf8ecef` | `312a537585cae2cf221a9f7e5b7b80b7dc1f17aa71598d6d0e22c2001338bea9` | `afd8a6b956baf4dc6df6d12349b327b7fb803f2e57e4ae50a33cc21f1cd036f3` | `681bc4a7c1065122d0b589e94bfd9cdc5d605e120e79d77a8f7ab0324da0fc8f` |
| `run_6e9a4e7b9829436e87b48640f7736bc7` | `f2b4e540e5b84dedebf8cfb1c4fa7d68f59380425f54308e3398924a49cfa572` | `ef1405ac445c7c812deb16c4be4fa0f3b4ec0b6ee12f63d3537b5184909149dd` | `681bc4a7c1065122d0b589e94bfd9cdc5d605e120e79d77a8f7ab0324da0fc8f` |
| `run_e57590b85ec54b34ba8108e1736ee795` | `4462cf9583582570c0a07301ea868d12298dee274031ce23ec0f6a5216492d1b` | `3f909d0b8f2dd98ab463a69088bb2f4e1791d5e1c0d27f1d4085c970faede642` | `0873ae3ca7917211cbfbbd3867e5b0340dcd6bdec7f597f9efeb67570f806478` |
| `run_4ac13e7ae5df45d1b1b7b0c208d89065` | `c5fe7bba75e7d26c2a9f54d176197241b8aefb0de81875681b7b2022ede06565` | `a165cd60fd5c57fde447bc707746a1bb14c4619601b7f2d758748fc0a6eb8c64` | `0873ae3ca7917211cbfbbd3867e5b0340dcd6bdec7f597f9efeb67570f806478` |
| `run_2bacea861c214a0b949e74d963a42330` | `8642e7c8fc2803059a5c5f1df5a657a942f45b5265547d1b3b3fe3040b23297a` | `6aafa0da0a26e751be9dc51b6a672d78830dec19797cba394e29b900fdd120b2` | `681bc4a7c1065122d0b589e94bfd9cdc5d605e120e79d77a8f7ab0324da0fc8f` |

## ricl-dual-loop-20261126-v7

| 题目 | 条件 | Run 状态／停止原因 | 末次 Provider finish | 独立正确性／完备性 | 确认／未知请求 | 已知输入／输出 Token | 估算／授权扣减（US$） |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| DLV6-01 | APRS+CCL | `failed` / `preflight_rejected` | unknown | unknown / unknown | 3 / 0 | 1,062 / 18,433 | 0.0598352 / 0.2777088 |
| DLV6-01 | APRS | `not_run` / `—` | — | unknown / unknown | 0 / 0 | 0 / 0 | — / — |
| DLV6-02 | APRS | `not_run` / `—` | — | unknown / unknown | 0 / 0 | 0 / 0 | — / — |
| DLV6-02 | APRS+CCL | `not_run` / `—` | — | unknown / unknown | 0 / 0 | 0 / 0 | — / — |

状态为 failed 1、not_run 3。实际 APRS 派发为 cold_start 2。
本批已观察到 0 个自然触发 Run，裁决记录为 无。采纳 0 次。回灌后实际 gain 派发为 0 次，单步移除回灌信用后改变选路为 0 次。
批次请求上界 3，已知用量峰值估算 US$0.0598352，按预检上界扣减 US$0.2777088。

| 文件 | SHA-256 |
| --- | --- |
| `budget.json` | `31250ad797818862010f345357985f91b3804096eeb1a0e5c260375c97c4423a` |
| `frozen-plan.json` | `48de63bf7aae74cd2db8eb45e7b28ca48c7a952f22206e90590e81aa0754f91b` |
| `preflight.json` | `6b68a3b6937abf692e17fac197e6e1c455f128a219465dfe855ba5cf45afe6b0` |
| `archive-manifest.json` | `a666d2333bbc8db2852128e3708c97a442baca604c320bfd3346e06e75def778` |
| `audit.json` | `f75a5d30ec8b4b8ef18d27a0617ca069e9adbdb185d3dbb103472340af9af13b` |
| `selection-audit.py` | `a96d6be7a1209e99bf4a6731be975d7bf402e33bfd4fb53ba30ba2f60d1eaf15` |
| `selection-audit.json` | `9eb0c90768c7f3c81abe378c315ff221cc412eeb43e972eaf63597f2e248649a` |

| Run ID | Run SHA-256 | Trace SHA-256 | 配置 SHA-256 |
| --- | --- | --- | --- |
| `run_8b66746e318d45428723725f57339088` | `091232681070b33e3c78e758cdd8df0d273e7d6ea1d300ca1c2fa62bf6f840b5` | `05bc02edec84944d8aa784bac77d30a0096df8c2fff6b73e1a3c8db46b24f541` | `d480f0ee1e139d61cd689dfd959106303db0f5d209b1533dafd7b4a91bec87ed` |

## 验收与复算

全任务累计授权账本为 326/384 次、US$18.6171392/US$30。实付账单为 `unknown`。
分别在批次源码工作树运行对应批次目录的 `audit.py` 和 `selection-audit.py`。前者核对题目与独立答案键、根预算、Run 和 Trace。后者重算真实派发的单步决策。
#259 仍缺同一真实 Run 中回灌信用改变冷启动后实际选路的证据，保持开放。
#256 的真实撤销证据继续跟踪。[已归档的依赖与替代支撑复算](dependency-replay-v3-v5-evidence.md)。
