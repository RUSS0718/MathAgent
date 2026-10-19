# v0.2 Live 调试与 Agent 可观测性规格

**状态：** accepted for the `math-agent-workbench-v0.2` development branch

## 目标

修复 Showcase 工作区 `live` 模式只返回 `unavailable`、而没有进入 Agent 执行链的问题。后端必须通过统一的 live pipeline 运行数学题，前端必须展示 pipeline 的公共节点事件，CLI 必须能驱动与网页相同的 HTTP/SSE 合同。

## 运行边界

- 只修改 Showcase profile；根目录 `user_agent.py`、`implementations/`、官方预算和 baseline 不变。
- `fake` 仍用于无凭证的离线合同测试；人工调试 CLI 默认要求服务为 `live`，不把 fake 结果当作真实能力证据。
- 事件只包含节点名称、状态、耗时和脱敏摘要，不包含完整提示、隐藏推理、凭证、原始图片或工具参数值。
- live pipeline 使用有限节点和独立预算：`intake`、`planner`、`solver`、按需 `tool`、`verifier`、`synthesizer`、`terminal`。
- live 默认采用长槽预算：总运行 1100 秒、最多 6 次模型调用、2 次工具调用、单次 Intern 请求 180 秒并最多重试 2 次；这些值只属于 Showcase，可由 `SHOWCASE_*` 环境变量覆盖。

## 验收合同

1. 在 `SHOWCASE_MODE=live` 且凭证可用时，创建 Job 后必须进入真实 Intern API；不能在工作区执行器中直接写入 `unavailable`。
2. Job 的 SSE 必须至少能够表示 `intake`、`planner`、`solver`、`verifier`、`synthesizer` 和 `terminal` 的开始/结束或失败状态；模型请求工具时还必须出现 `tool` 事件。
3. live 请求失败时，Job 必须进入 `failed`，前端必须显示失败节点和稳定错误类别；不能显示空白成功报告。
4. CLI 必须覆盖网页使用的身份、能力、会话、Job 创建、SSE 观察、状态、报告、取消、恢复和多项式检查入口；`probe` 默认拒绝非 live 服务。
5. 页面刷新后可以从 Job 的最后事件游标恢复时间线，并在终态重新加载报告。
6. 现有官方路径、旧 `/api/runs` 合同和 fake 测试继续通过。
