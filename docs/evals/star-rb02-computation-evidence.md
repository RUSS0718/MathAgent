# RB-02 计算证据验收

范围：[RB-02 #89](https://github.com/RUSS0718/MathAgent/issues/89)。合同见 [计算回执与比较语义](../engineering/star-rb02-computation-evidence.md)。基线为 `0f909a2eda63533a505224b04ab0ecfc7949aee5`，分支 `fix/star-rb02-computation-evidence`。

证据类型：有限 scripted HTTP 提供方、真实认证 Job、Adapter、Registry、SQLite 与 Docker。没有付费模型请求。镜像固定为 `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d`，没有拉取或构建镜像。

| 验收 | 实际观察 |
| --- | --- |
| ROB-AC-04 | `print(17*23)` 无预期：真实 stdout 为 `391\n`，未比较，claim 保持 easy-verify，6 次模型逻辑请求和 6 次受控 HTTP，无 Meta，继续步骤及整题审查 |
| ROB-AC-05 | 显式匹配保留有限计算升级；真实不匹配触发一次 code_issue/output_mismatch；异常触发 execution_error；先打印再异常保留输出但未比较 |
| ROB-AC-06 | 表达式无 stdout 不比较、不进入 Computation 账本；旧布尔回执消费不新增 Meta 或升级，未改写输入，replay 零派发；结构化 0、false、空数组及空对象保持可用 |
| ROB-AC-16（本票部分） | 实际 docker_isolated 来源、执行、清理与 stdout artifact 可查；重开公共 Job 后回执一致且无新增 HTTP；相关真实隔离、损坏回执拒绝与进程恢复回归通过 |

RED 记录有三条行为断言：无预期输出错误调用 Meta；无 stdout 的执行被错误写为 proven Computation；失败执行已打印 stdout 却错误报告无输出。首次夹具 8 秒观察超时不计入 RED；有效 RED 使用覆盖工具上限的局部观察窗口，最终窗口为 30 秒。

命令在票内 worktree 执行，统一前缀：

```powershell
$env:MATHAGENT_TEST_PYTHON_IMAGE='sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d'
uv run --project D:/project/工程化MathAgent/Challenge-Cup-2026 --no-sync python -m unittest tests.test_star_rb02_computation tests.test_rb02_receipt_compatibility -v
```

最终票内 9 项通过，其中 6 项执行真实 Docker。相关首轮 75 项中 74 项通过，1 项旧单元正例只有引用却无输出。为该正例补入实际输出后，分类模块 13 项全部通过，受影响票内用例再次通过。相关范围还包含 tools、candidates、Python、Guidance、Verifier/Explore 计算续接、分类成果及已完成工具回执的真实进程退出恢复。没有跳过项；没有重复全套或前端门禁。

原始 RED、GREEN、聚焦和相关日志与 `IMPLEMENTATION.md` 保存在仓外 `D:/project/工程化MathAgent/notes/star-robustness-20261025/rb02/`。`explore.py:140` 的既存 I001 导入排序问题已在指定基线复核，本票没有修改该处；其他修改文件 Ruff 通过。

限制：旧回执测试是合成历史记录的消费与只读 replay，公共进程恢复复用既有回归。未新增旧版本真实 Docker 进程崩溃实验。此处证明工程语义，不证明真实模型自然路由、数学能力提升或完整 ROB-AC-16。最终全套、前端、真实模型与发布门禁由 RB-08 验收；不升级或关闭 #70、#80、#87。
