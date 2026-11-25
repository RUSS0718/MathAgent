<p align="center"><strong>English</strong> · <a href="README.zh-CN.md">简体中文</a></p>

# RiCL Runtime

RiCL Runtime is the repository's Python entry point for research on mathematical reasoning. It runs single problems and records independent verification, resource use, and a redacted trace. The former Showcase and official-scoring implementations are retired from this branch; historical evidence remains in the documentation and Git history.

## Run the offline single-route CLI

From the repository root:

```shell
uv run python -m ricl_runtime --problem "Compute 2 + 2." --offline-answer "4"
```

The offline port returns the answer supplied by `--offline-answer`; it does not solve the problem with a model. The independent verifier covers only supported integer-addition prompts. Other prompts have no applicable criterion and are recorded as `unknown`. By default, the CLI writes `run.json` and a redacted `trace.jsonl` under `artifacts/<run_id>/`; use `--output-root <path>` to choose another location.

## Runtime mechanisms

| Mechanism | Offline entry point | Scope |
| --- | --- | --- |
| Shared Reasoning State | `--reasoning-state --model-request-limit 2` | Records evidence references in later requests. [#239](https://github.com/RUSS0718/RiCL/issues/239) |
| Causal Search Loop | `--population --model-request-limit 2`; add `--no-aprs` for plain search | Serial candidate expansion and APRS ranking. [#240](https://github.com/RUSS0718/RiCL/issues/240), [#241](https://github.com/RUSS0718/RiCL/issues/241) |
| Counterfactual Control | `uv run python -m ricl_runtime.experiments --order-seed 17` | Offline paired branches and feedback-consumption fixtures. [#242](https://github.com/RUSS0718/RiCL/issues/242) |

Offline fixtures demonstrate only the behavior they exercise. They do not establish live-provider reliability, general mathematical correctness, or research gains.

## Read next

- [Documentation index](docs/README.md) for the CLI, paired fixtures, experiment evidence, and archived history.
- [DeepSeek paired-pilot record](docs/evals/runtime-deepseek-paired-pilot.md), [DeepSeek smoke](docs/evals/runtime-deepseek-smoke.md), and [MiniMax smoke](docs/evals/runtime-minimax-smoke.md).
- [Development gates](docs/engineering/development-gates.md) and [repository instructions](AGENTS.md).
- [Runtime specification #236](https://github.com/RUSS0718/RiCL/issues/236), [mechanism evidence order #232](https://github.com/RUSS0718/RiCL/issues/232), and [retirement record #246](https://github.com/RUSS0718/RiCL/issues/246).

## Focused offline checks

```shell
uv run ruff check ricl_runtime tests
uv run python -m unittest discover -s tests
uv run python -m ricl_runtime --help
uv run python -m ricl_runtime.experiments --order-seed 17
```
