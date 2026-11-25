<p align="center"><strong>English</strong> · <a href="README.zh-CN.md">简体中文</a></p>

# RiCL Runtime

RiCL Runtime is the repository's Python entry point for research on mathematical reasoning. It runs single problems and records independent verification, resource use, and a redacted trace. The former Showcase and official-scoring implementations are retired from this branch; historical evidence remains in the documentation and Git history.

## Run the offline single-route CLI

From the repository root:

```shell
uv run python -m ricl_runtime --problem "Compute 2 + 2." --offline-answer "4"
```

The offline port replays the reply supplied by `--offline-answer`. The CLI writes `run.json` and a redacted `trace.jsonl` under `artifacts/<run_id>/` by default. Use `--output-root <path>` to choose another location.

### Check a radical equation

```powershell
$reply = @'
{
  "answer": "Solution set: {3}",
  "checks": [
    {"kind":"necessary_conditions","radicand_lower_bound":"-6","rhs_lower_bound":"0"},
    {"kind":"candidate_constraint","coefficients":["1","-1","-6"],"direction":"forward"},
    {"kind":"candidate_coverage","candidates":["-2","3"]},
    {"kind":"original_equation_filter","accepted":["3"],"rejected":["-2"]}
  ]
}
'@
uv run python -m ricl_runtime --problem "sqrt(x+6)=x" --offline-answer $reply
```

The single-route verifier covers supported integer addition and equations of the form `sqrt(a*x+b)=c*x+d` with rational coefficients and positive slopes. For these equations, it freezes equal-weight goals before the first request and uses exact rational arithmetic to check the domain, the squared constraint, its rational candidate set, and substitution. A local check can be `verified` while completeness is `unknown`. The Run records certified completeness and whether it matches the final solution set stated in the free-text answer. The independent model review field remains `unknown` in this offline example. Cases outside the exact criterion remain `unknown`. Use `--model-request-limit` to set the Run's request cap.

### Replay online route search

Provide the candidate proposal first and then one reply per expansion. The root request limit includes the proposal. This example reuses `$reply` from the radical equation above.

```powershell
$candidates = '{"candidates":[{"strategy":"Find the domain first."},{"strategy":"Derive and filter the squared candidates."}]}'
$step = '{"answer":"The exact checks are available in shared state.","checks":[]}'
uv run python -m ricl_runtime --problem "sqrt(x+6)=x" --online-search aprs `
  --model-request-limit 3 --offline-answer $candidates --offline-answer $reply --offline-answer $step
```

Use `--online-search round_robin` to replay fixed rotation with the same request limit. The Run records the candidate opportunities, active goal credit, token usage, and the request ID for each selection. Offline replies leave model token usage `unknown`.

Enable online intervention with `--counterfactual`. To replay a checked failure on the first request, set `--model-request-limit 5` and pass five `--offline-answer` values in dispatch order. Provide the failed solve increment, a diagnostic JSON object with `hypothesis` and `strategy`, the control and treatment increments, then the parent continuation. The trace records whether the pair was admitted and which verified evidence reached the continuation. [#258](https://github.com/RUSS0718/RiCL/issues/258)

The integrated mechanism acceptance runs Baseline, RiCL-State, RiCL-Search, RiCL-Full, and RiCL w/o Search through one `Runtime.run` entry with matched model, tool, verifier, candidate-generation, and root request/token/time/cost limits. It checks that a verified state update changes APRS inputs, a current critical failure admits one source intervention within those limits, and the continuation request goes to the newly selected APRS route and receives the merged evidence, with the parent route recorded in the trace. Run records count local verification calls separately and preserve measured elapsed time; they do not infer provider cost or token use that the model port did not report. The experiment-side `run_mechanism_ablation` helper writes `public-input.json` with hashes, matched capabilities, configurations, and artifact links, and a separate `evaluation.json` with recomputable verification, Verified Gain, token use, route expansions without new evidence, and route selections. The latter count is an offline observation, not a protocol-approved search-waste metric. [#259](https://github.com/RUSS0718/RiCL/issues/259)

## Runtime mechanisms

| Mechanism | Offline entry point | Scope |
| --- | --- | --- |
| Shared Reasoning State | `--reasoning-state --model-request-limit 2` | Records evidence references in later requests. [#239](https://github.com/RUSS0718/RiCL/issues/239) |
| Causal Search Loop | `--population --model-request-limit 2`; add `--no-aprs` for plain search | Serial candidate expansion and APRS ranking. [#240](https://github.com/RUSS0718/RiCL/issues/240), [#241](https://github.com/RUSS0718/RiCL/issues/241) |
| Counterfactual Control | `uv run python -m ricl_runtime.experiments --order-seed 17` | Offline paired branches and feedback-consumption fixtures. [#242](https://github.com/RUSS0718/RiCL/issues/242) |
| Integrated ablation | `uv run python -m unittest discover -s tests -p "test_runtime_mechanism_integration.py"` | Five Runtime conditions, source intervention, shared accounting, and experiment-side evidence. [#259](https://github.com/RUSS0718/RiCL/issues/259) |

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
