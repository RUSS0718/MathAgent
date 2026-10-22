# 21: 真实 Intern 适配与 live 工具闭环

**What to build:** 使用真实 Intern S2 和显式预算，验证模型请求、工具执行、结果续接与 Evidence 关联形成可追溯的 live 闭环。

**Blocked by:** #14, #16

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] 复用现有 Intern 适配器的传输、重试和用量语义，只补 Solver 需要的角色与会话字段。
- [ ] 在固定公开题上取得可复核的真实请求、工具执行和结果续接证据。
- [ ] 每次真实调用有显式预算、模型身份和调用身份。
- [ ] 失败、超时、截断或无工具请求的样本保留，不删除。
- [ ] 没有 live 证据时 `v0.2 AC-06` 保持 unavailable/needs-review。
- [ ] 支持 SC-019 的真实用量合同；本 ticket 不改变离线 CI 的网络边界。
