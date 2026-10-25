# RB-01 交付来源与离线复评 API

范围：spec #87 / issue #88，ROB-AC-01、02、03。官方入口、默认预算和运行时求解流程均不变。

## 公共接口

`showcase.star_acceptance.evaluate_delivery(job, run, contexts)` 接受：

- `job`：认证 `/api/agent/jobs/<job_id>` 的终态响应。
- `run`：`SolverStateStore.get_run(job_id)` 返回的控制器快照和事件；包含完整调用审计。
- `contexts`：外部传输边界捕获的请求上下文列表，保留 `run_id`、`call_id`、候选与步骤证明。它不是脱敏 Job 摘要。

接口不派发模型或工具，只返回身份、计数、布尔判定和原因。调用者必须在受控环境提供真实来源，不能把自填 ACCEPT 当成审查。

选择依据为当前交付文本、控制器审查记录及其中的调用引用。接口核对同 Run、Plan Attempt、候选版本、完成状态和真实 ACCEPT，沿既有 retry/repair/tool 调用链核对候选。生成事件的版本区间将候选绑定到实际生成请求，重复文本的不同版本也分开处理。缺少或歧义来源返回失败，不能退回 first/last role 选择。

`review_bound` 表示当前交付绑定到实际完成的整题 ACCEPT。
`proof_delivered` 表示对应生成与审查请求的完整 `step_proofs` 相同，且证明正文身份及回执引用与控制器审查来源相符。
`nonfastpath` 只表示上述非快通道证明传递成立，不代表 #80 AC-18 或全部实验条件通过。
Explore 快通道可以 `review_bound=true`、`proof_delivered=false`、`nonfastpath=false`。
LLM ACCEPT 不等于独立数学真值或形式化证明。

## 保存批次接口

```python
from showcase.star_replay import replay_saved_batch

report = replay_saved_batch(
    saved_batch_directory,
    original_runner_version="原 runner 版本或源码 SHA-256",
)
# 调用者将 report 写到独立目录；保留原归档。
```

接口验证 `hashes.json` 所列全部文件，要求 Job、报告、Evidence、捕获上下文及原 acceptance 都在清单内。SQLite 以 `mode=ro&immutable=1` 打开，不构造运行时、Adapter 或 Registry。存在 WAL 时拒绝读取，避免忽略尚未落盘的新状态。

复评核对快照与已有公共审查历史、交付文本及来源；报告保留输入 SHA-256、两版 runner 身份、原 `proof_delivered`、新选择和差异理由。缺失、损坏或来源不一致的批次不会判成功。接口不写入原目录，也不返回完整问题、prompt 或证明正文。

旧 manifest 未覆盖 SQLite；本次记录其当前哈希并与已列入清单的公共导出交叉核对。`integrity=verified` 表示清单及上述一致性核验通过，不是对历史数据库真实性的独立认证。

## 验证范围

`tests/test_star_acceptance.py` 使用真实认证 Job、控制器、Adapter、SQLite、Registry 和账本，只替换外部 HTTP。覆盖早期 REJECT/最终 ACCEPT、多候选、相同文本不同版本、重规划、格式修复、工具续接、显式重试、无效来源及只读 replay。

first-role 敏感性探针须使同一公共 Job 的 `proof_delivered` 行为断言失败；导入失败不算错选缺陷证据。历史保存批次的派生报告及 RED/GREEN 原文保留在本轮独立 notes，不提交 raw。保存批次复评不追溯改变预登记条件，也不自动完成 #70/#80。
