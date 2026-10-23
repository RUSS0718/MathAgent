# SP-02 implementation and acceptance contract (prepared; gated by SP-01)

Ownership: feat/star-sp02-job-bridge, based on showcase-star-product; only SP-02 product bridge, mode identity, initial selector and public tests/docs. No official baseline changes.

1. Add strict optional solver_mode to existing Job request; legacy remains default. star_limited explicitly identifies missing full-reference mechanisms; star_reference/star_best_effort fail closed until all actual product prerequisites (including corrected isolation evidence) are independently enabled. Unsupported ablation/unknown mode/invalid verification combination rejects before enqueue and HTTP dispatch. Include selection in idempotency identity.
2. Connect a focused bridge to existing WorkspaceService pipeline dispatch. Existing S3 bind_budget/bind_control remains outer authority, InternModelAdapter owns model+attempt reservations. Harness uses same job_id and shared SQLite path, never creates RunService duplicate. Enable actual Explore -> same-session polish -> fresh whole review, no standalone acceptance solver loop.
3. Project allowlisted committed Solver revision/event IDs and phase/status into same Job/Run/SSE/result. No prompt or raw invocation exposure. Preserve selected identity on queue/start/failure/result. Incomplete mechanisms remain needs_review, never succeeded by fallback text. Unknown calls never automatically retried.
4. Add minimal accessible selector and display of selected mode/missing capabilities in existing frontend, keep legacy UI flows.

Agreed seams: authenticated POST/GET Job, same-ID GET Run, events/report/Evidence; controlled actual InternChatClient transport with independent outbound request count and request content inspection. TDD per vertical slice.

Acceptance: invalid/full mode zero outbound and no accepted Job; controlled solved/polish/ACCEPT gives exactly three outbound requests with original problem and exact polished review candidate; same persisted run identity/revision and report answer survive app reopen without new outbound calls; REJECT or malformed response cannot become reviewed success; shared ledger actual count matches outbound count; legacy tests unchanged. Browser renders selector and mode identity with zero errors; frontend check and relevant unittest suites pass. SP-03+ richer control/recovery remains explicit gap, no full capability claim.
