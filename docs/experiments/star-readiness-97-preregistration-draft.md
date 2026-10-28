# #97 v5 非流式两题登记草案

状态：`draft_not_dispatchable`。这是按用户最新指示提出的 v5 登记草案，未授权或执行 live API。源码绑定的待审阅预览为 `artifacts/issue-97-prereg/manifest-v5-reviewed-20261028.json`，对应 hash 见同名 `.sha256` 文件及 `artifacts/issue-97-v5-offline-20261028-r2/delivery.json`。原 Issue #97 合同规定不得提高现有预算；本草案拟议调整该合同的墙钟预算，但不修改远程 GitHub issue。此前 v2/v4 登记与 2026-10-28 两次真实批次均已消费，保持原样，不续跑、不重试，也不由本草案替换。

## 样本与规范化输入

此前曾将多步候选误称为 IMO 2025 第 1 题，现更正：草案候选为 **IMO 2025 Problem 4**，题号及题面已由[IMO 官方题目页](https://www.imo-official.org/problems/2025/)核实（[官方 PDF](https://www.imo-official.org/assets/documents/problems/2025/2025_eng.pdf)）。简单题使用 [Project Euler Problem 5](https://projecteuler.net/problem=5)。样本标签说明登记意图，不保证模型选择特定推理路径。

| 样本 | 来源 | 规范化输入 SHA-256 | 目标 |
| --- | --- | --- | --- |
| `simple-05` | [Project Euler Problem 5](https://projecteuler.net/problem=5) | `66e13c3935ec292ac66513bfbf76dc554e6e1e93c77f6ccbf1334ab98ce0f5e2` | 观察简单题路径、整题审查和交付绑定。 |
| `multi-04` | [IMO 2025 Problem 4](https://www.imo-official.org/problems/2025/) | `db91a829df2f5ad0fc777006698bd95fd3c363946cb025956a6203d81d738e38` | 观察自然产生的多步规划、步骤证据和适用的受控计算。 |

完整题面 `text` 字段保存在被忽略的 `artifacts/issue-97-prereg/draft-v5.json`。本分支只记录来源、样本身份和 hash；执行源码不携带题面，测试使用合成题。输入规范化为 UTF-8、LF 分隔段落、无首尾空白且无末尾换行；哈希针对 `text` 字段本身，不含样本标签。Project Euler 官方页面当前呈现重复的 `divisible` 及冗余的 `with no remainder` 字样，草案将它们规范为单次“evenly divisible”表述；IMO 定义句明确写出整数本身以补足页面省略的数学变量，数学排版以 ASCII 下标记法表示。冻结 manifest 必须使用该草案中的同一文本和本表 hash。

每题至多派发一次，不为触发某种机制而改写提示或替换样本。提高 wall-clock 只给慢请求更多等待时间，**不能保证模型自然选择非快通道**。未自然触发的目标按 `not_covered` 记录，不重跑、不换题。

## 模型条件与拟议预算

两题均使用非流式 Intern S2、`star_reference`、`verification_mode=auto`。单请求 timeout 拟由原 180 秒调整为 600 秒；单请求最大输出 8192 tokens、客户端 `retry=3`、`thinking_mode=true`、temperature 0.2 及其他模型/Reference 条件保持原值，并须在冻结登记中逐项固定。整题审查、S3 账本、S4 绑定和隔离保持开启。

按用户允许提高预算的最新指示，简单题 Run wall-clock 从 300 秒拟调至 900 秒，多步题从 600 秒拟调至 3600 秒，全批从 900 秒拟调至 4800 秒；单请求 timeout 从 180 秒拟调至 600 秒。该调整是对原 Issue #97 “不得提高现有预算”约定的本地拟议变更，仅作用于等待时间，尚不构成对具体 live manifest 的执行授权。

估算依据是 r8 首次 Explore 用时 117.789 秒，而第二次在 180.022 秒超时且未收到响应头。第二次的最终耗时未知，因此不能从这两个观测计算成功率或保证 300 秒足够。600 秒请求等待约为原来的 3.3 倍；多步题 3600 秒相当于 12 次逻辑调用平均 300 秒的规划额度，给大部分请求留出超过既有成功请求两倍的时间。简单题 900 秒相当于已观察到的三次快通道调用各 300 秒。全批 4800 秒覆盖两个 Run 的 4500 秒，再留 300 秒用于启动和环境预检。这是保守规划，不能让每次请求都等待满 600 秒；Run 与批次截止仍会结束本地等待，但不能证明 provider 已取消处理。现有失败证据指向等待超时，未显示 token 或调用次数耗尽，故这两项暂不提高。

| 限额 | 简单题单 Run | 多步题单 Run | 全批 |
| --- | ---: | ---: | ---: |
| Run 数 | 1 | 1 | 2 |
| logical calls | 6 | 12 | 18 |
| HTTP attempts | 8 | 16 | 24 |
| 题目工具调用 | 1 | 3 | 4 |
| charged / reserved tokens | 32768 | 65536 | 98304 |
| Run wall-clock | 900 秒（15 分钟） | 3600 秒（60 分钟） | — |
| 全批 wall-clock | — | — | 4800 秒（80 分钟） |

除上述 wall-clock 和单请求 timeout 外，所有旧上限保持不变：环境预检最多 3 次，含预检的工具调用合计不超过 7 次；输出 token、logical call、HTTP attempt、题目工具和 Run 上限如表。全批 wall-clock 从服务启动前开始，涵盖预检、等待和退避；Run 在准入后取得绝对截止，恢复不重置截止。charged 已包含 reserved，不重复相加；缺失用量保留预留，实际费用未知时记 `null`。

## 停止与冻结条件

传输未知、用量不完整或未决、任何失败或取消、硬限、源码或配置漂移、账本或交付绑定缺陷发生后，停止新增派发。保留已有 attempt、预留、失败和截止；不自动重发、换题、续跑或突破上限。迟到用量只结算原 attempt，迟到文本不得覆盖终态。数学正确性、错误或未知单独记录；LLM 接受不是数学证明。

当前代码已加入 v5 登记、适配器 timeout、协调器批次墙钟与独立一次性消费键；完整发布门禁 873 项通过、零失败、零跳过，测试接缝及六个旁路探针通过。源码身份与报告 hash 见[核对状态](../evals/star-readiness-97-status.md)。交付脚本在本记录提交后，验证相对验收提交仅有文档变化且源码 hash 不变，再生成包含精确题面、hash、模型配置、源码 revision/hash、dirty 状态、硬限及停止条件的不可派发预览。`delivery.json` 分别记录验收和交付的 Git revision，不把两者称为同一身份。冻结后仍须针对该份具体登记再次取得授权，方可执行 live API。此草案不改变旧批次、旧合同或远程 Issue #97。
