# 运行工程门禁

本文件统一规定开发检查与阶段最终验收的执行频率和证据复用方式。检查结果只证明所覆盖的合同，不自动升级数学能力结论。

## 按修改范围检查

- 纯文档修改：检查差异格式、相对链接和规则一致性。仅因新增文档提交，不重跑产品全仓测试或前端安装。
- 代码切片：先运行聚焦检查及受影响模块的回归。涉及身份、预算、恢复、交付绑定或默认路径时，补齐对应公共合同检查。
- 阶段退出：集中完成双轴差异审查，处理阻塞项并通过聚焦回归后，冻结源码运行一次最终门禁；浏览器及专项合同仍按阶段要求验收。门禁前逐项映射阶段合同到公共入口、状态/断言、测试与证据位置；未覆盖项须保持未完成或明确列为未验证，不得由全仓通过替代。
- 门禁后有代码、测试、依赖、配置或检查脚本变化：复核影响，阶段退出前对最终源码重新运行门禁。仅有文档变化时，检查文档并保留原门禁源码 SHA，另记最终交接 SHA。

同一冻结源码已有成功门禁且环境与验收条件未变化时，交接引用原证据。失败时修复最小责任范围，先通过聚焦检查再重跑；保留原失败记录。CI 按其工作流独立执行，不以本地证据跳过。

阶段验收映射可使用以下最小列项；保留合同原编号，并将未运行或不适用与通过项区分记录：

| 合同 | 公共入口 | 状态/断言 | 测试与证据 | 结果 |
| --- | --- | --- | --- | --- |
| 例：C1 | API 或命令 | 可观察的持久状态 | 测试名、报告路径 | pass / fail / not_run |

## 快速检查与完整检查

```powershell
uv run python scripts/check_fast.py
uv run python scripts/check.py --offline
uv run python scripts/check_showcase_release.py
```

快速检查验证 baseline 字节、官方导入边界、Demo HTTP 合同、测试接缝和两个服务的 CLI。它不替代完整测试、mutation probes、发布检查或前端检查。

CI 在 pre-commit 后先运行快速检查；完整测试只通过 `check.py` 执行一次。发布检查仍执行其聚焦验收，属于有意保留的独立发布条件。Python quality job 上限调整为 60 分钟，前端仍为 15 分钟。

完整测试写入 `artifacts/repository-check/tests.json` 和 `diagnostics.log`；CI 在成功或失败后均尝试上传该目录，目录缺失时告警。摘要保留失败、错误、跳过和 expected failures。诊断文件接收测试及其继承标准句柄的子进程输出；失败保持非零，不把未知诊断认定为预期噪声。

手工重跑命名用例或补跑隔离测试时，使用报告入口并声明预期用例数；入口会先验证选择器可加载且实际数量相符，再执行测试：

```powershell
uv run python scripts/run_unittest_report.py --expect-count 1 tests.test_module.Test.test_case
```

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
