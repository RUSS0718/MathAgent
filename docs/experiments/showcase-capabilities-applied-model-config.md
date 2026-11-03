# Showcase applied model config response

`GET /api/capabilities` adds an `applied_model_config` field. The field reports the active STAR adapter configuration used by this Showcase server. Existing response fields remain unchanged.

## Version 1 schema

The projection has this exact top-level allowlist:

```json
{
  "schema_version": 1,
  "status": "available",
  "model": {
    "name": "intern-s2",
    "thinking_mode": true,
    "temperature": 0.2,
    "max_output_tokens": 512,
    "request_timeout_seconds": 60,
    "retry": 0
  },
  "solver_modes": ["star_limited", "star_limited_best_effort"],
  "verification_modes": ["auto", "required", "off"],
  "transport": {
    "policy": "legacy",
    "profile_set_fingerprint": "<64 lowercase hexadecimal characters>"
  },
  "config_sha256": "<64 lowercase hexadecimal characters>"
}
```

`model` contains only the active model name, thinking mode, temperature, output-token limit, request timeout, and retry count. If the adapter has no thinking-mode override, the server reports the active client's value. `solver_modes` and `verification_modes` list the modes enabled by this server. `transport.policy` is `legacy` or `stream_first`; its fingerprint identifies the configured stream-profile set.

Version 1 requires the exact keys shown. `schema_version` is the integer `1`; `status` is `available` or `unavailable`. An available model uses a nonempty string name, a Boolean thinking mode, a finite nonnegative temperature, positive integer token and timeout limits, and a nonnegative integer retry count. Mode arrays contain unique strings. `transport` contains only the policy and a 64-character lowercase hexadecimal fingerprint.

`config_sha256` hashes the UTF-8 canonical JSON for all other projection fields. Canonical JSON uses sorted keys, compact separators, and unescaped Unicode. The digest does not include itself.

The projection contains no credentials or private database data. The route sends `Cache-Control: no-store`.

## Unavailable configuration

When the server cannot resolve every required setting from its active adapter and client, it returns `status: "unavailable"`, `model: null`, `transport: null`, and empty `solver_modes` and `verification_modes` arrays. It does not construct a lazy provider client to produce the projection. It still returns the schema version and digest.

Experiment preflight rejects a missing, malformed, unavailable, stale, or mismatched projection. The CLI reads this projection before preflight and checks it again before creating a session or dispatching a Job.

The public response contract is tested in `tests/test_showcase_experiment_public_api.py`.
