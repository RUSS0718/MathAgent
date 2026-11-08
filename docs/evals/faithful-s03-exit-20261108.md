# S03 规格与工作块工程退出验收

日期：2026-11-08（Asia/Shanghai）。状态：工程退出通过（`engineering-preview`）。集成分支：`mathagent-faithful`。门禁源码提交：`3a6943f26564db250b96e21044bb4b28511f599f`。完整合同见 [S03 技术设计与工程退出合同](../engineering/faithful-s03-exit-contract.md)。

## 实现边界

S03 在现有 Solver Harness 与 Showcase Job/Run 路径实现版本化 ProblemSpec、根义务和 WorkUnit 多对多映射、类型化且绑定实际 Verifier 来源的义务证据、AND 前提、规格修订定向失效、共享预算账本的收尾预留，以及独立 Whole Verifier 和 exact-text 绑定。

ProblemSpec 只通过显式开关启用。默认配置和旧 Run 保持原语义。官方 `user_agent.py`、`implementations/`、`BASELINE.json` 与默认评分路径未改。`tests/test.md` 未读取或改动。

公开进度仅增加 `root_obligations.covered`、`total` 和 `items[{ordinal,type,status}]`。该投影不包含义务 ID、原题或义务文本、假设或证明内容。关闭开关时保留旧公开 shape。

## 验收结果

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| S03 聚焦回归 | 47 项通过 | `uv run python -m unittest discover -s tests -p "test_faithful_s03_*.py"` |
| Whole Verifier 与交付绑定回归 | 8 项通过 | `uv run python -m unittest discover -s tests -p "test_star_product_final_binding.py"` |
| STAR 持久恢复回归 | 29 项通过 | `uv run python -m unittest discover -s tests -p "test_star_product_recovery.py"` |
| Chromium 产品端到端 | 13 项通过 | `npm run test:browser -- --config playwright.product.config.ts`；含 ProblemSpec 进度、刷新、SSE 持久游标与零新增求解调用 |
| Ruff 与差异格式 | 通过 | `uv run ruff check showcase tests/test_faithful_s03_*.py tests/star_recovery_worker.py`、`git diff --check` |
| 官方 baseline | 11 个文件 SHA-256 全匹配 | 按 `BASELINE.json` 逐文件核对 |
| 最终六阶段门禁 | 6/6 阶段通过，`source_changed=false` | run ID `faithful-s03-exit-3a6943f-20261108-1355`，目录 `artifacts/final-gates/faithful-s03-exit-3a6943f-20261108-1355/` |

最终门禁 PID 为 39392，开始时间为 2026-11-08 14:04:56（Asia/Shanghai），总耗时 1458.563 秒。仓库 unittest 运行 1448 项，0 失败、0 错误、42 跳过，用时 1334.440 秒。42 项均需已验证的 Docker 镜像或显式 Docker 集成环境，未计为通过。

fast 检查 5 项通过，release 检查 27 项通过。`npm ci --no-audit --no-fund` 成功，`npm audit --audit-level=high` 报告 0 个漏洞，前端 typecheck、单元测试和构建通过。Vite 对 509.85 kB 的主 JS bundle 输出超过 500 kB 的非阻塞提示；门禁退出码为 0。

## 代码审查

Standards 复核提出的公开进度字段合同与重复失效判定问题已处理：字段 shape 和脱敏边界已写入 S03 合同；结果失效归档与当前账本共用 `invalid_nodes` 判定。

Spec 复核提出的义务跨 WorkUnit 认领、候选列表误关完备性、Pell 多要求覆盖、容量拒绝保留原文、规格修订后旧 Whole Verifier 记录及候选重用、ProblemSpec 进程恢复和浏览器 SSE 游标验证问题，均已补实现约束或验收回归。两轴审查未留下阻塞项。

## 能力边界

本次退出结论只代表 Showcase 工程合同与受控边界可达，不代表真实 provider-live、已标定容量或 SLA、自然题规格抽取、隔离工具完整运行或数学效果通过。42 项 Docker 测试跳过仍为未验证。本轮未运行付费 provider 实验，不据此声称数学能力提升。

S03 工程退出解除 S04 和满足其余前置的 S05 的 S03 依赖。F1 仍等待 S04。本次不关闭总 Issue #146，也不宣称完整并发或 F1–F8 已实现。
