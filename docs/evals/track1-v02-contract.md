# RiCL v0.2 Track 1 单题交接

主仓提供单题控制与用量记账。实验仓负责冻结题目、编排四条件、离线评价和计算对比曲线。当前工作归 [Runtime #272](https://github.com/RUSS0718/RiCL/issues/272) 和 [实验仓 #35](https://github.com/RUSS0718/RiCL-experiemnt/issues/35)。

## 运行与记录

用 `uv run python -m ricl_runtime.track1_cli --help` 查看入口。向 Runtime 传单题题面文件、题目 ID、条件、源码提交以及请求、Token 和费用限额。参考答案留在实验仓。运行目录保存 `run.json` 与脱敏 `trace.jsonl`。所有出网阶段共享 Token 预算。费用估算按网关公布的最高适用倍率计算，实付状态单列。记录已开始请求、已确认用量、失败分类及未执行项。筛题使用 `--screen --condition B1 --request-limit 1`，只采样首答。批次用 `--reasoning-effort` 固定思考强度。

`B1` 用独立采样与核查排序选答，`B2` 在同一路线修复，`B3` 用独立完整候选与核查得分管理搜索，`RiCL_v0.2` 根据核查结果继续、剪枝修复或切换路线。初始解答通过后直接交付。待修复时才抽取引理。处理臂经过独立复核，运行轨迹记录请求、剪枝节点与发给下一请求的引理 ID。

## 核查证据

- L1 用 Python 有界解释器核查闭合等式、一元多项式恒等式和特值反例。多项式恒等式用次数上界和有理数精确求值核对。语法只含白名单算术，模型文字只作为数据。特值成立仍记为 `uncheckable`。L1 结果的适用范围限于被检查的等式或反例。
- L2 在独立 API 上下文审阅候选。批次使用同一模型，作用域为独立的步骤审查。离线准确率直接和评价侧参考答案对照。
- DAG 以拓扑序校验前提，已知失效向下游传播。轨迹区分保留下来的节点与后续请求实际携带的节点。模型是否使用引理仍需相应证据。

首批题目来自 AIMO3 官方参考集，许可为 CC BY-SA 4.0。本地冻结文件记录题面和答案键的散列。[竞赛数据说明](https://www.kaggle.com/competitions/ai-mathematical-olympiad-progress-prize-3/data) · [真实 smoke 记录](track1-v02-smoke-20261126.md)
