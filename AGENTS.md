# RiCL Research Repository

## Research boundary

- Use one Python-owned core for the main solve loop and a distinct, separately controlled auxiliary verification/intervention loop; both share the Run budget. Python controls state, scheduling, and termination, while the model supplies mathematical reasoning and strategy proposals. This first slice stays single-route and adds no model-driven auxiliary call.
- The former official-scoring and Showcase implementations are retired from this branch. Keep their archived evidence separate, and do not reintroduce dependencies on those paths into Runtime.
- Treat a generated answer as free text. Record independent verification status and scope separately; use `unknown` when no applicable independent criterion exists. A successful run, valid JSON, or model self-review is not mathematical verification.
- Persist only research Run data needed for reproduction: source revision, config snapshot/hash, problem and condition IDs, result, status/stop reason, model/reasoning settings, shared budget/use and measurement sources, and a redacted trace. Never store credentials, complete prompts, or private reasoning. Keep generated data under ignored `artifacts/`.
- `tests/test.md` is user-managed: never read, modify, stage, or delete it.

## Working and validation

- Use `uv run` for Python. Read `GLOSSARY.md` and only the ADRs/contracts relevant to the changed boundary; keep detailed policy in its source document and link to it rather than duplicating it here.
- Run the narrowest tests that cover the changed Runtime seam, then the applicable offline CLI acceptance command below. Expand validation only when the change crosses another boundary; frontend, browser, release, and full-repository gates are not defaults for Runtime work.
- Offline fixtures prove only the behavior they exercise. Never issue a live Provider request without the human approval gates below.
- Follow the repository's [commit convention](docs/engineering/commit-convention.md); preserve unrelated work and inspect the final diff.

## Human approval gates

- First Provider/model and local credential selection, plus bounded real-request data and budget approval: [#238](https://github.com/RUSS0718/RiCL/issues/238). No secret values in chat or Git.
- A second model family and its credentials after the first bounded validation: [#244](https://github.com/RUSS0718/RiCL/issues/244).
- Formal paper protocol (data rights, baselines, sample/repetition plan, metrics, statistics, and fair budget): [#243](https://github.com/RUSS0718/RiCL/issues/243).
- Retirement of legacy assets only after an itemized impact/rollback inventory and explicit approval: [#246](https://github.com/RUSS0718/RiCL/issues/246).

## Read by task

- Terms: [GLOSSARY.md](GLOSSARY.md). Research scope and accepted decisions: [#236 runtime specification](https://github.com/RUSS0718/RiCL/issues/236), [#231 single-route contract](https://github.com/RUSS0718/RiCL/issues/231), and [#232 mechanism evidence order](https://github.com/RUSS0718/RiCL/issues/232).
- Profile isolation: [ADR-0001](docs/adr/0001-profile-separation.md). Lightweight independent verification: [ADR-0003](docs/adr/0003-experimental-python-tool-and-lightweight-verifier.md) and [ADR-0010](docs/adr/0010-r3-typed-verification-unknown.md). Provider transport: [ADR-0015](docs/adr/0015-provider-transport-business-boundary.md).
- Agent-instruction guidance: [OpenAI Codex](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra), [Claude Code](https://code.claude.com/docs/en/best-practices), and [GitHub Copilot](https://docs.github.com/en/copilot/concepts/prompting-and-context/custom-instructions).

## Offline acceptance

```powershell
uv run python -m unittest discover -s tests -p "test_runtime_cli.py"
uv run python -m ricl_runtime --help
uv run python -m ricl_runtime --problem "Compute 2 + 2." --offline-answer "4"
```
