# 14: 数学工具、执行证据与 easy-verify 预检

**What to build:** 可执行验证标签在送审前得到真实工具回执；工具错误、超时和不可执行状态不会冒充已验证。

**Blocked by:** #13

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] 工具调用经过权限、超时、输出大小和预算检查。
- [ ] `[easy-verify]` 的受支持计算得到输入、输出、状态和来源回执。
- [ ] 工具失败或不可执行时状态明确为失败/未执行，不写成 `verified`。
- [ ] Meta 执行代码或跨题访问的请求被拒绝并留下脱敏审计。
- [ ] CI 使用假工具，live 工具证据不在本 ticket 冒充完成。
- [ ] 支持 STAR AC-14、STAR AC-27 的工具错误分类和预检边界。
