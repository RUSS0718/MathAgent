# STAR 产品集成执行合同

状态：执行中，未完成产品验收。规格为 [#56](https://github.com/RUSS0718/MathAgent/issues/56)，用户于 2026-10-23 确认实现全部规格。

## 集成基点与边界

- 集成分支：`showcase-star-product`。
- 开发基点：`606d874fcee11bc161d68aa001cd706de63afbe2`。
- 状态职责：[ADR-0014](../adr/0014-star-product-state-and-recovery.md)。
- 官方冻结文件、默认调用预算和输出合同不变；新增入口显式开启。
- 现有未跟踪文件 `tests/test.md` 不属于本次交付。

## 依赖图与验收归属

| 切片 | 工单 | 前置 | 本片退出证据 |
| --- | --- | --- | --- |
| SP-01 | #57 | 无 | 固定来源、全部 SC/AC 映射、公共恢复窗口与隔离风险验证 |
| SP-02 | #58 | #57 | 真实 Job 纵切、严格模式校验、统一任务身份；SP-AC-01/02 |
| SP-03 | #59 | #58 | 共享准入、结算、取消与 deadline；SP-AC-03/04 |
| SP-04 | #60 | #59 | Explore、合法 Plan、双 Gate；SP-AC-05/06/07 |
| SP-05 | #61 | #60 | 连续 Challenge、有界升级；SP-AC-08 |
| SP-06 | #62 | #61 | 依赖失效、救援、重规划；SP-AC-09/10 |
| SP-07 | #63 | #62 | 角色记忆、七类 Skill、MetaGuidance、受限研究；SP-AC-11/12/25/26 |
| SP-08 | #64 | #63 | 安全续算、显式未知重试；SP-AC-13/14 |
| SP-09 | #65 | #59 | 隔离 Python、可核验产物和预检；SP-AC-15/16/17 |
| SP-10 | #66 | #63、#65 | 整题审查与 S4 实际文本绑定；SP-AC-18 |
| SP-11 | #67 | #64、#66 | 候选历史、硬预算后零调用和重放；SP-AC-19/20 |
| SP-12 | #68 | #67 | Workbench 全生命周期与故障交互；SP-AC-21 |
| SP-13 | #69 | #68 | 独立复核、反旁路、真实验收与发布门禁；SP-AC-22/23/24 |

工单正文为逐票验收合同；本表仅记录调度关系。SP-03 通过后，SP-09 可与 SP-04 起的机制链并行。失败的风险验证返回设计，不跳过前置工单。

## 切片执行与验证

每票在基于集成分支的独立 worktree 中由实现子代理负责。先写失败用例或可执行验收，再做最小实现；聚焦检查、相关回归与 diff review 通过后提交。实现分支合入最新集成分支后，由合并子代理集成。

最高层验收经现有认证、ChatSession、Job/Run HTTP、控制、SSE、报告和 Evidence；不得另建仅供验收的求解循环。每个机制记录同一 Run 的触发、决策、实际动作、持久状态及用户结果。scripted、故障注入、live、replay 分开记录，未触发与缺失不计作通过。

真实 API 批次已获用户授权。每批执行前另存硬预算，保留实际用量、失败和 unknown；不自动重试未知远端结果。运行 raw 写入被忽略的 `artifacts/<run_id>/`，提交只含脱敏报告与可复现入口。

最终检查包括：

- `uv run python scripts/check.py --offline`
- `uv run python scripts/check_showcase_release.py`
- 前端目录内 `npm ci --no-audit --no-fund`、`npm audit --audit-level=high`、`npm run check`
- 官方冻结文件差异、依赖与干净环境入口检查
- 集成分支标准/规格审查及固定上游一致性独立复核

所有票的实际验收与发布门禁通过后才关闭对应工作；历史工单、helper 测试和 Demo 可运行均不能替代能力证据。
