# F8-R18 空答案辅助审查修复

日期：2026-11-12（Asia/Shanghai）。问题：[#159](https://github.com/RUSS0718/MathAgent/issues/159)，关联 [#157 交接](https://github.com/RUSS0718/MathAgent/issues/157#issuecomment-6813618228)。适用源码：`ba97cd0` 后的本修复提交。

## 复现与边界

实际本地 `review_contract.validate_row` 仅以 run_id/answer_sha256 为 None 判断缺失。非空 Run ID 和 SHA256(empty) 可使空答案的 pass/fail 均被接纳。最小离线脚本实测 pass ACCEPTED、fail ACCEPTED、unresolved ACCEPTED，然后实施修复。

新增 tracked `showcase.faithful_review_artifact.validate_answer_verdict`，将缺失 Run ID、缺失 hash、空 hash 以及 SHA256(empty) 都限制为 unresolved。非空答案身份原有 verdict 不变；helper 不代替来源、hash、anchor 或 rubric 校验。

真实批次 adapter 位于 ignored artifacts，继续不进入提交分支。其 `review_contract.py` 已接入 tracked helper：

```python
from showcase.faithful_review_artifact import validate_answer_verdict

# 替换原有 if run_id is None or answer_sha256 is None 的两行检查
validate_answer_verdict(identity, row['verdict'])
```

adapter 当前 SHA256：`7f26f9d49bfe0c6e0e85daca2843745293a857ad13d2bb3692bd72402001bba2`。这是一处本地审查脚本改动，复用该批次时须核对此接入，不能只凭安装新 helper 推断旧 adapter 已更新。没有重封 frame 或重签历史证据。

## 验证

`uv run python scripts/run_unittest_report.py --expect-count 2 tests.test_faithful_review_artifact` 的2项用例通过；53项相关回归、Ruff及快速检查通过，0 failure/error。完整阶段门禁未运行。

实际本地 adapter 的最小复现与真实 G/PutnamB1 身份复核均改为 pass/fail REJECTED、unresolved ACCEPTED。证据在本工作树 `artifacts/bugfix-20261112/{repro_review.py,verify_real_review.py,real-review-verification.json}`；验证零 provider 请求。真实 job/result 内容 hash 在检查前后相同：

- result.json：`d99fcddea264c89a0c4a76b3f475f8f4ddfd2e30118dc34d467e22bffd774f78`
- job.json：`5d6aa3297f1c7f0d90d77999aafaf4fac53d928c1ed6700a57647302574e1ed5`

41份首次、29未派发、98登记/70必需和28固定辅助审查槽保持原状；unknown 不重发，不替换槽。本修复解除这一空答案校验缺口，不完成重启处置、F8辅助评测或最终报告，不关闭 #157。
