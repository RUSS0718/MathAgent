# S3 #28 中断与恢复风险验证

状态：风险验证与工程闸门已通过。只使用离线 fake HTTP，未调用真实 API。

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


## 风险退出证据

- `uv run python -m unittest discover -s tests -p "test_run_control*.py"`：11 项通过。
- cancel / deadline / 重启不明 / 安全 checkpoint 恢复 / HTTP retry / 工具 continuation / 并发 resume / SSE 断线 / 迟到 usage 均通过公共 Job、Run、Evidence 合同检查。
- LangGraph 的 terminal 节点与持久 terminal seal 记录原 thread 的终态；seal 固定 checkpoint ID，迟到节点写入不能覆盖它。并发控制以持久 Job/Run 终态赢家决定 seal。
- HTTP/tool 预算 reservation 是动作准入的线性化点，与 cancel 的 SQLite 写事务互斥；已准入动作按在途处理。网络调用期间不持有 SQLite 锁。cancel 只停止后续调度，不宣称撤销远端请求。
- 安全 waiting_input interrupt 在服务重启后保留并可恢复；其他 active checkpoint 进入 needs_review，公开 resume 返回 409。Job 保留兼容的 failed 状态，error/event 与 Run 的 NEEDS_REVIEW 明示待复核。
- Run 终态冻结 ended_at 与 wall_time_seconds；waiting_input 不冻结，原 deadline 继续生效。迟到 provider usage 可继续结算。
- 并发计量回归先在旧实现复现：应累计 20 provider tokens，旧 freeze 的整行回写却仅留下 10。改为 JSON1 单字段条件更新后保留 20、reserved_tokens=0。
- 官方 user_agent.py、implementations/、BASELINE.json 的差异为空。

## 最终工程闸门

验证代码提交：`f49ca22`（已经合入集成分支 `d595ef9`）。二轴代码复核发现的终态 checkpoint、并发 seal 赢家、Run/Job waiting 状态和并发 usage 丢失问题均已修复；后续复核无新增问题。

以下检查依次执行，没有并行运行全量检查：

- `uv run python scripts/check.py --offline`：157 tests 通过（109.687s）；workspace_contract、contract_test_seams、repository_check 均 PASS；Demo/Showcase help 成功。
- `uv run python scripts/check_showcase_release.py`：showcase_release=PASS。
- `uv run ruff check showcase tests`：All checks passed。
- `uv run pre-commit run --all-files`：所有适用 hooks 通过；check-json 因无匹配文件跳过。
- `git diff --check`：通过；官方 user_agent.py、implementations/、BASELINE.json 的差异为空。

本记录仅证明离线工程控制合同，不证明真实 provider 请求可撤销、费用精确已知或数学正确率提升。
