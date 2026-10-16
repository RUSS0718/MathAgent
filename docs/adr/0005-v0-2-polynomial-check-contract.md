# V0.2 限定域 polynomial_check 与验证结果分层

**状态：accepted**  
**日期：2026-10-16**  
**范围：V0.2 数学检查**

v0.2 使用严格 schema 的 `polynomial_check`，输入一元 1–4 次多项式的有理系数数组、实数或有理区间定义域和候选根；工具执行精确代回、重复项和定义域检查，不解析任意表达式，也不判断完整解集。`verification_mode` 支持 `auto`、`required` 和 `off`；`required` 且没有合法工具证据时进入 `needs-review`。

结果将候选有效性与覆盖范围分开记录：候选全部代回通过时为 `candidate_status=pass`、`coverage_status=unknown`，界面明确显示“候选有效，完整性未核验”。形式化失败、超出适用域或工具不可用返回 `unknown`，不能把工具执行成功描述为数学证明。
