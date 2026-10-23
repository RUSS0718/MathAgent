# SP-12 持久运行审阅合同

基点25aaca1，归属#68/SP-AC-21。公开接缝由#56确认：认证Job/Run、SSE、报告、Evidence及控制；浏览器仅替换外部提供方HTTP，不mock产品API。

- 公开投影仅白名单计划序号、步骤Gate、归档/重规划计数；不公开内部ID、prompt或证明原文。HTTP失败用例先验证持久摘要存在。
- RunReview展示模式与证据类别、阶段版本/预算、候选版本/失效/选择、最终审查历史与工具回执scope；无数据明确说明。模式可用性以服务端capabilities为准。
- 已有报告不出现错误空态；显式恢复后store允许新代际，过期事件不得覆盖。先unit/browser RED，再最小实现。
- 真实Flask+SQLite+S3/S4+InternChatClient到本地有限HTTP提供方，验证刷新/重连/导出/replay/并发读取不新增请求，恢复和取消由真实控制接口驱动；四档宽度/隐私/可访问性/错误检查。

退出：聚焦Python、前端check/audit、真实browser证据及差距记录、官方冻结无差异、最新集成合入；全量Python与最终live由SP13统一执行。
