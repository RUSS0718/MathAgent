# Glossary

- **official profile**：只运行根 `user_agent.py` 和当前官方 baseline 的模式。
- **showcase profile**：面向主观评审的产品模式，允许持久化、事件流、搜索、工具和回放。
- **research profile**：实验性多 Agent、长期记忆、沙箱或 RSI 模式。
- **AuthSession**：把一次请求绑定到本地身份的认证会话；它决定请求能否进入工作区。
- **ChatSession**：用户可见的一段数学对话容器，包含问题、答案和它们对应的运行记录。
- **Run**：一次隔离的数学任务执行，拥有唯一 ID、状态和产物。
- **Job**：用户可观察、可恢复的一次运行控制对象；它表示任务当前是否排队、执行、等待输入或已经结束。
- **Stage**：Run 内可恢复的阶段，例如 intake、planning、solving、verifying。
- **Evidence Pack**：答案、解释、验证、来源、工具调用和事件摘要的导出包。
- **Baseline**：官方 88/12/0 评测对应的字节和行为基线，不等同于普遍能力保证。
- **研究基础设施阶段（S1–S6）**：Intern S2 实验与 Showcase 的有序工程准备阶段；区别于 R1–R5 算法方向，以及 v0.2 Workbench 文档中含义不同的 S1–S4 阶段。
