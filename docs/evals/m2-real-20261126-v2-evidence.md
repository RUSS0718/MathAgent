# M2 真实配对先导 v2 · 2026-11-26

## 范围与复算

本记录只覆盖批次 `m2-real-20261126-cap16k-timeout180-v2`，不与此前停止批或 2026-11-25 的双循环批次合并。6 道独立留出题按冻结顺序组成 6 对 APRS / Round-Robin，共 12 个串行 Run。题目 ID、来源/自编归属或许可状态、题目版本、配对顺序及评价侧答案键在冻结计划中分离保存；此处不公开题面、答案键或 Provider 消息内容。CCL 与工具调用关闭。

在受控原始归档目录运行 `uv run python audit.py` 可从 Run、Trace 和独立答案键重新计算下表。2026-11-26 本地复算成功，12 个计划项均结算，汇总产物 SHA-256 与归档前一致。原始 Run/Trace 留在忽略的受控归档目录；下表公开聚合结果和文件哈希，不把原始对话载荷提交到源码仓库。

## 冻结配置

| 项目 | 冻结值 |
| --- | --- |
| 集成源码 | `11023a0536e7618fe00423873717033f9e9078ca`（Git 树 `9236b925d6f04ce42553bab07fc561da9ea3e543`） |
| Provider / 模型 | `https://code.aigcpro.org/v1` / `deepseek-v4.1-flash` |
| 每 Run 上限 | 12 请求、393,216 Token、900 秒、0 工具调用 |
| 请求传输与输出 | 180 秒传输超时、16,384 输出 Token 上限；无自动重试 |
| 预检费用上界 | US$0.0663552 / 请求；US$0.7962624 / Run；12 Run 共预留 US$9.5551488 |
| APRS 配置 SHA-256 | `0873ae3ca7917211cbfbbd3867e5b0340dcd6bdec7f597f9efeb67570f806478` |
| Round-Robin 配置 SHA-256 | `88f86e36a3ce71546b9b21f822aca59c4e93dba4ec5d5987a0d7776be6777572` |
| 冻结计划 SHA-256 | `853be902df58ed472bd734e8f4d2f9118de2ea2d1a78d33ef2e404199da2a9f0` |
| 冻结公开输入清单 SHA-256 | `e24756bcc9ef5ddf16986d1731b82ba0d2bf2d033cd376965ff2fab6e8d68fa6` |

6 对按冻结规则交替先运行 APRS 或 Round-Robin。每个 Run 均独立生成 3 个候选；每对的两臂候选 ID 无交集，候选顺序不同。两臂共享模型、候选生成上限、独立核查能力及相同的 Run 预算。

## 观察结果

| 指标 | APRS | Round-Robin | 合计 / 说明 |
| --- | ---: | ---: | --- |
| 计划 / 结算 / 完成 Run | 6 / 6 / 6 | 6 / 6 / 6 | 12 / 12 / 12；失败、停止、unknown、未执行均为 0 |
| 独立答案键正确 | 6 / 6 | 6 / 6 | 12 / 12 |
| Runtime 独立验证及解集完备 | 6 / 6 | 6 / 6 | 12 / 12 `verified` |
| 冻结目标 / 有效 Verified Gain | 24 / 24 | 24 / 24 | 48 / 48；零归因收益 Run 为 0 |
| 实际 Provider 请求 | 24 | 24 | 48；无用量未知 Run |
| 已知输入 / 输出 Token | 17,351 / 91,220 | 18,244 / 102,740 | 35,595 / 193,960；总计 229,555 |
| 已知用量费用估算 | US$0.30578480 | US$0.34336320 | US$0.64914800；非实付账单 |
| 计入总授权的预检上界 | US$1.5925248 | US$1.5925248 | US$3.1850496；每个已确认请求均按冻结上界计费 |
| 实付账单 | unknown | unknown | unknown |

共记录 24 次有效证据送达和 24 次明确引用。每对均生成 3 个候选，实际发生 36 次路线派发；36/36 决策均为 `cold_start`，且 Trace 中每项决策都关联到其后实际送达的 Provider 请求。冷启动后的派发为 0。APRS fallback 计数/分母为 0/0，频率不适用；本批未观察到 APRS 收益选路、探索或固定轮转，也不能据此声称策略相同、有效或无效。未观察到支撑撤销、自然关键失败或合并；CCL 已关闭，因此本批不构成 CCL 触发率观察。

独立答案键和完备性评价均为 12/12 正确/verified。此为 6 个配对单元的描述性结果，不构成主效果、因果或普遍性证据。候选生成发生差异，但调度决策没有离开冷启动，因此策略效果尚未被本批检验。

## 完整性摘要

| 产物 | SHA-256 |
| --- | --- |
| `budget.json` | `061a971c403bc196d8f327575e997ab7c36d04289aa81592e823c4a5ab51bfd2` |
| `execution.json` | `c4501c3a08ccd3374b8a2ff79c786743acb276383ad5c50c4aa18ce217948ed1` |
| 复算 `audit.json` | `099659c03632c5784eeec976825833b86615c8f04a42164610c08eb83ec2ee12` |
| 脱敏 `audit-summary-redacted.json` | `108da557d93cc85bc0f7e0f62e288db7f52d88fdf0dc8a308e3e3477bce1b47d` |

