# RB06 零付费故障与恢复验收

范围：spec #87 的 ROB-AC-15/16/17/18/23，责任票 #93。公共接缝为认证 Job/Run、resume/cancel、SSE、report 和 Evidence；不改变官方 baseline。E3 不调用真实付费提供方，不替代 RB08 的真实模型与发布门禁。

## 可执行入口

在待验收 worktree 中设置 `MATHAGENT_TEST_PYTHON_IMAGE` 为已验证的精确本地镜像 ID，并运行：

```powershell
uv run --project D:/project/工程化MathAgent/Challenge-Cup-2026 --no-sync python -m tests.rb06_e3
```

`tests/rb06_e3.py` 固定本票定向矩阵，先执行产品与隔离用例，再执行五项旁路。测试失败、skip、expected failure 或探针异常均不能得到 E3 PASS。旁路要求指定的目标断言失败，无关夹具断言不能冒充识别保护。

## 行为与证据矩阵

| 合同 | 公共行为与入口 | 证据类型及限制 |
| --- | --- | --- |
| AC15/18 | `test_star_rb06_recovery`：Docker 回执落盘后 `os._exit(71)`；重启同一 Job，仅继续数值审查、最终生成和整题审查；6 模型、6 HTTP、1 工具，原 deadline 不变 | 真实 loopback HTTP、真实 Docker、真实进程退出；模型回复受控 |
| AC15 | `test_star_rb06_faults`：已完成计算后，取消阻止迟到文本绑定；模型、HTTP、token、工具额度各自拒绝非法派发 | fault-injection；真实 Registry/S3/SQLite，不宣称 Docker |
| AC15/18 | 同文件 unknown 整题审查：无决定的两个 resume 入口均拒绝；显式新身份只重试审查，旧预留/deadline/完成动作保留 | ReadTimeout 故障注入；网络 unknown 不等于数学审查 unknown |
| AC15/18 | 同文件延迟响应头：Run 硬截止停止本地等待，保留 unknown 与预留，迟到用量只结算原 attempt，终态不被文本覆盖 | 真实 loopback HTTP；不代表供应商取消 |
| AC15 | `test_star_product_align_recovery` 的选定用例：跨持久边界退出、预算耗尽和原截止恢复拒绝；旧构建生成的完成/中断快照读取及显式恢复 | 真实进程退出、旧版本执行产物；外部提供方受控 |
| AC16 | `test_star_rb02_computation`、`test_star_product_python`：匹配/不匹配/未比较、无输出、执行失败、真实引用和下载权限 | 真实 Docker；受控模型回复，不能证明数学效果 |
| AC16 | `test_star_product_classified_outcomes` 选定用例：坏回执完整性来源和伪造回执/依赖不进入成果账本 | 公共产品故障注入；不宣称真实磁盘故障自然发生 |
| AC16 | `test_python_executor_docker` 选定用例：网络/文件/资源限制的实际失败、子进程超时清理、取消清理 | 真实 Docker 执行器 seam 的辅助证据；公共 Job 隔离证据另列 |
| AC17 | `rb06_mutations`：错选首个审查、未比较冒充匹配、跳过适用义务、绕过传输硬截止、绕过 S4 | 每个旁路必须命中对应公共行为断言；errors 不计成功 |
| AC18/23 | `test_star_transport_policy`：真实 HTTP 阶段、无换行细流、迟到用量、重试对账；`test_star_product_streaming_recovery` 选定用例：流中退出与人工恢复 | HTTP 生命周期为真实 loopback；进程恢复用受控 SSE；都不是 live 供应商 |
| AC23 | `test_star_rb03_obligations`、`test_star_product_semantics`：数值/带数字 sharp 对照、NOT_FOUND、解释完整性、required 模式与多入口一致 | scripted/fault-injection；LLM 接受不等于形式化验证 |

## 结果解释

E3 PASS 只证明固定版本上的工程故障合同。Challenge、Traceback、Replan 的受控用例不能标为真实模型自然触发；这些 live 项仍为 `not_covered`。真实提供方、E1/E2 数学正确性和延迟门槛、浏览器与最终全量发布门禁由 RB08 验收。费用缺失保持 unavailable，未知预留不按零成本处理。

完整命令、RED/GREEN、环境失败、测试输出、固定提交及未覆盖项保存在本轮仓外 `rb06/IMPLEMENTATION.md` 和同目录日志，不提交运行 raw。
