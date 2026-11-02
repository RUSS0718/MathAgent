# 运行工程门禁

本轮六项改进仅调整开发环境、验收入口与导航，不改变官方 baseline 或数学能力结论。代码、测试和文档等待用户审核后分别提交。

## 快速检查与完整检查

```powershell
uv run python scripts/check_fast.py
uv run python scripts/check.py --offline
uv run python scripts/check_showcase_release.py
```

快速检查验证 baseline 字节、官方导入边界、Demo HTTP 合同、测试接缝和两个服务的 CLI。它不替代完整测试、mutation probes、发布检查或前端检查。

CI 在 pre-commit 后先运行快速检查；完整测试只通过 `check.py` 执行一次。发布检查仍执行其聚焦验收，属于有意保留的独立发布条件。Python quality job 上限调整为 60 分钟，前端仍为 15 分钟。

完整测试写入 `artifacts/repository-check/tests.json` 和 `diagnostics.log`；CI 在成功或失败后均尝试上传该目录，目录缺失时告警。摘要保留失败、错误、跳过和 expected failures。诊断文件接收测试及其继承标准句柄的子进程输出；失败保持非零，不把未知诊断认定为预期噪声。

## 最终验收

```powershell
uv run python scripts/run_final_gate.py --root . --output-dir artifacts/final-gates --run-id review-01
```

每次使用新的 run ID，避免覆盖已有证据。该入口统一执行快速检查、完整仓库检查、发布检查及前端安装、审计与检查；失败后不继续下一阶段。`--require-reference` 额外要求指定 Reference 用例实际执行，需要先配置仓库既有的 Docker 测试环境。默认离线门禁不代表真实 provider 或数学效果验收。

启动长测试时只保留一个运行进程。读取独立 run 目录的 `status.json` 查看 PID、开始时间、当前阶段、完成阶段数与日志位置；每 30 分钟的定时检查在状态无变化时静默，完成或失败后移除。

## 只读 Issue 核验

```powershell
uv run python scripts/check_issues.py --repo RUSS0718/MathAgent 116 117 118 119 120
```

该入口只发 GET，返回机器可读状态；网络或数据错误以非零退出，不根据本地历史文档推断 GitHub 当前状态。它不关闭 Issue，也不代替逐项验收。

身份与恢复相关修改先读 [身份链导航](identity-navigation.md)。历史 `final-validate-04/05` 等脚本保留为旧实验资料；后续使用仓库参数化入口，不再复制硬编码路径版本。
