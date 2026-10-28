# #101 恢复、工具回执与 Meta 当前裁决合同

状态：实施合同；2026-10-29。Refs: #101。基点 `dc9dc807314ad3fe27373e9a5111fdf3dcc6752a`（#98 已验收）。

范围仅为分配工作树的显式 Showcase；复用现有恢复与 repair 路径，不依赖 #100 的并行接口，不修改官方 baseline、默认开关、预算、llm_client 或诊断模块。

## 已确认接缝与步骤

用户已指定公共 call / Job / CLI 接缝。测试通过认证 Job 创建、查询、resume/cancel、SSE、报告和 Evidence 观察结果；子进程退出与边界故障注入只安排断点和离线回复，不替换调度。既有公开 Harness 事件提交可构造损坏/陈旧裁决作为反例，断言仍经公共 Job。

1. 先运行既有恢复、Meta、回退/重规划用例，核实实际缺口。验证：保存完整模块执行结果，skip 不算通过。
2. 每个缺口先写可复现失败用例，再最小修改。验证：同一用例红→绿，并运行拥有模块全套。
3. 补适用组合并核对最终账本。验证：固定镜像实测、相关完整模块、baseline、Ruff、测试接缝检查；全仓长门禁由主聊天协调。

## 验收映射

| 编号 | 可执行场景 | 必须观察的结果 |
| --- | --- | --- |
| F07 | 已接受步骤/持久化模型回复后真实进程退出；固定隔离工具回执后真实退出 | 原 Job/计划/步骤及已完成动作复用，工具只执行一次，原限额/deadline、已知用量与未知预留保留 |
| F08 | 修复回复产生工具请求并持久化回执后退出；并发 resume、重复 key、resume/cancel | 状态版本和动作身份拒绝重复推进，最终工具/HTTP/事件计数一致；取消后无数学推进 |
| F09 | 显式进展进入 Meta；合法回退/重规划恢复；缺失/伪造/旧来源或已消费裁决反例；unknown 恢复反例 | 只消费当前真实裁决一次，合法中间审计事件不使裁决失效；失效事实不复活；Meta 不授权 unknown 自动重发 |

版本线索暂为待验证风险，不能直接把 `decided_at_revision == 最新 revision` 当作合同。裁决必须来自已提交的正确事件与当前动作身份；合法中间审计可推进 revision。

## 已复现的最小缺陷

公共 Job 的 `meta_guidance_decided` 持久化边界注入缺少 `decided_at_revision` 的裁决时，原代码仍执行两次回退。新增 `tests.test_star_recovery_decisions_101` 先以该反例失败，增加来源校验后 8 项通过。校验要求整数版本、对应的已提交 Meta 事件、匹配的干预记录及原有 Run/计划/attempt/步骤/未消费身份；中间 `call_audit` 事件仍允许当前裁决消费一次。

修改后的 Guidance、ReplanDecision、Trace-Back、CONTINUE identity 和 Harness Meta 五个完整模块共 27 项通过，零跳过；官方 baseline 和导入边界通过。完整组合结果见本票验收记录。

## 证据边界

仅离线替身或显式 `127.0.0.1` HTTP，无真实 provider，无历史消耗登记改写。unknown 保留原 attempt/预留/deadline，零自动重发。本地显式记录恢复不代表提供方隐藏思考或远端会话恢复。

隔离场景固定镜像 `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d`；运行前 `docker image inspect` 已确认此 ID、linux/amd64，实际运行结果另记。未执行场景记 `not_covered`。绝不访问保留的 `tests/test.md`。
