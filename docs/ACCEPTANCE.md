# Acceptance Gates

每个垂直切片必须通过对应门禁后才能进入下一阶段。

| Gate | 证据 |
| --- | --- |
| Entry | `user_agent.py` 可导入，最小 `solve()` 返回非空 `final_response` |
| Offline | 无 API Key 时 `scripts/check_workspace.py --offline` 通过 |
| Quality | `uv run pre-commit run --all-files` 和 `uv run pytest -q` 通过 |
| Demo | `/health`、`/solve`、错误状态和最小浏览器流程可运行 |
| Evidence | 每个阶段有结构化事件，结果可导出和回放 |
| Release | clean Codespace 重建通过，官方文件哈希/返回合同无变化 |

失败门必须保留证据，修复后重新运行同一门禁；不得用删除失败记录替代修复。

Solver v1.2 使用 [唯一 AC/SC 映射与实际结果](evals/showcase-solver-v1.2-release.md)。产品发布检查同时执行 `uv run python scripts/check_solver_release.py`；工程预览可通过离线门禁，完整 live 发布仍由 `--require-live` 阻塞。STAR AC-06 标签边界与历史 v0.2 AC-06 真实工具闭环分别记录。
