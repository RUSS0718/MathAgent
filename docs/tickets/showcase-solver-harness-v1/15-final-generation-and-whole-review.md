# 15: 最终生成与独立整题审查

**What to build:** 全部步骤完成后，新 Verifier 会话按原题检查最终答案；拒绝时有界重试，失败或不可用时返回准确的未验证状态。

**Blocked by:** #09, #11

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] 最终生成使用所有仍有效的接受结果，不读取失效结论作为前提。
- [ ] 整题审查使用新会话并检查原题对应、完整性、跨步骤逻辑和输出格式。
- [ ] 拒绝后按配置和预算有限重试。
- [ ] 审查不可用但仍有候选时返回 `completed_unverified`。
- [ ] Verifier 意见与可选 Meta 风险意见分别记录。
- [ ] 支持 STAR AC-13、STAR AC-30 的最终审查与来源隔离。
