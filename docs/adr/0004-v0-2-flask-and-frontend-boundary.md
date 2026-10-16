# V0.2 Flask 兼容入口与数学工作区前端边界

**状态：accepted**  
**日期：2026-10-16**  
**范围：V0.2 Showcase 产品侧**

v0.2 需要直接承载 CausalAgent 普通工作区的会话、Job 和 SSE 合同，因此将现有 Showcase 入口迁移到 Flask，并把 MIT 授权的 `chat-frontend` 搬入 `showcase/frontend/chat-frontend/`。迁移保留 v0.1 的 `/health`、`/api/runs`、JSON events、resume 和 Evidence 响应语义，再增加兼容工作区的 Job/SSE 路由；前端移除因果图、RAG、搜索和管理员入口，官方 `user_agent.py` 不导入产品侧代码。

这样保留旧 Demo 的回归边界，同时让数学工作区拥有自己的源码、构建和安全渲染责任。代价是产品侧需要维护一套前端构建和 MIT 来源记录，Flask 依赖也只能进入 Showcase 环境。
