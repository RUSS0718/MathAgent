# RiCL v0.2 Track 1 单题交接

主仓提供单题控制与用量记账。实验仓负责冻结题目、编排四条件、离线评价和计算对比曲线。当前工作归 [Runtime #272](https://github.com/RUSS0718/RiCL/issues/272) 和 [实验仓 #35](https://github.com/RUSS0718/RiCL-experiemnt/issues/35)。

## 运行与记录

用 `uv run python -m ricl_runtime.track1_cli --help` 查看入口。向 Runtime 传单题题面文件、题目 ID、条件、源码提交以及请求、Token 和费用限额。参考答案留在实验仓。运行目录保存 `run.json` 与脱敏 `trace.jsonl`。所有出网阶段共享 Token 预算。费用估算按网关公布的最高适用倍率计算，实付状态单列。记录已开始请求、已确认用量、失败分类及未执行项。筛题使用 `--screen --condition B1 --request-limit 1`，只采样首答。批次用 `--reasoning-effort` 固定思考强度。诊断批可指定 `none`，同时发送关闭思考的开关，并用返回的 Token 细分核对行为。

官方 DeepSeek 配置使用 `BASE_URL=https://api.deepseek.com` 与 `MODEL=deepseek-flash`，配合本机匹配的 `API_KEY`；SiliconFlow 配置使用 `BASE_URL=https://api.siliconflow.cn/v1` 与 `MODEL=Qwen/Qwen3.5-35B-A3B`（求解阶段启用 `enable_thinking=True` 与 `thinking_budget`，JSON 辅助审查阶段关闭思考）。同一 Run 固定端点、模型与价格上界。[官方模型与价表](https://api-docs.deepseek.com/quick_start/pricing/)

`B1` 用独立采样与核查排序选答，`B2` 在同一路线保留首错前已核查前缀重推（StepCo 风格），`B3` 为平面 `RSE + Same Verifier`（抽取正面引理与负面教训并经相同 L1/L2 核查筛选后注入下轮，不做依赖图撤回），`B4` 为无引理打捞的纯换路对照（`Switch without Salvage`），`RiCL_v0.2` 启用“分歧/异常门控 + 单次合并 `review_extract` + `SharedReasoningState` + 纯 Python `APRS` 多路边际收益调度”：首答之后发起轻量独立探路，若两路终答一致则直接 `consensus_passed` 交付；仅当发生分歧或截断/缺答时，才触发单次合并核查抽取并由 `APRS` 在活跃路线上调度继续（最多 1 次）、依赖剪枝局部修复（保留首错前已核查前缀、首错后非连续独立引理与失败约束）或跨路打捞切换路线（附带累计失败路线约束）。

## 核查证据

- L1 用 Python 有界解释器及 AST 白名单 SymPy 核查闭合等式（含根式、阶乘、三角恒等式等）、单/多变量多项式与符号恒等式，以及特值反例。模型文本仅作 AST 数据解析（禁止 `sympify` 原始字符串），特值成立仍记为 `uncheckable`。L1 结果的适用范围限于被检查的等式或反例。
- L2 在独立 API 上下文审阅候选。单独核查、引理抽取与合并 `review_extract` 使用 JSON 对象模式，输出上限分别为 2,048、4,096 与 4,096 Token，预检按 `ceil(bytes/2) + 512` 与输出上限保守估算。批次使用同一模型，作用域为独立的步骤审查。离线准确率直接和评价侧参考答案对照。
- DAG 以拓扑序校验前提，已知失效向下游传播；`source_quote` 校验允许轻度 LaTeX/空格归一化匹配，并在 L2 返回 `unknown`/`incomplete` 时仍按规则准入未污染的 L1/L2 独立引理，同时由 `SharedReasoningState` 跟踪跨路失效撤回。轨迹记录准入标签、实际派发的引理 ID 与响应中的显式引用。
- 抽取优先保留已审查前缀内的独立事实，允许 1 至 10 个节点。Trace 记录抽取状态、节点数和第一个被拒节点的位置。`--stop-after-salvage-dispatch` 在收到非空引理路线切换的 Provider 响应后停止，适用于派发 smoke。该次新路线的解答仍未经过独立复核。
- 剪枝修复未通过后，已有合格引理池可直接供下一条路线使用，无需再次浪费辅助抽图调用。派发 smoke 的非空切换仅预留派发所需的一次请求。
- 抽取可为 L2 提供 `source_quote`。Runtime 核对它与编号步骤的原文一致后，用该原文作为入池候选内容，继续执行原有作用域、首错和依赖证据校验。

首批题目来自 AIMO3 官方参考集，许可为 CC BY-SA 4.0。本地冻结文件记录题面和答案键的散列。[竞赛数据说明](https://www.kaggle.com/competitions/ai-mathematical-olympiad-progress-prize-3/data) · [真实 smoke 记录](track1-v02-smoke-20261126.md)
