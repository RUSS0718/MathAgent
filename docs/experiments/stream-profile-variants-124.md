# #124 流式 Profile 变体与传输拒绝合同

状态：accepted（用户已确认）

## 范围

- 保持旧的 `{"call_id", "profile_fingerprint"}` stream-first manifest call 形式不变。
- 仅允许 `stream_first` 使用替代的 `{"call_id", "profile_fingerprints": [...]}` 形式；两种字段不能同时出现，也不能都缺失。
- `profile_fingerprints` 必须是非空、无重复、合法 SHA-256 值，且每个值都属于 frozen profile set。每个 role/call_id 仍只有一个 manifest entry。
- preflight、public adapter matching 和 independent verifier 只接受该 role 的 frozen allowed list 中实际选中的 fingerprint；实际匹配仍校验 exact endpoint/model/thinking/temp/output/message-shape/schema。
- 新增一个已完成真实 probe 的静态 profile：`researcher` / `counterexample_check` / message shape 5 / InternS2 / endpoint `https://chat.intern-ai.org.cn/api/v1/chat/completions` / temperature `0.2` / `max_output_tokens=32768` / thinking `false`。证据目录：`C:\Users\CQX\.codex\worktrees\issue127-provider-readiness\Challenge-Cup-2026\artifacts\issue124-counterexample-probe-20261103`；`registration_sha256=5810cee527273621175289b51fd79688640b1766c853ba22f48a6194e3d33308`，`schema_fingerprint=9806bf844a1871e77a826e802027f93929767e99a7bd3bc1366318abf4be7590`，`profile_fingerprint=c533d7e24d63633c1b4418e51cc1412c552bffb4dd51195ba87d2173f6fce406`。registration SHA、schema fingerprint 和 profile fingerprint 是不同字段；只记录证据 hash，不提交 raw response。普通 `researcher` profile 与该变体在同一 role 的 allowed list 中分别登记。
- transport identity 在已知 policy rejection 时保留此前成功 call，并可增加根级 rejection：`call_id`（public alias）、`role`、固定 `reason`、`new_run_required: true`。未知 transport 不得被改写为已知拒绝。
- public runner/adaptor 对已知拒绝停止为 `transport_policy_rejected`；independent verifier 对已知拒绝返回 `FAIL`，而不是 `UNKNOWN`。
- 正常成功 root schema、旧 manifest entries、官方 baseline、Best-Effort 默认关闭和 `tests/test.md` 保持不变；不新增 framework/catalog/plugin/mode 或 action schema。

## 验收

- `validate_manifest` / transport preflight：旧 singular 和新 list 均通过；both、neither、empty、duplicate、unknown fingerprint 均拒绝。
- regular 与 counterexample schema 在同一 role 的 allowed list 中均可通过；错误实际 fingerprint 失败。
- public adapter / experiment run：已知拒绝不产生额外 HTTP，且此前成功 call 保留。
- `verify_experiment_run` / public projection：已知拒绝产生白名单 stop reason 和 `FAIL`，不把拒绝误报为 `unknown_transport`；未知或伪造拒绝仍失败关闭。
- 运行相关 focused tests 与 `ruff`；不运行 provider calls 或 broad full suite。
