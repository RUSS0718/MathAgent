# 本地 Python 拒绝后的有界纠正

日期：2026-11-12（Asia/Shanghai）。问题：[#158](https://github.com/RUSS0718/MathAgent/issues/158)。适用源码：`ba97cd0` 后的本修复提交。

## 复现与修复

`LiveAgentPipeline` 收到 `python_math` 的 `call_not_allowed` 后直接停止，`final_response=None`。使用真实 Registry/PythonMathTool 和离线 ScriptedModel，新增测试先失败：`test_guard_rejection_can_return_an_answer` 的非空答案断言失败。附件原始183字符代码未保存，本次重建相同拒绝规则，不冒称恢复原代码。

对 Python AST/语法的明确本地拒绝增加一次纠正机会。原请求和 rejected 回执以原 tool_call_id 回喂，模型可直接回答或提交修正代码；修正代码仍经 Registry、AST 和原 Run 预算。第二次拒绝停止；权限、schema、身份、未知结果、执行错误和超时不取得该重试资格。成功工具原有续接合同不变。

所有拒绝记录保留，验证器仍看到失败工具，不升级成成功计算证据。native 与 text_action 两种协议均覆盖；公开事件不含代码正文。未知续接传输不重发。

## 验证

```powershell
uv run python scripts/run_unittest_report.py --expect-count 7 tests.test_live_tool_recovery
uv run python scripts/run_unittest_report.py --expect-count 53 tests.test_live_pipeline tests.test_live_tool_workspace tests.test_live_workspace_pipeline tests.test_tools tests.test_faithful_f8_reporting
uv run python scripts/check_fast.py
```

7项新增用例和53项相关回归通过，0 failure/error/skip；Ruff及快速检查通过。新增用例涵盖直接答案、两协议修正工具、再次拒绝、模型预算、工具预算、预算异常回执保留和未知传输停止（两协议属于同一测试）。运行报告由既有报告入口保存在 ignored artifacts。此次为小范围修复，未运行完整阶段门禁；未发真实 provider 请求，不证明数学正确率。官方 baseline 由快速检查核验。
