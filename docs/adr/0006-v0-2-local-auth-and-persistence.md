# V0.2 单用户 AuthSession 与本地持久化

**状态：accepted**  
**日期：2026-10-16**  
**范围：V0.2 Showcase 产品侧**

v0.2 先服务本机单用户演示，不引入注册和公网账号体系。后端自动创建一个本地用户，使用 HttpOnly、SameSite=Lax 的 `AuthSession` Cookie 和 CSRF token 保护状态变更；logout 只清当前 Cookie，新的认证会话仍能访问原有 `ChatSession`。运行历史、事件、checkpoint、幂等记录和附件统一持久化到可配置的 `artifacts/showcase-v0.2/` SQLite 目录。

这个选择让刷新、重启、回放和现场演示可以复现，同时保留未来替换为多用户身份层的边界。它不代表当前产品具备公网多租户安全能力。
