# SP-04 产品集成验收合同

状态：已获授权实现，公共离线验收已通过，待集成复核。父规格为[#56](https://github.com/RUSS0718/MathAgent/issues/56)，本票为[#60](https://github.com/RUSS0718/MathAgent/issues/60)。公共验收使用现有认证Job入口、Run读取、SSE、报告和Evidence；只替换InternChatClient的HTTP传输为有限scripted回复，不直接调用Harness作为产品验收。

Success: Explore's four assessments cause actual bounded next role actions; structurally illegal plan never reaches Reasoner; both gates control step advancement; accepted step appears once; no job succeeds before fresh whole review. Same Run/job identity, persisted event decisions, public outcome, and independent actual outbound count prove each transition. Evidence_kind scripted/fault_injection must remain explicit; zero live calls.

## Files / ownership

Read SP03 integrated tip before writing: reuse its trusted features/ports/Registry/controller and shared S3/control/context. Primary ownership: solver_harness/star_routing.py, plan_generation.py, planning.py, plan.py, verification.py when regression demonstrates need; additive structured public projection in star_product_pipeline or SP03's extracted equivalent; focused tests/test_star_product_planning.py plus docs/engineering/star-product-sp04-contract.md and docs/evals/star-product-sp04.md. Do not duplicate SP03 dispatch/guard/budget or invent solver loop. Only minimal UI needed for actual hint selection/provenance if ticket requires public selectable hints; root alignment before API expansion.

## Vertical TDD slices (one failing public test then minimal patch)

1. Route evidence and rejection fallback: scripted Explore SOLVED -> polish -> whole REJECT -> legal one-step Planner -> Reasoner -> valid StepVerifier -> final-generation/review as existing trusted controller enables. Assert outbound role order and planner.exploration_findings contains original polished discovery; no success before final whole review ACCEPT. Expose allowlisted durable route fields needed to inspect assessment and verdict. Existing SOLVED+whole ACCEPT remains regression with zero planner.
2. Partial route: PARTIALLY_SOLVED -> Meta PLAN -> Planner (no second Explore); separate RETRY -> second PARTIALLY_SOLVED -> Planner, <=2 Explore, <=1 partial Meta at cap. NEED_PLAN and UNKNOWN each immediately Planner, no polish/whole review of absent candidate. Check original findings included in request, public decision, persisted state revision survives reopen without calls.
3. Plan validity/repair: first duplicate-ID plan -> second valid plan, exact version1 preserved and repair_attempt1. Two invalid plans (duplicate, forward/self dep, >20 steps), including malformed JSON response separately: <=2 planner calls, zero Reasoner, failed/needs_review. Repair carries previous invalid response and concise structural failure (no unlimited retries). Valid plan contains nonblank title/objective, unique nonempty IDs, earlier deps and 1..20 steps. Assert actual request step objective matches plan's goal.
4. Gates / acceptance: two-step plan; first YES/PASS/ACCEPT dispatches next step exactly once. Contradictory NO/PASS/ACCEPT, PARTIAL/PASS/ACCEPT, YES/FAIL/ACCEPT and YES/UNCERTAIN/ACCEPT do not dispatch second Reasoner and never succeed. Durable event exposes system-derived valid=false and exact gate enums; accepted evidence has source/dependencies and llm_reviewed at most. No fake tool evidence. Validate immutable accepted step not duplicated in SSE/reopen (do not add resume behavior; SP08 owns it).
5. Labels/hints: forged verified label/refs downgraded; easy-verify without receipts never tool_verified/formally_proved. Optional `solver_hint` accepts nonblank text up to 2000 characters only for `star_limited`; it is stored for execution, included in the idempotency digest, and passed to Planner. `meta_auto` hints use the same size bound. Public events expose only `hint_source` (`none`, `user`, or `meta`); Job/Run DTOs, SSE summaries, reports, Evidence and chat history do not expose hint text. `solver_options` remains rejected. The default hint mode is `none`; legacy requests without a hint keep their existing request digest and call path.
6. Budget stop: trusted SP03 fixed bounded profile exhausted before Planner or StepVerifier -> no prohibited dispatch, no completed status, original S3 totals/deadline retained. Use existing supported budget injection seam, not new public budget settings. Update limited-mode identity/summary only for mechanisms actually wired; full modes remain rejected.

## Public event contract

Add allowlist only: assessment,round,next_phase,decision category,actual step_id,plan_version,goal_gate,logic_gate,verdict,valid,trace_back_to and categorical hint source. Avoid raw plan/report/argument/prompt/call response or unrestricted dict copy. Mathematical snapshot remains Solver authority, Job/Run projection retains revision and stable event ID. Existing dedup transaction handles exactly-once public projection.

## Acceptance / release checks

Focused new tests plus existing SP02 product Jobs; related Harness routing/plan/verification and SP03 controls. Then uv run python scripts/check.py --offline and uv run python scripts/check_showcase_release.py sequentially once; avoid duplicate full suites if release invokes offline (inspect runner first). Ruff changed Python, git diff --check, frozen BASELINE file diff. If UI changes, npm ci/audit/check + current browser regression and relevant added UI behavior. Record real results, known gaps and no capability claim from scripted tests. Commit logical vertical slices with Chinese conventional subjects and Refs #60. Before report, merge integration branch tip into worker; root merger owns final integration.

The public Job fixture uses the real Harness, product controller, Adapter and shared S3 controls. Its provider transport is fault-injected with finite replies. Do not claim live-provider behavior from these tests. No UI hint field is required by #60, so the Workbench frontend does not expose the private planning hint.

The current loopback authentication model has one fixed `local-user`. Public requests without an auth cookie return 401; a second authenticated owner cannot be created through the public API. Do not seed user rows directly to claim cross-owner isolation.

SP-04 does not add a standalone solve loop and does not close SP-05 challenge, SP-06 trace-back/re-plan, SP-08 recovery, SP-09 Python tools or SP-10 final-answer binding.
