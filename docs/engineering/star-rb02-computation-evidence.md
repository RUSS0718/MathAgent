# RB-02 计算回执与比较语义

范围：[工单 #89](https://github.com/RUSS0718/MathAgent/issues/89)，对应 ROB-AC-04、05、06 及 ROB-AC-16 的计算部分。

`tool_precheck` 保留 `assertion_matched` 布尔字段，并新增两个字段：

| 字段 | 含义 |
| --- | --- |
| `comparison_status=not_compared` | 没有执行可用的有限计算比较，包括未声明预期、缺输出或执行失败 |
| `comparison_status=matched` | 成功执行、退出码 0、有可用输出、有限计算作用域且显式预期匹配 |
| `comparison_status=mismatched` | 同上，但显式预期与实际输出不匹配 |
| `output_available` | 是否保留可观察输出，不表示执行成功或数学命题已被接受 |

无预期值的成功输出保持 `assertion_matched=False`，但不触发 `output_mismatch` 或 `code_issue`。Verifier 收到实际回执继续审查。显式匹配仍只支持有限计算范围的 claim；未比较不会自动升级 `verified`。真正不匹配及执行错误继续触发既有有界指导。

Python 工具通过真实 stdout 提供计算结果。空或纯空白 stdout 即使与显式空预期相等，也没有计算证明。运行时不改写脚本、不补造输出。结构化工具的 `0`、`false`、`[]`、`{}` 都是可用结果，`null` 表示缺失结果。分类账本拒绝用无输出的成功回执建立 Computation。

脚本先打印再异常退出时，输出可用性为 true，执行仍失败、断言仍未比较。stdout 本身不能替代成功执行或数学审查。

旧回执缺 `comparison_status` 时不从布尔值推断 mismatch，也不新增匹配升级。已有历史事件、回执和审查不改写。旧计算证据读取仍要求实际输出；退出码或 stdout 引用本身不足以证明输出存在。既有来源、隔离、预算和恢复权限保持。

验收测试：`tests/test_star_rb02_computation.py` 经认证公共 Job、真实 Registry、真实 Docker、SQLite、报告、Evidence 与出站提供方记录验证。只有 HTTP 提供方使用有限脚本。`tests/test_rb02_receipt_compatibility.py` 补充公共结构化工具及旧回执消费检查。结果及限制见 [评测记录](../evals/star-rb02-computation-evidence.md)。
