# Faithful S01 browser recovery acceptance

## Scope

This acceptance covers the public browser seam for a persisted Job, its SSE event stream, page refresh, stream reconnection, and an unknown solver call. The fixture uses real Chromium against the local Vite app and Playwright controlled API responses. It provides browser presentation and request-boundary evidence only; it does not exercise a real provider or claim an end-to-end service recovery result.

Same-key POST response-loss recovery remains a backend acceptance owned by the lead agent and is outside this record.

## Acceptance cases

| Case | Browser assertion |
| --- | --- |
| Initial run review | The persisted failed Job and unknown call are presented with the explicit retry action. |
| SSE interruption and replay | The first event response ends; the browser reconnects with `Last-Event-ID: 1`. Replayed ID 1 is not rendered twice, and new events advance the timeline. |
| Page refresh | Reload reads the existing Job/report and subscribes to its events. It does not POST a new Job or resume the unknown call. |
| Explicit event reconnect | Reconnect uses the visible event cursor and performs GET requests only; replay does not produce a new Job or resume POST. |
| User-selected unknown retry | Only clicking the explicit action sends resume. The request keeps `unknown-call` as the original reference and supplies a distinct UUID as `new_call_id`. |

## Execution and evidence

The single browser invocation ran this spec together with the existing `star-recovery.spec.ts` in Chromium, using the repository's configured Vite and legacy test servers:

```powershell
npm run test:browser -- --config playwright.config.ts tests/browser/star-recovery.spec.ts tests/browser/faithful-s01-recovery.spec.ts
```

## Result

3 tests passed in 15.2 seconds: the new recovery scenario and the existing 320px and 1440px unknown-retry cases. The new scenario observed the cursor-based SSE reconnect, deduplication of the repeated event ID, refresh without create/resume POSTs, GET-only explicit reconnect, and a user-triggered retry with the original unknown call reference plus a distinct new UUID.

The configured Python web server ran `uv run` with `UV_PROJECT_ENVIRONMENT` unset. Its log shows that uv created the ignored worktree `.venv` and installed 81 project dependencies, although the supplied D: environment exists. The generated environment was removed after the run; no package manifest or dependency lockfile changed. This does not affect the browser assertions, which use controlled API responses.

Evidence is limited to Chromium presentation and request behavior against controlled API fixtures. Provider-live behavior, real service recovery, and same-key lost-POST recovery were not exercised.
