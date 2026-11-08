# Faithful 实施入口与前置核验

日期：2026-11-07（Asia/Shanghai）。本文件保留实施起点核验快照，不作为当前阶段待办。2026-11-08 已完成 S01–S03 工程退出，当前入口见[文档索引](../README.md)；完整发布与能力结论分别查看对应验收记录。

## 来源与工作区

- 实施总票：[#146](https://github.com/RUSS0718/MathAgent/issues/146)。
- 阶段合同：[#144 resolution](https://github.com/RUSS0718/MathAgent/issues/144#issuecomment-6703147321)。
- 调用生命周期细化：[#135 resolution](https://github.com/RUSS0718/MathAgent/issues/135#issuecomment-6686145136)。
- 完整并发增量：[#155 resolution](https://github.com/RUSS0718/MathAgent/issues/155#issuecomment-6704660319)。
- 审计基线：`b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6`。
- 本次实际起点：`e6b6b8919ac266694c36eb0205e5f79fb3ef3953`。
- 集成分支：`mathagent-faithful`，隔离工作树开发，不搬运原工作区未提交文件。

起点相对审计基线有 138 个文件差异，469 行新增、6874 行删除，包含上下文、事件、工具与恢复相关代码和测试。这个差异不能解释为这些能力已经通过或全部失效，必须在实际起点逐项核验。复核命令：

```powershell
git diff --stat b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6 e6b6b8919ac266694c36eb0205e5f79fb3ef3953
git diff --name-only b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6 e6b6b8919ac266694c36eb0205e5f79fb3ef3953 -- user_agent.py implementations requirements.txt
```

第二条命令无输出。原工作区保留的未提交修改包括 `GLOSSARY.md`、`docs/README.md`、两份已有评测记录与一份未跟踪评测记录。`tests/test.md` 为用户保留文件，不读取、修改或提交。

## 开工判据

S01 → S02 → S03 → S04；S05 等 S01、S03；S06 等 S03、S05。F1 等 S03、S04。不能以决策票关闭、旧 SP 测试存在或快速门禁通过代替这六项新阶段验收。

每个纵切按以下顺序执行：

1. 写出公共接口的失败验收，记录实际失败。
2. 最小实现，显式启用新行为，保留旧 Run 和默认行为。
3. 聚焦回归、相关完整检查，保留失败和 skip。
4. 审查差异和官方隔离边界，提交一个逻辑变化。

起点核验时首个确认缺口属于 S01：流式 Adapter 将客户端 timeout 用作整次请求绝对截止，当时尚无新合同所需的显式版本化活跃/首包/空闲策略和 1300 秒虚拟时钟证据。该历史缺口及下表状态均对应原起点，后续退出证据见文档索引。

## S02–S06 静态证据核验

独立只读审计对实际起点及 `b7038798` 的代表性源码、测试和历史验收文档进行核对，没有运行测试。`git rev-list --left-right --count b7038798...e6b6b89` 为 `57 0`：实际起点是审计基线的祖先。以下“未验收”表示没有找到满足新退出条件的实现与证据组合，不能由旧同名阶段或 Issue 关闭替代。

| 切片 | 可复用证据入口 | 新合同缺口与当前结论 |
| --- | --- | --- |
| S02 | `context_injection.py`、`sessions.py`；`test_solver_harness_sessions.py` | 未见版本化 ContextPack 容量治理及长 history、巨大固定层、摘要失败、回执配对的完整失败矩阵；未验收，等 S01 |
| S03 | `plan.py`、`verification.py`、`finalize.py`；`test_star_rb03_obligations.py` | 步骤与 claim 类型不等于原题根义务；未见 ProblemSpec→根义务→WorkUnit 映射、合并工作块和根义务进度分母验收；等 S02 |
| S04 | `controller.py`、`challenge.py`、`meta.py`、`replan.py`；Challenge/replan 公共测试 | 有界 Challenge 不能代替按数学证据计量的停滞；缺连续三回合无进展、同动作两次、改名和无关引理的统一验收；等 S03 |
| S05 | `star_product_events.py`、`star_product_projection.py`、`AgentTimeline.vue`、SSE cursor | 旧 Workbench/campaign 浏览器记录不覆盖新义务台账和子智能体视图；缺规定的完整浏览器矩阵及事件到页面 P95 证据；等 S01、S03 |
| S06 | `final_binding.py`、`final_evidence.py`；`test_star_product_final_binding.py` | 既有 GET report 是查询端点；未见三种独立输出模式、PresentationArtifact、段落来源及整理失败回退的完整验收；等 S03、S05 |

上述 Python 源码位于 `showcase/solver_harness/`（除另列的公开事件模块），测试位于 `tests/`。审计完整笔记保存在仓库之外的 `C:/Users/CQX/.codex/faithful-s02-s06-audit.md`，不作为运行证据。旧 Intern S1–S6、STAR SP 与新 S01–S06 的命名不得混用。固定基线也没有上述新阶段的完整退出证据，因此同步基线后仍须从缺失前置切片开始。

## 已执行检查

在实际起点的隔离工作树运行，Python 使用 `uv run`：

| 检查 | 结果 | 能证明的范围 |
| --- | --- | --- |
| `uv run python scripts/check_fast.py` | PASS；5 项测试通过 | baseline、官方 JSON/导入边界、Demo 合同、CLI 入口及测试接缝 |
| `uv run python scripts/check_workspace.py --offline` | PASS | 仓库与官方最小 solve 合同 |
| `uv run python scripts/check_test_seams.py` | PASS | 既有测试接缝静态约束 |

完整仓库回归、发布门禁、浏览器、真实隔离工具、provider、自然题和独立数学评测尚未由本记录验证。不能从上述 PASS 推导数学能力、并发实现或 S01–S06 全部通过。

### 起点回归与基线同步

对原起点 `e6b6b89` 运行一次 `uv run python scripts/check.py --offline --report-dir artifacts/faithful-entry-146/repository-check`，后台 PID 为 1964，开始于 2026-11-07 16:54:55（Asia/Shanghai）。最终 1251 项测试、7 个 failure、12 个 error、42 个 skip，报告耗时 1373.6 秒，命令退出 1。该次全仓检查失败，后续 mutation probes 和入口检查未由该命令执行，不能算通过。

原始结果保存在忽略目录 `artifacts/faithful-entry-146/`。12 个 error 均出自 Flask 测试清理时 SQLite 文件仍被占用；7 个 failure 涉及 Explore/Verifier schema、未校准概率字段、完整流协议失败与 RB-03 声明校验。报告保留了完整失败名和 traceback，未删除失败或将 skip 计为成功。

起点检查结束后，集成分支合入总票指定的 `b7038798`（同步提交 `6f3c917`）。没有把运行中的测试源码改为新基线。同步后的聚焦复核覆盖旧失败场景：

- ExploreReplySchemaTest、VerifierReplySchemaTest 和 Flask 测试：16 项通过，报告 `artifacts/faithful-baseline-146/focused.json`。
- 未校准概率字段、完整流协议失败、流恢复及 RB-03 旧失败用例：5 项通过，报告 `artifacts/faithful-baseline-146/failures.json`。

这 21 项只证明被复核的旧失败场景在指定基线通过，不替代同步后完整全仓回归或 S01 新合同验收。后续实现以该冻结基线为基础，原工作区保持不变。

## 并发交接边界

#148 仍只负责串行 F2；#155 决策完成不关闭任何实施票。完整并发需要独立 policy、公共控制与持久化路径的重叠执行证据，以及所有权、资源原子准入、依赖版本核验、局部 unknown、答案冻结和终止栅栏验收。容量和性能参数必须实测，不在实现前填造数值。

详细增量责任见 [并发实施交接](faithful-concurrency-handoff-155.md)。

## 原始方案核验边界

已在本机找到 `MathAgent_11.5.pdf`，SHA-256 为 `370a37110d4104ff839daf3f08d933b004bc42d41868a7df15f6576cfa14091e`，与 #130 的原件身份一致。通过 `pdftotext -layout` 提取并复核 §5.3–5.4（第 12 页）的路线依赖快照、真实成本、Pareto/APRS，§7.3 的同源隔离干预，以及第九章的 A–G 评测目标。原文支持这些机制目标；具体轮次、所有权和局部 unknown 规则依据 #155 的用户决议，不能把它们冒称原 PDF 的逐字要求。

尚未找到 SHA-256 为 `14651a0adb075ba466814f2b618ccc2bdefe5f0eb6cc291fbd5b897557305433` 的 Faithful ZIP。ZIP 中产品与技术文档优先；本次局部 PDF 核对不能替代 ZIP 全文目标覆盖核验。
