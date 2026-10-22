# MathAgent 产品事实

本分支服务数学智能体的本机主观评测展示。用户通过 ChatSession 输入数学问题，观察 Job/Run 的执行状态，阅读公开数学报告，审阅配对实验与 Evidence。工作区提供会话、运行观察、设置、配对实验和运行详情；独立 Demo 与旧 Showcase 入口仍可使用。

依据根 AGENTS.md、GLOSSARY.md、accepted ADR 0004/0006 与前端 accepted 重设计，当前边界是本机单用户产品，不是公网多租户服务。官方 `user_agent.py` 与产品侧隔离；新增展示能力不得改变默认官方调用路径或预算。运行数据进入被忽略的 artifacts 目录。

公开界面只呈现脱敏步骤、状态和摘要，不呈现凭证、完整 prompt、隐藏推理或隐藏答案。fake、replay、live 等模式必须可区分；运行完成和检查通过不等于通用数学正确性。能力提升只能由独立可复现评测支持。

视觉事实与复现流程分别见 [DESIGN.md](DESIGN.md) 和 [UI 复现指南](docs/frontend/ui-reproduction-guide.md)。当前版本范围与证据状态以 [文档索引](docs/README.md) 为入口，本文不扩展产品范围。
