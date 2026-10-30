# #99–#102 组合发布验收

日期：2026-10-30，Asia/Shanghai。范围为安全重试、纯序列化修复候选、持久化恢复与离线诊断 runner 的组合工程验收；未派发真实 provider 请求。

## 固定来源与实际结果

验收源码为 `a2aa83ab3e69bb6e89438ea0f5155466613c54f8`，tree 为 `1944be15b1d50e334f6b3fd226d7d6d88b0f9df6`，分支 `showcase-star-timeout`。门禁开始和结束源码一致且工作树干净。本文随后以文档提交记录，生产字节不变。

| 检查 | 结果 | 原始证据 |
| --- | --- | --- |
| 19 个旧失败责任模块 | 189 项，833.292 秒，OK，零 skip/expected-failure | `artifacts/issues-99-102-recovered-20261030-48fb7df0/related.log` |
| require-reference release | 1097 项，1536.281 秒，OK，`showcase_release=PASS`，零 skip/expected-failure | `artifacts/issues-99-102-validation-20261029-5cfb17a7/release.log` |
| 改动 Python 文件 Ruff | exit 0，`All checks passed!` | 同目录 `changed-ruff.log` |
| 固定基点至验收源码 diff check | exit 0 | 同目录 `diff-check.log` |
| 官方 baseline | 11 个文件 SHA256 匹配 | 同目录 `state.json` |
| 固定隔离镜像与实际 Reference | `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d linux/amd64`；Reference 门禁实际运行 | 同目录 `state.json`、`release.log` |
| 最终身份 | HEAD/tree 同上，`final_dirty=false`，全部步骤 exit 0 | 同目录 `state.json` |

运行目录名中的 `20261029` 来自既有 launcher 命名；实际 release 于 2026-10-30 09:45 启动，10:11 结束。uv PID 19920 创建于 `2026-10-30T01:45:17.5358731Z`，gate PID 28620 创建于 `2026-10-30T01:45:17.6611244Z`。进程已经结束，不再把状态文件当存活证据。

实际入口为 `uv run --offline --no-sync python -u <外部release-gate> <新产物目录>`；gate 执行 `scripts/check_showcase_release.py --require-reference`，随后执行改动文件 Ruff、diff check 和最终身份核验。`--offline` 是 uv 禁止依赖联网选项，本次没有重复执行仓库 offline 门禁。C 盘启动时约 7.80 GiB，TEMP/TMP 仅对检查子进程指向 `D:/CodexEvidence/MathAgent/release-temp-a2aa83a`。

## 工单映射与审查

- #99：逐 attempt 有界安全重试、预算准入、ReadTimeout 零自动重发，见[专属证据](star-safe-retry-99-acceptance.md)。
- #100：完整可见回复隔离、严格同值序列化修复、每请求根一次持久额度和无工具权限，见[专属证据](star-format-repair-100-acceptance.md)。
- #101：真实回执持久恢复、重复执行防护和当前裁决来源校验，见[专属证据](star-recovery-101-acceptance.md)。
- #102：不可变登记、fake-only 账本批次及只读监控，见[专属证据](star-diagnostic-102-acceptance.md)。真实 provider 派发入口不属于该票。

组合审查和修复覆盖修复谱系、当前裁决来源、监控 SQLite 首读、processing deadline 早唤醒、Job 证据收集前后投影一致性以及七个时序 fixture 的起算边界。最终增量的 Spec 审查为独立审查，0 finding；Standards 按用户指定由主聊天审查，0 finding，明确为非独立。原先被策略拒绝的审查未重试或计为通过。外部报告保留于 `C:/Users/CQX/.codex/issues-99-102-{79e0460,a2aa83a}-{spec-review,standards-main-review}-20261029.md`，前序范围另有相应固定源码报告。

## 历史失败与限制

旧 `89c18fe3-release` 的 1097 项中 60 fail、13 error，保持失败。旧 offline 虽有 unittest OK，但缺完整 wrapper 成功标记，不认证为完整通过。旧 358 focused 只属于 `c45d59c`，440 次重复执行只属于 `1599cbc`，均不换标为本次源码证据。

`48fb7df0` 的 189 项通过后，release 预检因 C 盘约 3.35 GiB、低于 5 GiB 门槛退出；该次预检失败保留。用户恢复空间后才启动本次 release，未重复 related，未降低测试断言、预算、空间门槛或跳过要求。磁盘耗尽和 Docker 故障是已确认环境异常，但不能断言所有旧失败均由环境造成。

日志中的 late-settlement 和隔离预检失败输出包含受控负例，最终以完整测试汇总、退出码与门禁标记核验；不据此声称真实远端已取消。运行 raw 留在 ignored artifacts，公开文档不包含凭证、完整 prompt、答案库或隐藏推理。

默认官方路径与默认预算不变，新增候选仍需显式启用。本次不证明真实 provider 兼容、数学能力提升或 #97 通过。#103–#110 仍需按依赖新登记和分别验收，P/T/R 未通过不得接入候选或启动后续完整 STAR 批次；unknown 保留原身份、预留和 deadline，零自动重发。并行维护提交 `67c2a08` 未纳入本次源码，需独立审查，不能覆盖本次冻结身份。
