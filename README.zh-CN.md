<p align="center"><a href="README.md">English</a> · <strong>简体中文</strong></p>

# RiCL Runtime

RiCL Runtime 是仓库中用于数学推理研究的 Python 入口。它运行单题任务，并记录独立验证、资源用量和脱敏 Trace。旧版 Showcase 与官方评分实现已从当前分支退役；历史证据仍保留在文档和 Git 历史中。

## 运行离线单路线 CLI

在仓库根目录运行：

```shell
uv run python -m ricl_runtime --problem "Compute 2 + 2." --offline-answer "4"
```

离线端口重放 `--offline-answer` 提供的回复。CLI 默认将 `run.json` 和脱敏后的 `trace.jsonl` 写入 `artifacts/<run_id>/`，也可以用 `--output-root <path>` 指定目录。

单路线独立验证覆盖受支持形式的整数加法，以及斜率为正有理数的 `sqrt(a*x+b)=c*x+d`。运行在首次请求前冻结等权目标，并用精确有理数核查定义域、平方约束、有理候选集和原式代回。Run 分别记录局部核查、解集完备性、自由文本答案与解集的匹配，以及独立模型复核。超出精确判据的情况记为 `unknown`。可用 `--model-request-limit` 设置一次 Run 的请求上限。[根号方程离线示例](README.md#check-a-radical-equation)

## Runtime 机制

| 机制 | 离线入口 | 范围 |
| --- | --- | --- |
| Shared Reasoning State（共享推理状态） | `--reasoning-state --model-request-limit 2` | 记录后续请求引用的证据。[#239](https://github.com/RUSS0718/RiCL/issues/239) |
| Causal Search Loop（因果搜索循环） | `--population --model-request-limit 2`；添加 `--no-aprs` 可运行普通搜索 | 串行扩展候选路线并进行 APRS 排序。[#240](https://github.com/RUSS0718/RiCL/issues/240)、[#241](https://github.com/RUSS0718/RiCL/issues/241) |
| Counterfactual Control（反事实调控） | `uv run python -m ricl_runtime.experiments --order-seed 17` | 离线配对分支与反馈消费夹具。[#242](https://github.com/RUSS0718/RiCL/issues/242) |

离线夹具只证明其实际覆盖的行为，不证明真实 Provider 稳定性、一般数学正确性或研究收益。

## 接下来阅读

- [文档索引](docs/README.md)：CLI、配对夹具、实验记录与归档历史。
- [DeepSeek 配对先导记录](docs/evals/runtime-deepseek-paired-pilot.md)、[DeepSeek smoke](docs/evals/runtime-deepseek-smoke.md)及[MiniMax smoke](docs/evals/runtime-minimax-smoke.md)。
- [开发门禁](docs/engineering/development-gates.md)与[仓库指引](AGENTS.md)。
- [Runtime 规格 #236](https://github.com/RUSS0718/RiCL/issues/236)、[机制证据顺序 #232](https://github.com/RUSS0718/RiCL/issues/232)及[退役记录 #246](https://github.com/RUSS0718/RiCL/issues/246)。

## 聚焦离线检查

```shell
uv run ruff check ricl_runtime tests
uv run python -m unittest discover -s tests
uv run python -m ricl_runtime --help
uv run python -m ricl_runtime.experiments --order-seed 17
```
