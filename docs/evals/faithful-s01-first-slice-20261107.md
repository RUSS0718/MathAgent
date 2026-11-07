# Faithful S01 首纵切集成验收

日期：2026-11-07（Asia/Shanghai）。分支：`mathagent-faithful`。

本记录只确认版本化流式调用生命周期首纵切的离线工程验收。S01 尚未完整退出；S02–S06 及 F1 开工门槛未因此解除。

## 实现与审查

- `272f0f5`：默认关闭的 `faithful-stream-v1`，Job/Run 冻结策略；1300 秒活跃流、1200 秒一次软提示、首有效增量后 30 秒有效 idle、Run 原截止、安全重试和同 key 恢复。
- `e250e80`：适配器失败验收复现同 SSE ID 的不同内容被丢弃，去重改为同时核对 ID 和载荷摘要；无 ID 的相同增量保持完整。
- `c9f394f`：Spec 终审 P2 修复，公开 attempt 增加策略版本、endpoint SHA-256、未知 provider 和未知公开上限来源状态；严格白名单，不公开原 URL、凭证或查询参数。旧策略不增加该字段。

审查中发现的队列心跳绕过 idle、EOF 排队后的慢消费者误超时、全局迟到清理改变旧策略及 timeout 参数审计不实均在提交前修正，并保留对应聚焦验收。Standards 轴无可行动发现；Spec 轴唯一终审 P2 已修复。官方 `user_agent.py`、`implementations/`、`requirements.txt` 相对 `b7038798` 无差异，baseline 快速检查通过。

## 六阶段门禁：冻结版本 e250e80

唯一后台运行开始于 19:17:44，runner PID 12624，耗时 1457 秒。命令：

```powershell
uv run --frozen python scripts/run_final_gate.py --root . --output-dir artifacts/final-gates --run-id faithful-s01-e250e80
```

六阶段均退出 0，最终 `passed`，`source_changed=false`：快速、全仓离线、发布、前端安装、前端审计、前端检查。全仓测试 1362 项，0 failure、0 error、42 skip；mutation probes 完成。前端审计 0 vulnerabilities。构建有既有的大于 500 kB chunk 提示，不影响退出状态。

证据位于忽略目录 `artifacts/final-gates/faithful-s01-e250e80/`，包括 `status.json`、源码清单、阶段日志及 `repository-check/tests.json`、`diagnostics.log`。42 个 skip 不算能力通过；未配置已验证 Docker 镜像的 Reference 用例仍是缺项。

## 最终证据补丁 c9f394f

该补丁晚于冻结门禁，不宣称六阶段门禁验证了此 SHA。集成侧执行：

```powershell
uv run --frozen python -m unittest discover -s tests -p 'test_faithful_s01_*.py'
uv run --frozen python -m unittest tests.test_request_attempts tests.test_star_default_envelope_98
uv run --frozen python scripts/check_fast.py
uv run --frozen ruff check llm_response.py showcase/stream_timeout_policy.py showcase/adapters.py tests/test_faithful_s01_call_evidence.py
git diff --check
```

结果为 18 项 S01 聚焦、9 项共享 attempt/envelope 回归、5 项快速测试通过；lint/diff 检查通过。实施侧另有 11 项 attempt/envelope 回归通过。主代理一次误用不存在的 `tests.test_llm_response` 得到导入错误，随后使用上述实际模块重跑；错误调用不计通过。补丁未改变超时调度或前端行为，未重复启动全仓长测。

## 尚未完成

完整非流式等待、取消/协议失败/迟到响应完整矩阵、浏览器刷新/SSE 重连、跨进程完整恢复、provider-live SLA、真实容量和数学效果仍未由本纵切验收。真实工具缺项不能以 mock 补成通过。下一前沿仍是 S01 剩余合同，随后才是 S02，不直接开工 F1。

原工作区未提交文件保持原样，`tests/test.md` 未读取或改动。实现工作树内容已合入；应用因另一活动任务引用而拒绝归档，保留 `faithful-s01` 工作树，不强制删除。最终门禁进程已结束，没有新增自动化或遗留临时检查任务。

完整并发独立交接见 [#156](https://github.com/RUSS0718/MathAgent/issues/156) 与 [本地合同](../engineering/faithful-concurrency-handoff-155.md)；串行 F2 不代表并发覆盖，相关实施票保持开放。
