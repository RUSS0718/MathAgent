# SH21 Intern Solver 适配与真实调用记录

**日期：** 2026-10-23（Asia/Shanghai）  
**关联：** [SH21 #53](https://github.com/RUSS0718/MathAgent/issues/53)、父规格 [#32](https://github.com/RUSS0718/MathAgent/issues/32)  
**结论：** `needs_review`。两次真实样本均未执行工具，`v0.2 AC-06` 仍为 `unavailable`。本记录不关闭任务，也不声明数学能力提升。

## 实现边界

`showcase/solver_harness/intern_port.py` 通过现有 `showcase.adapters.InternModelAdapter` 调用 Intern，保留其请求重试、物理 attempt 和 provider usage。角色输出接受严格 JSON 对象；完整 schema、原题、角色协议和当前状态视图进入请求。Meta 请求缺少原题时，port 使用创建时绑定的同一道原题。

`InternModelPort()` 默认没有 adapter，不创建网络客户端。`scripts/run_solver_intern_live.py` 默认输出 `not_run`，只有显式 `--live` 才调用服务。官方 `user_agent.py`、`implementations/` 和默认评分路径没有变更。

每次调用记录 `run_id`、`call_id`、角色、模型标识、finish reason、usage、物理 attempts、错误类型，以及 Verifier 实际收到的 receipt IDs。未知 usage 保留 `null`。完整失败输出保存在被忽略的运行目录，不写入本记录。最终实现把 provider 记录保存在空状态补丁的审计事件与 `evidence.json` 中，避免修改已冻结的终态业务状态。

## 固定公开任务与预算

任务是求解实数方程 `x²−1=0`，由模型生成 `polynomial_check` 候选代回请求，再根据真实回执继续审查。这个工具只能检查候选代回、重复项和定义域；完备性仍需要独立代数论证。它不支持展开式恒等验证。

底层 `InternChatClient.retry` 表示总尝试次数。配置为 `1` 表示每次逻辑调用最多一个物理 HTTP attempt，即零次重试；设置为 `0` 会完全不发送请求。两次样本的输出上限都是每请求 `1024` tokens，HTTP timeout 都为 `30` 秒，`thinking_mode=false`，工具不重试。

| 样本 | 逻辑与物理请求上限 | 工具上限 | 总时限 | 实际逻辑与物理请求 | 实际工具 | Provider tokens | 结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `a1491b1a814d414fa4f502fd4b499c0a` | 6 | 2 | 180 秒 | 5 | 0 | 8767 | `needs_review` |
| `eb2475142ada44bab1358fff5dabc582` | 4 | 1 | 120 秒 | 3 | 0 | 4023 | `needs_review`、`failed_runtime` |

两次合计使用 8 次逻辑调用、8 次物理 HTTP attempt、0 次工具执行和 12790 provider tokens。没有发生 HTTP 重试。成本未知。每次 provider finish reason 都是 `stop`，没有 `length` 样本。

两次真实样本均开启 `skills`、`persistent_sessions`、`local_code_tool`、`final_generation`、`final_solution_review`，均未开启 `stream_recovery`。这是实际运行条件。后续代码已默认在显式 probe 中开启 `stream_recovery`，但没有用修订后的代码再调用真实服务。

## 两次失败与后续离线修订

第一份报告生成了真实的工具请求，但模型把未执行的计算标为 `verified`。现有 normalizer 将这类断言降为 `hard-verify` 并丢弃未授权证据，因此未执行工具。Verifier 发起质询，随后模型返回一次无法解析的 JSON。该样本原始 Run 最后停在 `STEP_EXECUTE`，状态仍为 `running`；sidecar 明确为 `needs_review`。原始记录保留，没有事后修改状态冒称完成。

随后加强协议：待执行工具请求必须标为 `easy-verify`，可合并候选，未知完整工具输出时省略 `expected_output`。第二份报告确实生成了 `easy-verify` 的候选代回请求，但给其他断言添加 `tool_request:null`，违反当时的可选对象 schema。port 拒绝整份报告。Verifier 和 Meta 随后调用，runner 最后以 `failed_runtime` 停止，仍未执行工具。

最后仅进行离线修订：schema 显式允许可选 `tool_request:null`，不改变标签、不修改模型给出的工具参数。新增开启 `stream_recovery` 的错误测试，证明不可解析角色输出停在 `interrupted` 并保留 call audit，不再归一化成空报告。修订后的代码没有第三次真实调用；本轮授权预算已经停止。

离线集成测试另有注入客户端生成工具请求、真实本地 polynomial registry 执行、回执进入 Verifier、最终生成与整题审查的路径。该测试证明工程连接，不能替代真实 Intern 工具闭环证据。

## 运行引用

首次调用：

```powershell
uv run python scripts/run_solver_intern_live.py --live --env-file '<本地 .env 的绝对路径>'
```

最后一次授权调用：

```powershell
uv run python scripts/run_solver_intern_live.py --live --followup --env-file '<本地 .env 的绝对路径>'
```

当前脚本保留同样的预算入口，并新增 `stream_recovery` 与 nullable schema 修订；重放这些命令会产生新运行，不会重现旧模型输出。本记录不是额外真实调用的授权。

| Run ID | 被忽略的证据文件 | SHA-256 |
| --- | --- | --- |
| `solver-intern-a1491b1a814d414fa4f502fd4b499c0a` | `artifacts/solver-intern-a1491b1a814d414fa4f502fd4b499c0a/evidence.json` | `f176185e2f062da1e34d35c6a0520c2ff57f969f21380072b000dd83d0e3f975` |
| `solver-intern-eb2475142ada44bab1358fff5dabc582` | `artifacts/solver-intern-eb2475142ada44bab1358fff5dabc582/evidence.json` | `12878ee9142902c1f906d30f9ffae72c0bd31b7368b4ef0abaf8debcda91ce93` |

各目录还包含 `run.json`、`solver.sqlite3` 与 `budget.sqlite3`。证据不含凭证或完整输入 prompt。运行产物不提交 Git。
