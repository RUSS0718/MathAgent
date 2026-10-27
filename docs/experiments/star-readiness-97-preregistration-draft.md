# #97 非流式两题登记草案

状态：预算映射已由用户确认，真实登记仍不可派发。日期：2026-10-27。本草案与旧 RB08 E1/E2 独立，不改变旧合同或历史记录。`artifacts/issue-97-prereg/draft-v2.json` 保存精确输入，文件 SHA-256 为 `cfc091faf41865c87ad5b196cd48183f2f1ebf874224dc22581ef16d0bed6f34`；该历史草案中的预算状态保留创建时的值。`showcase.star_readiness_registration.adapt_draft` 可将其绑定到当前源码，`StarReadinessCoordinator` 只允许 loopback 脚本验收，不能向真实 provider 派发。最终源码身份及门禁结果以[就绪核对记录](../evals/star-readiness-97-status.md)为准。

## 样本和身份

| 样本 | 公开来源 | 输入 SHA-256 | 目标及条件 |
| --- | --- | --- | --- |
| `simple-01` | [Project Euler 第 1 题](https://projecteuler.net/problem=1) | `e84be303c2719dd77c917a0a6d75884a7c9abdd6f4c55e1069ff6af67a033cfb` | 观察自然快通道、整题审查和交付绑定。 |
| `multi-01` | [Project Euler 第 10 题](https://projecteuler.net/problem=10) | `874c20406723e261e1f2dde0c5ab7f9ccb9e76957c48cb84718383151ccce5d6` | 观察多步规划、步骤及适用受控计算。 |

两题均先执行一次，不为触发机制改变提示。哈希输入是 JSON 中 `text` 字段的 UTF-8 字节，句段用 LF 分隔，末尾无换行；原网页数学排版在此输入中规范化为纯文本。每题实际路径由模型决定；未自然触发快通道、规划或隔离计算时，对应目标记 `not_covered`，不替换题目或重跑。

历史 `draft-v2` 创建时绑定 HEAD `fc6e9b4d489ae9e402fc3e97cfce0fe9e49f7762`、源码 SHA-256 `5ad75b4d6def323e179a15679669ed5ebb5f936423c372bdf98fe1cfc57b136e`，工作树为 dirty；该身份不代表新增执行器。当前验收源码及边界见 [#97 核对记录](../evals/star-readiness-97-status.md)。最终 `artifacts/issue-97-final-20261027/loopback-manifest.json` 重新绑定交付源码，配置和 canonical manifest hash 记录于同目录 `delivery.json`。源码或配置变化后须重新登记，不能沿用旧身份；该 loopback 登记不授权真实派发。

## 模型和候选硬限

两题均使用非流式 Intern S2、`star_reference` 和 `verification_mode=auto`。请求 timeout 为 180 秒，单请求最大输出 8192 tokens，客户端 `retry=3`，`thinking_mode=true`，temperature 为 0.2。实际发送配置必须与登记一致；配置漂移时停止。整题审查、S3 账本、S4 绑定和隔离不可关闭。

| 限额 | 简单题单 Run | 多步题单 Run | 全批 |
| --- | ---: | ---: | ---: |
| Run | 1 | 1 | 2 |
| logical calls | 6 | 12 | 18 |
| HTTP attempts | 8 | 16 | 24 |
| 题目工具调用 | 1 | 3 | 4 |
| charged / reserved tokens | 32768 | 65536 | 98304 |
| 墙钟秒数 | 300 | 600 | 900 |

上限参考旧合同的单 Run 数值，全批上限为两个单 Run 上限之和；用户已确认将其作为新执行合同的预算映射。环境预检另限 3 次，含预检的工具调用合计不超过 7 次。全批墙钟从服务启动前开始，包含预检、等待和退避；Run 截止不因恢复重置。缺失用量保留预留，charged 已包含预留，不重复相加。费用未知时记 `null`，不由 token 估算冒充实际费用。

## 停止和判定

发生传输未知、用量不完整或未决、任何失败、取消、硬限、源码或配置漂移、账本或交付绑定缺陷时停止新增派发。保留已发生的 attempt、预留、失败和截止；不自动重发、换题、续跑或提高限额。迟到用量只结算原 attempt，迟到文本不得覆盖终态。需要复验时另立登记和预算。

逐 Run 记录实际阶段和调用来源、真实隔离回执的消费、审查对象、交付文本身份、provider 返回用量、预留和剩余预算。完整响应、阶段链、审查绑定和账本对账用于判断工程闭环；数学正确、错误或未知单独记录。LLM 接受不是数学证明。报告分别标记 scripted、fault-injection、live 和 replay；未触发或未执行均记 `not_covered`。

真实执行前须取得相同源码下的停止、归档、配置和隔离预检证据，再就具体登记与预算取得授权。当前执行器显式拒绝 live，真实 provider 兼容和自然机制触发均未验收。本草案不授权付费派发，也不替代 #80、#87、#95、#96 或 #70 的验收。
