# #127 自然多步 provider-live Run：readiness-01（2026-11-05）

本记录对应一个独立冻结 Run；不与其他源码、manifest 或旧批次拼接。结论为**已执行未通过**。本次只审查工程交付，不判断数学答案正确性。

## 冻结身份与约束

- Manifest：`issue127-natural-20261105-readiness-01`；SHA-256 `d1a08223e364f4032dffeecf7c0253fe4e8f8640c7c537ab9c1998d5097ff3e9`。
- Run：`issue127-natural-20261105-readiness-01-run01`。
- 源码 revision：`2b42070fbd64145d761ceede68abe7113bdbe557`；source SHA-256 `ff61c8bd8867d7f63d7edab1f05cb53a744dfba8e6439d9c1cced70c307a5a6d`；登记为 clean。
- 模型 `intern-s2`，thinking=false，temperature=0.2，输出上限 32768；每调用 900 秒、流空闲 30 秒停止、Run 总截止 3600 秒；传输 `stream_first`。
- Run 限额：32 model calls、32 HTTP attempts、8 tool calls、2,097,152 tokens；usage policy `observe_only`。best-effort 关闭，整题审查和最终文本绑定启用。
- 两个登记样本：`simple` 与 `vieta-equation`。本次没有修改该冻结 manifest，也没有续跑或重发其中的请求。

## 执行与停止

- runner PID 28420 于 2026-11-05 04:07:01.650（北京时间）启动，04:16:20.358 退出，exit code 0。退出码不代表验收通过。
- Run 完成 1/2：简单题公共 Job 成功；自然多步 Job `run_79a65d148a2beb293b75eb407453d617` 于 04:16:20.094 以 `failed` 终止，Job error code 为 `star_needs_review`。自然多步阶段没有达到 Run 或调用硬截止，也没有流空闲停止。
- 自然多步 trace 自然生成 4 步计划；第 1 步经两次 challenge 后被接受，并执行了 3 次成功的 Python 工具调用。第 2 步 verifier 返回 `verdict=ACCEPT`、`goal_gate=PARTIAL`、`logic_gate=PASS` 的相互矛盾组合。系统按既有合同拒绝接受并终止在 `STEP_VERIFY`，未进入最终答案生成；整题审查未执行，最终文本未绑定。
- 自然多步 Job 有 12 次逻辑模型调用和 12 次 HTTP 调用，包含一次格式修复；全批次观察为 15 次逻辑调用、15 次 HTTP、3 次工具调用。计量字段不证明 provider usage 已知。
- 最后一个 verifier 正文 token 时间为 2026-11-05 04:13:56.561，末正文为 04:16:18.332；流完成时间为 04:16:19.145。末流有正常 completion，不是未知 HTTP 请求。
- 旧批次报告：task/process_path `FAIL`，coverage `UNKNOWN`，transport `PASS`（仅配置与登记相符），usage `UNKNOWN`。coverage 的 UNKNOWN 来自一个已确认失败 Job 仍残留 dispatch intent，属于本地状态分类缺陷；修复后同等证据应归为 FAIL。usage 保持 UNKNOWN，不阻断答案完成，也不标 PASS。

## 修复与验证

只读核对确认模型返回了自相矛盾的 gate/verdict； fail-closed 是正确行为。发现两项独立实现缺陷：矛盾 ACCEPT 的安全原因会被 verifier 自由文本覆盖，导致 Job 仅报告笼统 `star_needs_review`；另外，intent 在未通过账本/传输核验的终态路径可能被过早删除，令 coverage 丢失 unresolved 标记。当前工作树修复这两处分类/身份保留行为；不会把矛盾 verdict 改为接受，也不会自动重答。

本次自然多步 Run 使用冻结的 `2b42070` 源码身份，发生在上述未提交修复生效前；不得把修复后的行为声称为本次线上结果。修复仅由离线回归验证。新的 provider-live 尝试必须使用新 source identity、新 manifest 和新 Run ID。

## Issue 状态

- **#127：已执行未通过 / open。** 缺自然多步最终非空答案、整题审查和最终文本绑定；本次已形成自然多步 trace，但在步骤核验阶段终止。
- **#128：NOT_RUN / open。** baseline 与 variant 均未派发；#127 的自然多步 readiness 前置尚未 PASS。
- 不改变官方 baseline，不放宽硬预算，不启用 best-effort，不声称数学能力提升。

脱敏归档位于 `artifacts/issue127-natural-20261105-readiness-01/`；原始 prompt、模型输出和凭证不复制进本报告。