下表为受控归档中每个 Run 与 Trace 的文件 SHA-256。Run ID 可与归档对应；题面、答案键及消息正文没有在此复制。

| 配对 | 条件 | Run ID | `run.json` SHA-256 | `trace.jsonl` SHA-256 |
| --- | --- | --- | --- | --- |
| M2V3-01 | APRS | `run_80dc55bcace4423fb9f3a396f299268b` | `67b65c3d31cd3c2b70862e7cf9358e8c2e3cf7d7468a1b6ad1894a0af939b4a3` | `8e0fff77fb95fc83d09ecc0b7f0ce6683c30cafc0cc3b5fa7a5346349c9a66a6` |
| M2V3-01 | Round-Robin | `run_fb5e700bdd304693a373ed1e897be0e4` | `1e24a3db8c75c7a2832b4a85ce1c9e0bfeeba75cd5f32b168b83d9e7eccc9400` | `ed9f72b29b7643f541ee5831c2e1725b54566c0d906d035796cdce07d3c58cb8` |
| M2V3-02 | Round-Robin | `run_c9d4c502a75f4ab09a2bc421dd338087` | `c2b85788c2b63f20421cfbb179f636ea470ded4d734992858674c0e1d9ba1aed` | `31588125373fe680466b384e9942befacd81f6eb969eac38154d14654b61dec6` |
| M2V3-02 | APRS | `run_4f717c1781354d30a986cdcf29112c4b` | `38ab496ed0e1fbaa8c20e6ecf35c7149b5bcb648aa313d80696fc198e90ba4c5` | `934995a3ee087b8f12b22d38ee50b55f3e403f3eb4ad9f514608692221d2be10` |
| M2V3-03 | APRS | `run_fe1df3158ea54db3aba32f65f853282c` | `83af0a02d0558f72c0b3aaf72f4ddda37130c81287c4853c0fd3b91d9f9aaf90` | `cc4df694e08afa7a92637a62bdde973829973fca0356d5fd17417d51f69163e5` |
| M2V3-03 | Round-Robin | `run_bbf2371a3ec248ff81a5760c33f48f53` | `d0ac68ba1292fc45446ad656cc295c37cf8fcd5f530b013db41b7f9200394344` | `676c8a70182f7b7154bdd77cb3370a4173e24f09da914c74f8c2a955ed87b7d9` |
| M2V3-04 | Round-Robin | `run_2c96f4dab4af47718a340625d1f522e8` | `ad64ad8a3afa004b0773640ca437448003aaa88903f3270f73e2663910c54478` | `e787e0cbaa9557d32638be0372a5594b507987d7eaa4ddc3ff2e24350e573152` |
| M2V3-04 | APRS | `run_e8bdd75aaaa94d7bb456cbd11d5df3dc` | `48b71459ad02a563b304b80c52124925d477966db08b644905fdbf4456509d88` | `07ac0459a3d900850c82d9ff3bcda9a80cd18003d3e7681742b5b560922d04d5` |
| M2V3-05 | APRS | `run_3fe7efb998f0456cb630f652c0e261ff` | `a207b26efc36b798491f85d9a57bf8750e07311d5e1fab5f6382ebbbf0a06701` | `07b79d600c5be3db41ea927d475e54d7b41626fc43fb4c78a91781ffd67b2e30` |
| M2V3-05 | Round-Robin | `run_02c7aa2594cc4d87931ef1a49fe62b6f` | `83892380960cca93219c3af66dbbf850aa4b57cdd9541c793c36dac28acfbcad` | `c8e7b66f77f2f0af0a34939f39fa3d727379805a4500123be1b1cd853b365a9e` |
| M2V3-06 | Round-Robin | `run_77219959ce7f4fee9548f90f8ae0f73a` | `abdf933f5856254e90ddf156ace220b0c4e9f971c0f3f189f195f388f93cb762` | `9ccdce015fda36b3d7011ebdd63cee4d0e36f879c7ca127152972228165139fb` |
| M2V3-06 | APRS | `run_d259bc75a377462fb9ffc98cc942a79e` | `4fbaac17b86ae81389c3737817d847e340fa0e391e21d4d53159f404f73936ed` | `d913fdcff4eda090042cb0e9d5da6be1db1b54e30f6fb5b76acadcf9c299312d` |

## 票据边界

- #257：本批完成 6 对 / 12 Run，交付了覆盖、收益、成本、候选差异、逐决策到请求关联及失败/unknown/未执行统计。AC6 的可复核记录验收完成；因冷启动后派发数为 0，不对 APRS 自适应行为或策略效果作结论。
- #256：本批没有支撑撤销，不能验证撤销传播与局部复用。
- #258 / #259：本批关闭 CCL，不能验证自然关键失败、自主诊断、同源双臂、裁决、回灌及回灌后的派发；真实双循环仍待获批凭证可用后续跑。
- #250：正式比较协议、样本与论文主张仍不在本 Pilot 验收范围内。

独立预算账本记录授权上限与各批消耗；本批按 48 个已确认请求计 US$3.1850496，已知用量估算 US$0.64914800，实付账单 `unknown`。该 Pilot 未触及总授权上限。
