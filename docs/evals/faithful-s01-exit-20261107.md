# S01 流式工程退出验收

日期：2026-11-07（Asia/Shanghai）。集成分支：`mathagent-faithful`。结论：按用户本轮确认的流式范围，S01 工程退出通过，保持 `engineering-preview`，可以解除 S02 的 S01 工程依赖。

## 范围与证据

用户本轮明确非流式不再强制验收，以后以流式为准；未删除旧接口或改变旧 Run。退出合同见 [S01 工程退出合同](../engineering/faithful-s01-exit-contract.md)。

- 首纵切：1300 秒活跃流、1200 秒软提示、有效 idle、旧 Run、默认关闭、原 deadline、安全重试及公开调用依据，见 [首纵切记录](faithful-s01-first-slice-20261107.md)。
- 浏览器：真实 Chromium、受控 API 的 3 项验收通过，刷新/SSE 重放和重连不创建新 Job、不自动 resume，显式操作才以新身份重试，见 [浏览器记录](faithful-s01-browser.md)。不冒充真实服务证据。
- 后端：`13ecd8d` 的公共 HTTP 幂等、真实进程退出、关闭服务配置后的冻结策略恢复、unknown 零自动重发、显式新 ID、旧预留/原 deadline、已完成响应复用、取消/完成后迟到用量、完整协议失败及本地处理分类，见 [恢复记录](faithful-s01-recovery.md)。新增恢复 6 项与处理分类 3 项、相关旧策略回归 8 项通过。
- 终审：Spec 轴无发现；Standards 轴发现完整流的本地汇总失败发出 unknown 活动事件。`2290e75` 补充先红后绿断言并修复，保留远端 completed；未完成流和旧策略仍沿原语义。

## 唯一冻结长门禁

```powershell
uv run --frozen python scripts/run_final_gate.py --root . --output-dir artifacts/final-gates --run-id faithful-s01-exit-13ecd8d
```

冻结 SHA：`13ecd8d4dba797f3deef697c31a150f0ca36b6c2`。runner PID 5984，开始于 21:31:23，耗时 1583.875 秒。六阶段全部退出 0，最终 `passed`，`source_changed=false`：快速检查、完整离线回归、发布检查、前端安装、前端高危依赖审计、前端检查。全仓 1374 项、0 failure、0 error、42 skip，mutation probes 完成，npm audit 为 0 vulnerabilities。

原始证据保留在忽略目录 `artifacts/final-gates/faithful-s01-exit-13ecd8d/`，包含状态、源码清单、各阶段日志、测试 JSON 和诊断。运行已结束，没有重复启动长测试或遗留临时检查任务。

## 终审补丁后的集成复核

`2290e7544e78cdc2c62d8410dd3c0074dddb6b8d` 晚于冻结门禁，不声称六阶段覆盖此 SHA。其生产差异只修复完整流本地失败的活动事件；集成侧执行 processing 3 项及全部 `test_faithful_s01_*.py` 27 项，通过；ruff/diff 检查通过。最终快速门禁另行复核官方 baseline、JSON/导入边界及 Demo/CLI。

## 声明边界

42 个 skip 不算能力通过，未配置真实 Docker Reference 环境的用例仍是缺项；它们不替代本轮已实际执行的 S01 流式工程合同。真实 provider SLA、自然题、实际容量/费用、独立数学效果仍为 `not_run/unknown`，不能由工程退出推导。S02 尚未实现，本记录不关闭 #146 或 F1–F8，也不宣称 #156 并发落地。

官方 baseline 文件无差异；原工作区用户未提交修改和 `tests/test.md` 未读取或更改。实施提交均已进入集成分支；工作树归档受应用活动引用保护时保留，不强制删除。
