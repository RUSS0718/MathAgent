# #185 按需求解阶段记录

2026-11-15；起点 `d4bed8a`，最终源码及阶段门禁待冻结。#185、#183、#168 仍开放。
要求和未闭合边界见 [策略合同](../engineering/adaptive-solving-185-contract.md)。

## 当前实现

- 显式 `adaptive_solving` 配置，省略保持原策略；直接候选不固定 polish，独立整题审查保留。
- 具体数学异议一次局部修正，每份候选独立 call/event 身份；拒绝消费标记覆盖结论提交前后两个恢复窗口。
- Planner 接收原失败候选、真实异议和未解决义务，并在已有请求中审查分解质量。
- 串行搜索状态区分完整规格、有效已证内容和实际工具输入/输出；排除重复身份、猜想、心跳和重复回执。
- 规格依赖语义错误接入既有一次协议修复；unknown 不自动重发。修复普通 solve 省略 metadata 时的 AttributeError。
- 高预算示例和公开策略摘要已接线；并发/形式化仍按既有能力准入。

## 已有必要离线证据

证据目录 `artifacts/issue-185/`（忽略产物）。`run_unittest_report.py` 通过声明数量执行：

| 接缝 | 证据 | 结果 |
| --- | --- | --- |
| 直接候选 / 一次修正 | direct-red-02、direct-green-02、boundaries | 红后绿；早期命令参数错误和夹具问题不算有效红证据 |
| 受影响 intake/config/final binding/budget | affected | 35 项通过 |
| 原串行路线边界 | routes | 19 项通过 |
| 已完成审查恢复 | recovery-red-02、recovery-green | 原失败到修正后通过；另覆盖已提交拒绝的恢复窗口 |
| 省略可选 metadata | metadata-red、metadata-green | 实际 AttributeError 红后绿 |
| 公开策略字段及只读刷新 | projection-red、projection-green | 红后绿；零刷新派发 |
| 猜想重复身份 / 不同输入同输出 | context-red、context-green | 2 项先失败后通过 |
| 真实发现的悬空规格依赖 | intake-red、intake-green、public-final | 公共 Job 红后绿；最终 3 项含未知修复结果不重发 |

双轴静态审查发现的恢复及搜索指纹缺陷已逐项修复并送复查；不算独立执行测试。
最终门禁尚未运行，不以聚焦检查代替阶段退出。

## 真实运行

`live-01` 首题 `run_035226c8ad49f22abe80610d44b9b512`：真实答案 5，独立常识核对一致；
整题 accepted、same_artifact，adaptive corrections=0，4 HTTP/模型调用，0 工具。
包含机器证明权限澄清前后两次规格处理，后续 Explore→整题检查，无固定 polish/Planner。
原观察器把 waiting_input 当结束，保留原 waiting 记录；按用户输入的普通证明意图回答 no，
继续原 Job，原预算/截止不变。恢复脚本第一次因已存在目录退出，未派发新调用。
本地计账 178964，provider usage 全部未知、0 unresolved，不能称实际消耗 178964 token。
根墙钟约333秒包含本地观察器停止期间，不当作模型计算耗时。

第二题 `run_5f013baf79fe7ff8c215b1cfe7dcf799`：1 次完成请求后 problem_intake_invalid_spec，
具体为 prerequisite_ids 引用未声明辅助目标；没有求解或答案。
保留失败，不重发旧 Job；触发本次协议修复接线。原第三题未派发。

针对修复的新普通输入与原计划深度案例留 `live-02`；当前 not_run。
高预算实证、规划/修正自然触发、深度正确交付、完整资源保障仍未验收。
旧 unknown、deadline 和历史失败均不改写；不声称正确率或总体效率提升。
