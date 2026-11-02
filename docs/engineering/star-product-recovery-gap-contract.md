# STAR 恢复缺口验收合同

状态：实施前合同。基点 `25aaca1`。责任：SP13 最终复核中的 AC15/32，及 AC39/40 公共反例；不解锁完整模式。

确认接缝继承 #56：认证 ChatSession/Job、公共 resume/Run/report/Evidence/SSE，经现有 Adapter、S3 与 Solver；不另建求解循环。

1. 在 Traceback 归档事务提交前/后真实子进程 `os._exit`，重启公共 resume 复用原 Verifier 回复/归档，不丢失败历史、不重复旧接受或计费。数学快照与归档同事务，没有可分裂的半提交；分别覆盖事务两侧。
2. checkpoint Solver revision 不存在或任务不匹配时公共 resume 拒绝；不得按猜测续算。只允许checkpoint落后且该revision确实存在。
3. 服务端显式注入可流式 Intern Adapter；默认原Adapter不流式。SSE delta在索取下一片前经原 calls._consume 持久化；正常完整包严格schema后才能归一化。timeout/进程退出保留unknown/原预留，默认零重发，显式新ID才允许。
4. 流式公开证据只发布字节/片段数量和状态，绝不公开partial prompt/隐藏推理文本。出站计量使用原S3，工具/模型调用上限不改变。
5. 同等级候选 `x=1` 与 `x=2` 的真实矛盾公共回放稳定；注入0.95概率字段由严格提供方schema拒绝或在公开输出剥离，不能显示校准概率。

先RED再最小实现，聚焦恢复/Adapter/最终绑定/预算/候选回归，不跑全量/live。文档记录故障注入与真实进程退出，非live效果。
