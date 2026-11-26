# RiCL Runtime 文档索引

从这里运行 RiCL Runtime、复跑离线配对并查阅真实先导证据。

## 当前 Runtime 入口

CLI 默认运行确定性离线端口上的单路线样例；`--population` 可运行两个预先给定候选路线的串行扩展样例：

```powershell
$runRoot = Join-Path $env:TEMP "ricl-runtime-smoke"
uv run python -m ricl_runtime --problem "Compute 2 + 2." --offline-answer "4" --output-root $runRoot

$populationRoot = Join-Path $env:TEMP "ricl-population-smoke"
uv run python -m ricl_runtime --population --problem "Compute 2 + 2." --offline-answer "4" --model-request-limit 2 --output-root $populationRoot
```

候选扩展样例可用 `--no-aprs` 运行普通搜索对照。两种模式复用相同候选路线与预算参数。命令打印结果 JSON，并在输出目录下写入 `run.json` 与脱敏 `trace.jsonl`。单路线独立核查支持整数加法和有限的实数一元根号方程。缺少适用判据时返回 `unknown`。[CLI 实现](../ricl_runtime/__main__.py)、[根号方程核查](../ricl_runtime/math_verification.py)

单路线使用 `--reasoning-state` 时，`run.json` 的 `derivations` 记录命题、推导、核查证据和目标。每条推导要求其全部前提在该作用域下仍有支撑。同一命题可以由多条推导分别支撑，最后一条适用支撑失效才会使下游推导和相应目标重新打开。下一请求携带仍适用的成果和待完成目标。Trace 分别记录实际送达的证据、模型明确报告引用的证据和独立复核导致的撤销。模型省略引用报告时，引用状态为 `unknown`。[共享推理状态规格 #256](https://github.com/RUSS0718/RiCL/issues/256)、[离线撤销与复用验收](../tests/test_runtime_scoped_derivations.py)

## 集成机制验收

运行聚焦离线验收：

```powershell
uv run python -m unittest discover -s tests -p "test_runtime_mechanism_integration.py"
```

该验收让 Baseline、RiCL-State、RiCL-Search、RiCL-Full 和 RiCL w/o Search 都经过 `Runtime.run`，并匹配问题、候选上限、模型、工具、候选生成与独立核查能力，以及请求、Token、时间和费用根上限。RiCL-Full 的 Trace 记录从关键失败触发的诊断、对照/处理臂、父状态合并，以及 APRS 本次选中的路线实际收到的合并证据与原父 Checkpoint；根预算在诊断和两臂派发之间持续生效。实验代码可通过 `run_mechanism_ablation` 写出版本化 Run 和脱敏 Trace；`public-input.json` 只保留输入哈希、匹配配置、产物路径与文件哈希，独立的 `evaluation.json` 提供可由 `summarize_mechanism_run` 重算的核查状态、Verified Gain、Token、无新证据扩展数与路线选择。Run 单独结算本地核查调用和实测耗时，不从模型未报告的用量推算 Token 或费用。无新证据扩展数不是正式指标定义。[集成规格 #259](https://github.com/RUSS0718/RiCL/issues/259)、[聚焦测试](../tests/test_runtime_mechanism_integration.py)

## 离线配对先导

在仓库根目录运行以下命令，使用固定的条件顺序种子。

```powershell
uv run python -m ricl_runtime.experiments --order-seed 17
```

输出目录 `artifacts/paired-pilot/pilot_*/` 包含 `pilot.json` 和每个 Run 的记录。两个算术夹具各运行五个主要条件和四个专项对照条件，共 18 个 Run。清单记录每题的条件顺序、共享预算、运行和验证状态、停止原因及产物路径。夹具用量用于检查账本，真实先导需要单独批准。[配对消融规格 #243](https://github.com/RUSS0718/RiCL/issues/243)、[离线矩阵实现](../ricl_runtime/experiments.py)

`pilot.json` 的 `rollback_pair` 指向另两个 Run。两个条件读取同一失败 Checkpoint，分别重推后缀和撤销失效的 AND/OR 依赖。配对记录以依赖状态核对回复中明确引用的依据，并记录夹具报告的返工输出 Token。[回退对照实现](../ricl_runtime/rollback_experiment.py)

## 真实 Provider 证据

获批的 DeepSeek 网关批次可显式使用 `--gateway-output-tokens 24576`。运行前按每次请求 US$0.0925696 的预检上界冻结共享预算。使用默认配置时，网关单次输出上限为 16,384 Token。

DeepSeek 与 MiniMax 分别用一次获批的真实请求完成了同一道整数加法校验。两次运行共用 CLI、ModelPort、独立验证和 Run 账本。记录包含请求与返回模型、供应商用量、阶段耗时和复跑参数。[DeepSeek smoke 记录](evals/runtime-deepseek-smoke.md)、[MiniMax smoke 记录](evals/runtime-minimax-smoke.md)

DeepSeek 真实配对先导完成九个矩阵条件和两个回退条件。证据记录列出共享预算、分支行为和剩余验证缺口。[配对先导记录](evals/runtime-deepseek-paired-pilot.md)、[批次与 Run 校验索引](evals/runtime-evidence-index.json)

校验索引包含四个批次的源码版本、可用的配置哈希，以及 Run、Trace 和批次清单的 SHA-256。文件路径相对于对应批次产物目录。拿到获准访问的产物后，按索引核对文件字节。仓库只发布校验信息。

### 研究方法 Pilot：原批与续批

2026-11-25 的 M2 与双循环 Pilot 共享源码版本 `588b2da388a6d850af7886c26f362716632d99d6`。原批因传输失败停止；续批以独立归档保存，没有覆盖原批。两批合计 24 个 Run（19 个完成、5 个失败）；按独立评价记录，22 个答案正确且完备，2 个未知。实付账单仍为 `unknown`，授权用量按预检上界计入 US$3.6929536。[实施地图及票据证据](https://github.com/RUSS0718/RiCL/issues/248#issuecomment-7165824444)

2026-11-26 M2 v2 的 6 对 / 12 Run 单独记录；所有 Run 完成并通过独立答案键与完备性复核，但 36 次派发均为 `cold_start`，没有策略决策机会。[M2 v2 证据、预算和脱敏文件哈希](evals/m2-real-20261126-v2-evidence.md)。

把获准访问的 `pilot-20261125` 和 `pilot-20261125-continuation` 两个目录放在同一父目录下。将下例中的 `./approved-archives` 换成该父目录：

```powershell
uv run python scripts/verify_runtime_pilot.py ./approved-archives
```

[固定校验锚点](evals/runtime-method-pilot-anchor.json)记录各归档的索引哈希、状态及预期文件数和 Run 数。核验器离线检查原批 40 个文件／15 个 Run 和续批 31 个文件／9 个 Run 的索引、文件字节、Run 身份、源码版本、配置哈希与对应 Trace，不读取受限答案键，也不调用 Provider。校验通过仅说明产物与锚点一致，不重判数学答案，也不把未触发的机制算作成功。

M2 v2 的 6 对运行均在冷启动阶段结束。双循环 v3 观察到自然关键失败、自主诊断、同源双臂裁决，以及拒绝回灌后的真实续接。状态复用已有真实送达和明确引用，实际撤销仍待观察。[双循环 v3 证据、费用与复算](evals/dual-loop-real-20261126-v3-evidence.md)。 [双循环 v4](evals/dual-loop-real-20261126-v4-evidence.md) 留有一个完整配对、一次持平裁决以及一次对照臂超时的记录。 [v3–v5 完整核心配对](evals/dual-loop-real-20261126-v3-v5-evidence.md) 记录一次真实回灌。后续冷启动派发读取回灌证据，父回复明确引用。 [回灌后选路的后续先导](evals/dual-loop-selection-follow-up-evidence.md) 记录匹配配对、扩额、失败与真实派发的复算。详见 [#256](https://github.com/RUSS0718/RiCL/issues/256)、[#257](https://github.com/RUSS0718/RiCL/issues/257)、[#258](https://github.com/RUSS0718/RiCL/issues/258)、[#259](https://github.com/RUSS0718/RiCL/issues/259)。

## 三项研究机制及当前状态

| 机制 | 范围入口 | Runtime CLI 状态 |
| --- | --- | --- |
| Shared Reasoning State | [已验证成果的存储与消费，#239](https://github.com/RUSS0718/RiCL/issues/239) | `--reasoning-state --model-request-limit 2` 记录后续请求引用的证据 |
| Causal Search Loop：固定候选 APRS | [APRS 排序，#240](https://github.com/RUSS0718/RiCL/issues/240) | 可通过 `--population` 观察排序 |
| Causal Search Loop：串行候选扩展 | [Population 扩展与选择，#241](https://github.com/RUSS0718/RiCL/issues/241) | 可通过 `--population` 观察两个固定候选的扩展与选择 |
| Counterfactual Control | [同源隔离分支与反馈消费，#242](https://github.com/RUSS0718/RiCL/issues/242) | 离线配对先导可观察触发、分支结果及父路线续接 |

三个机制分别指共享推理状态、因果搜索循环和反事实调控。搜索循环目前由两个单独的工作范围定义：先在固定候选集验收排序，再单独扩展和选择候选。路线图、代码存在和离线样例都不能证明真实运行参与或数学收益。

## 决策、实验与证据边界

- [研究型 Runtime 决策地图，#227](https://github.com/RUSS0718/RiCL/issues/227)、[起步范围决议，#234](https://github.com/RUSS0718/RiCL/issues/234)、[Runtime 规格，#236](https://github.com/RUSS0718/RiCL/issues/236)、[机制验收与证据顺序，#232](https://github.com/RUSS0718/RiCL/issues/232)记录目标、实现边界和证据等级。
- [单路线离线 CLI，#237](https://github.com/RUSS0718/RiCL/issues/237)及上方的 `uv run` 命令提供可重复的离线入口。该入口固定答案并使用有限整数加法判据；它不构成真实 Provider、机制参与或研究效果证据。
- [第二模型系列 #244](https://github.com/RUSS0718/RiCL/issues/244)记录 ModelPort 通用性验收要求。[旧资产退役 #246](https://github.com/RUSS0718/RiCL/issues/246)记录退役证据和人工决策要求。
- [开发门禁](engineering/development-gates.md)说明日常 Runtime 工作的差异、链接和聚焦命令检查。当前根目录 [AGENTS.md](../AGENTS.md) 是仓库工作约束入口。

## 归档

- [旧 Showcase 与竞赛文档索引](https://github.com/RUSS0718/RiCL/blob/8318be2a22122ebf9e33e6eef66691461c7c5255/docs/README.md)保留旧代码仍可定位时的导航。
- [退役清单与回滚依据](engineering/runtime-legacy-retirement-inventory.md)记录旧源码、容器、配置和数据的处置。
- [旧 Intern S2 配置](experiments/archive/intern-s2-campaign.json)用于追溯历史实验。正式 RiCL 实验的题集、重复计划和预算按 [#243](https://github.com/RUSS0718/RiCL/issues/243) 确认。
