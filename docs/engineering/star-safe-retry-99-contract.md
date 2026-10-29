# #99 安全传输重试合同

状态：离线工程验收通过；基点 `dc9dc807314ad3fe27373e9a5111fdf3dcc6752a`，Refs: #99。结果与限制见[验收记录](../evals/star-safe-retry-99-acceptance.md)。

## 范围与决策

沿用 #98 的绝对截止、未知预留和迟到对账。只修改本票传输策略、adapter 最小接线、必要的等待前预算准入及专属测试；协议 repair、恢复和诊断实现不变。

为保留 ADR-0014 的旧默认，新增显式 `InternChatClient(safe_retry_attempts=6)`（总 attempts，合法范围 1–6），adapter 延迟创建 client 时使用 `client_safe_retry_attempts=6`。未设置时沿用 `min(retry, 3)`；未绑定账本时仍只遵循历史 `retry`，新选项不生效。既有 STAR 默认 `client_retry=3` 与历史实验登记不变。此文细化 ADR-0014 的显式产品策略，只对新 opt-in 放宽上限，不改旧默认。

nonstream 由 client 独占重试权威；stream 由 stream adapter 独占权威，复用同一限额及安全分类。显式安全连接失败等待 1/2/4/8/15 秒；有效 429 遵循非负、有限且适合原截止的 Retry-After。ReadTimeout、一般连接中断、400/401、一般 5xx 不自动重发。429 缺 usage 继续保留预留，不假定免费。

等待前检查剩余时间、取消、下一 HTTP 和输入加输出 token 额度，不创建虚假 attempt；派发前保留原子复验。一次 logical 只预留一次，每次实际 HTTP 独立 ID、序号和预留/结算。已知协议失败的 repair 保持独立 logical 身份，不实现 #100。

## 切片与验收映射

| 切片 / 公共接缝 | 验证内容 | 未覆盖 |
| --- | --- | --- |
| `InternModelAdapter.complete` / `InternStreamAdapter.stream_complete` | 显式 6 次及 1/2/4/8/15，末次不等待，独立 attempt/同一 logical，旧默认和非 metered 行为 | 真实 provider |
| 同上，F02 故障矩阵 | ConnectTimeout、有效/非法 429、400/401/5xx、ReadTimeout/断流；原预留/deadline，零未知重发 | provider 幂等性 |
| 公共 call + Run 账本 | 等待前 HTTP/token/时间不足即停，等待后准入复验，429 未知用量保留 | 硬实时/远端取消 |
| 认证公共 Job / 既有 CLI | 安全重试后完成、未知进入 needs_review；transport 与 repair 不乘法且身份分离；CLI 入口相关回归 | 新 CLI 参数、#100 实现 |
| baseline / 官方入口回归 | 冻结字节、JSON、默认调用及输出预算不变 | 数学能力提升 |

每片先执行失败测试，再实施最小代码并记录 green。检查统一 `uv run`，只使用离线替身或 loopback。完整相关模块、必要 #98/预算/协议/CLI 回归及 Ruff/baseline 由本票执行；约 22 分钟的全仓组合门禁交主聊天协调，不将未运行或 skip 记为通过。
