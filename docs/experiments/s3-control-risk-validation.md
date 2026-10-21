# S3 #28 中断与恢复风险验证

状态：风险验证进行中；只使用离线 fake HTTP，未调用真实 API。

## 输入与边界

规格为 GitHub #23/#28；#27 已于 2026-10-21 关闭，基线为 b563246。
测试接缝已由任务授权：Flask Workspace Job、Run/Evidence，临时 SQLite、fake HTTP、确定性注册表。
官方 user_agent.py、implementations/、BASELINE.json 保持冻结。

## 风险验证

1. 在 fake HTTP 接收请求后阻塞响应，通过公开 cancel API 取消。
   原实现的取消报告 budget=null，不能审阅在途消耗（测试先红）。
   第一切片添加共享 action fence，取消后不再派发 planner 后续调用；报告立即显示一条 unresolved attempt，迟到结果不改变 canceled。
2. 旧 LiveAgentPipeline 是顺序调用，不能声称是 checkpoint 恢复。改为 LangGraph 节点调度角色，SQLite saver 保存原 thread 的 checkpoint；Workspace 仅投影状态。
3. 节点内 HTTP/工具动作可能已完成、checkpoint 尚未提交时进程退出。重启时 active Run 一律 needs_review，不自动 replay。只有显式 waiting_input 的安全 LangGraph interrupt 可 resume。
4. checkpoint 仅含完成角色的公开输出和工具结果，不保存模型 messages、prompt、raw response 或隐藏 reasoning。公开报告不导出 checkpoint。

## 实施与退出条件

- action 前后控制检查 → cancel/deadline 迟到响应合同通过。
- LangGraph 的原 thread checkpoint 恢复 → 已完成 planner 不重跑，预算累计、deadline 不重置。
- 重启 ambiguous → needs_review 可查，resume 被拒绝，保留预留。
- 并发控制、SSE 断线与报告 → 终态单调、报告与 Evidence 保留账本。
- 聚焦测试、全量 offline、release、Ruff、pre-commit 顺序运行，并审查官方文件 diff。

仅工程合同通过不代表真实远端请求可撤销或数学能力提升。
