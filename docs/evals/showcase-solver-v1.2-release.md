# Solver Harness v1.2 发布验收

状态：验收进行中，`engineering-preview`。完整 live 发布被阻塞。

机器可检验的 [STAR AC/SC 最终归属矩阵](showcase-solver-v1.2-matrix.json) 覆盖 STAR AC-01..44 与 SC-001..043，每项只有一个最终责任 ticket。前置依赖以 [父规格 #32](https://github.com/RUSS0718/MathAgent/issues/32) 为准；测试 ID 对应实际 unittest 公开行为接缝。矩阵中的 covered 只表示有对应离线用例，实际执行结果在本记录收口时写入。

`scripted` 是脚本模型或模拟传输的离线工程证据；`replay` 是快照重放；`live` 是真实服务请求；`unavailable` 是所需能力没有充分证据。真实本地有限计算执行不等于真实模型工具选择，也不等于形式化证明。

[SH21 两次真实探针](showcase-solver-intern-live-sh21.md)共8次模型调用、0次工具执行，状态 needs_review；历史 v0.2 AC-06 真实 Intern 工具闭环仍为 unavailable。它与 STAR AC-06 的标签证据边界是不同验收项。[SH22 配对工程合同](showcase-solver-paired-report-sh22.md)和[SH20 零调用重放](showcase-solver-result-replay-sh20.md)不能替代 live 证据。本任务不再进行真实调用。

发布命令：`uv run python scripts/check_solver_release.py` 检查矩阵、文档链接、官方基线与离线范围；`--matrix-only` 仅检查归属和测试引用；`--require-live` 必须阻塞。工程门禁通过也不授权修改官方入口或合入 main。

本记录不宣称论文完整复现、完整形式化证明、数学正确率提升或真实策略收益。官方基线以根 BASELINE.json 的11个冻结文件为准，默认预算与输出合同不变。
