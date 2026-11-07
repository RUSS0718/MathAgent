# Faithful 实施入口与前置核验

日期：2026-11-07（Asia/Shanghai）。状态：前置核验中，未通过发布验收。

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

当前首个确认缺口属于 S01：流式 Adapter 将客户端 timeout 用作整次请求绝对截止，尚无新合同所需的显式版本化活跃/首包/空闲策略和 1300 秒虚拟时钟证据。先补这个前置纵切，不越过依赖实施 F1。该描述不声称整个 S01 已经验收。

## 已执行检查

在实际起点的隔离工作树运行，Python 使用 `uv run`：

| 检查 | 结果 | 能证明的范围 |
| --- | --- | --- |
| `uv run python scripts/check_fast.py` | PASS；5 项测试通过 | baseline、官方 JSON/导入边界、Demo 合同、CLI 入口及测试接缝 |
| `uv run python scripts/check_workspace.py --offline` | PASS | 仓库与官方最小 solve 合同 |
| `uv run python scripts/check_test_seams.py` | PASS | 既有测试接缝静态约束 |

完整仓库回归、发布门禁、浏览器、真实隔离工具、provider、自然题和独立数学评测尚未由本记录验证。不能从上述 PASS 推导数学能力、并发实现或 S01–S06 全部通过。

## 并发交接边界

#148 仍只负责串行 F2；#155 决策完成不关闭任何实施票。完整并发需要独立 policy、公共控制与持久化路径的重叠执行证据，以及所有权、资源原子准入、依赖版本核验、局部 unknown、答案冻结和终止栅栏验收。容量和性能参数必须实测，不在实现前填造数值。

详细增量责任见 [并发实施交接](faithful-concurrency-handoff-155.md)。

## 原始方案核验边界

已在本机找到 `MathAgent_11.5.pdf`，SHA-256 为 `370a37110d4104ff839daf3f08d933b004bc42d41868a7df15f6576cfa14091e`，与 #130 的原件身份一致。通过 `pdftotext -layout` 提取并复核 §5.3–5.4（第 12 页）的路线依赖快照、真实成本、Pareto/APRS，§7.3 的同源隔离干预，以及第九章的 A–G 评测目标。原文支持这些机制目标；具体轮次、所有权和局部 unknown 规则依据 #155 的用户决议，不能把它们冒称原 PDF 的逐字要求。

尚未找到 SHA-256 为 `14651a0adb075ba466814f2b618ccc2bdefe5f0eb6cc291fbd5b897557305433` 的 Faithful ZIP。ZIP 中产品与技术文档优先；本次局部 PDF 核对不能替代 ZIP 全文目标覆盖核验。
