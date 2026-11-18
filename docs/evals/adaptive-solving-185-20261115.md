# #185 按需求解阶段验收

2026-11-16；起点 `d4bed8a`；最终冻结检查源码 `7b9962c`（产品变更至 `3dc90cc`）。要求见
[策略合同](../engineering/adaptive-solving-185-contract.md)。运行证据位于被忽略的
`artifacts/issue-185/`；不提交实验题集、完整 prompt、凭证或模型 raw。
本票增量工程达到退出条件；完整深度交付、历史持久化间歇故障和数学误判仍按下文保留。

## 实现范围

- 显式 `adaptive-solving-v1`：完整候选直接进入独立整题检查，不固定 polish。
  具体数学异议最多触发一次局部修正，每份候选重新绑定审查；无法完成则规划。
- Planner/Meta 使用已有接缝审查分解质量，消费失败候选、实际异议和未解决义务。
  普通题不强制 Lean；Population 仍受当前能力、容量与预算准入约束。
- `adaptive-resources-v1` 为修复、最终生成和整题审查预留模型、HTTP、本地 token
  与时间份额；实际派发仍由共享账本复核。高预算示例为 96 模型/96 HTTP/24工具/
  4194304 本地计账 token/7200秒，仅供显式新 Run 使用。
- `adaptive-search-v2` 分开记录搜索反馈与证明进度：新实际工具反馈、有效引理和
  确证反例可以允许同目标再次尝试；心跳、猜想改名和重复回执不能刷新进度。
  同上下文 CONTINUE 仍受阻且没有实际工作时明确停止，避免反复进入 Meta。
- 悬空规格依赖、检查点工具字段和 Meta 动作/回退目标冲突进入已有一次协议修复。
  `reason_noncoding` 保持同一检查点协议及目标绑定，合法已审来源可以进入 Proof Graph；
  其他角色、实际响应或审查身份不符仍拒绝。Meta 只有 TRACE_BACK/trace_back 可携带
  正整数回退目标；其余动作必须为 null。可选记忆字段仍有效，不默默改写裁决。
- 原 Job/Run、预算、截止和 unknown 身份不重置；未知零自动重发。SQLite 异常链
  只增加脱敏安全错误码诊断，历史 live-02 根因未确认，不声称已修复。

## 必要反例与审查

每个修复保留失败先于修复的证据；命令参数错误、夹具错误和中止门禁不算有效红或通过。

| 接缝 | 证据（相对 artifacts/issue-185） | 结果 |
| --- | --- | --- |
| 直接候选、一次修正及恢复窗口 | direct-red-02/green-02、recovery-red-02/green、boundaries | 原失败后通过 |
| 可选 metadata、公开策略及只读刷新 | metadata-red/green、projection-red/green | 原失败后通过，刷新零派发 |
| 规格依赖、unknown 与协议修复 | intake-red/green、public-final | 3项公共 Job通过 |
| 工具字段位置 | checkpoint-tool-red/green、checkpoint-regression | 红后绿，32项相关回归 |
| 修复/收尾预留及不递归预留修复 | reserve-red、reserve-repair-red、reserve-policy | 红后绿，21项相关回归 |
| 反馈与证明增益分离 | context-red/green、feedback-progress-red-02/green、final | 红后绿，51项最终聚焦 |
| Meta 原地循环 | meta-loop-red/green、boundaries-03、regression | 2项红后绿，7项边界、67项回归 |
| pure 检查点协议 | noncoding-checkpoint-red、green-02、regression | 4项通过，21项相关回归 |
| pure 来源与 Proof Graph | noncoding-source-red/green、regression | 1项红后绿，44项回归含9组篡改 |
| Meta 动作/目标及一次修复 | meta-target-red02、green02、review-red/green、final-regression | 公共 Job红后绿，最终49项通过 |

集成双轴静态审查固定 `d4bed8a..5544b8f`，无阻塞，见
`integration-review-5544b8f.json`。其后 Meta 切片以 `5544b8f` 为基点：初审发现
数值下限未执行及可选记忆字段被分支排除，分别复现后修复；两轴复审无剩余问题，
见 `meta-target-review.json`。随后通用 minimum 校验改变了 Planner 非法版本的失败
分类及派发，已用命名用例稳定复现，并在 `3dc90cc` 收窄为 Meta 新使用的
exclusiveMinimum；不改变其他角色的原校验路径。见 `meta-minimum-compat-red.json`、
`native-gate-diagnostic/summary.json`及两轴无发现的 `meta-minimum-compat-review.json`。
新切片 Ruff 与 diff 格式检查通过。最终验收草稿另经两轴审查，无需求缺漏，
一处数学答案“5”的含糊表述已澄清，见`final-acceptance-review-3dc90cc.json`。
脚本化 HTTP 只证明工程接缝，不代替真实模型和独立数学核对。

## 冻结版本的真实扩展

普通公共 Job，不注入答案、预制计划或执行模式。模型 `intern-s2`，thinking=false，
temperature=0.2，max_output=32768；高预算配置 SHA256 为
`6c23cb3ed570067bb59bfae7cc2d7364022d63d2db28f141d08c4d4afe964996`。

`live-15` 矩阵单题：新 Job `run_82191bb9cfdd01c95fba2c5f93881f2a`，5次请求、1次工具、
73.540秒、本地计账238747、0未决。正确交付行列式及全部不可逆参数，独立推导一致。
路线是 Explore/工具/整题检查，未触发真实 Meta 修复，不能据此声称该真实接缝已重演。

单题通过后扩展到预登记 `live-10` 的16题；逐题核对通过才派发下一题，首次失败即停止。
全部16题正确交付，accepted/same_artifact、0未决；65次请求、1次工具、各 Job根墙钟
合计622.928秒、本地计账3003410。两批源码均 `dfe8018`，前后快照无漂移。
其后的 `3dc90cc` 只收窄数值约束的校验范围；两批实际路线未调用 Meta。没有把这些
先前冻结案例改记为新 SHA 的真实运行，也未为相同轻量路线重复调用模型。

| 覆盖 | 独立核对内容 |
| --- | --- |
| 同余与最大公约数 | 通解及完备性；全部欧几里得除法 |
| 指数、对数及分式不等式 | 换元范围、定义域、增根及端点 |
| 平方和、特征空间及三角形 | 公式推导；全部特征空间；半径计算依据 |
| 定积分、递推及四次方程 | 正确换元界；归纳证明；全部实根 |
| 重复元素排列与不放回抽样 | 重复计数校正；条件概率和样本空间 |
| 最值、连续加性函数及级数 | 全部取等条件；有理数到实数的推广；有限和及极限 |

每题原输入、身份、实际动作、预算、报告、只读刷新及独立答案 SHA 见各批次
`identity/receipt/final/report/refresh/caseN-independent.json`。17个新 Job共70次请求、
2次工具、根墙钟合计696.468秒、本地计账3242157；provider usage 全部未知。
本地计账不是确认的实际 token 或费用，不计算伪精确的真实 token 效率。

## 开发序列的失败与深度成果

全历史41个已提交 Job：30个独立正确交付、2个数学误判接受、7个失败、2个取消，
共222次请求，保留2个历史未决；见 `all-submitted-results.json`。
这是跨多个源码版本的开发序列，不是固定源码的准确率评测，未派发题不计为成功。

| 批次 | 观察与限制 |
| --- | --- |
| live-01 | 首题正确交付答案5；第二题悬空规格依赖失败，第三题未派发 |
| live-02 | 实际数学修正后进入规划；SQLite OperationalError，1未决保留 |
| live-03 | 工具字段两次非法，一次修复后仍失败；13次请求、无答案 |
| live-04/05 | 前述5个简单/中等题正确；live-05第四题重复 Meta后取消，1未决保留 |
| live-06 | 模幂错误被接受；复数根正确；第三题为停止扩展而取消，后续题未派发 |
| live-07 | 单参数四次式正确完整交付 |
| live-08 | 实际工具、审查、Meta CONTINUE与新纯推理派发；有正确局部引理，协议失败无整题交付 |
| live-09/11 | 分别在 pure 来源及 Verifier JSON接缝失败，均无完整交付 |
| live-12 | Schur题错误证明被接受，独立核对拒绝；不是正确交付 |
| live-13 | 模幂正确交付 |
| live-14 | 前4题正确；矩阵题错误规划被指出，Meta裁决意图正确但回退目标违规，最终失败 |

live-01首题是 `d4bed8a+当时工作树`，不是 `8064136` 干净源码；准确快照
`e03ce2d77cce706b0ebba7ad9274f667d14cd88e7e2d971f9e79d151a34c7f75`，前后无漂移。
其后各批次源码以对应 identity 为准，不回填或改写旧 Run。

深度局部成果：live-08 的持久账本已接纳引理“x非零时，t=x+1/x的像恰为|t|>=2”，
等级为 llm_reviewed，图中 derivation accepted，无来源拒绝；独立核对由
x²−tx+1=0的判别式及非零根确认，见 `live-08/independent-progress-check.json`。
它证明真实探索、审查成果保留及合法继续可达；不是机器证明或完整深度交付。
live-14的S1正确行列式也经工具与局部审查，但后续 Job失败，不作为整题成功。

数学误判分别为 live-06 把模幂答案12判成1，以及 live-12 把排序后的负项误判非负且
等号分析错误。两例均保持 accepted但独立核对失败的事实，没有放宽 Verifier或重写结果。
本票不声称已消除模型数学审查错误，也不声称总体正确率或效率提升。

## 阶段退出

`offline-exit-05` 在冻结源码 `7b9962cbf6755cf2c1802e3970e618cc263d2e20` 上通过
3/3 后端离线阶段：快速检查、完整离线检查（含六组 mutation probes 和两个服务 CLI）、
发布检查。全套2196项、0failure、0error、42skip，1952.767秒；发布27项通过，37.993秒。
42项均为未配置本机验证 Docker image/readiness 环境的专项，不算已执行通过。
总墙钟2074.718秒；前后源码 hash 均为
`5b70206155f800dde47b300ae87296f0fddbc9934311e146f31064b060a86fa3`，
`source_changed=false`。证据见该目录的`status.json`、`source-manifest.json`、
`source-after.json`、`repository-check/tests.json`、`repository-check/diagnostics.log`
和`fast/offline/release.log`。

顺序执行的命令：

```powershell
uv run python scripts/check_fast.py
uv run python scripts/check.py --offline --report-dir artifacts/issue-185/offline-exit-05/repository-check
uv run python scripts/check_showcase_release.py
```

未修改前端，本轮未安装依赖或执行联网 audit，不冒称标准六阶段门禁。
自有测试进程已退出，30分钟临时检查任务已删除；原8100服务未停止。
官方 baseline 11个文件逐项 SHA256一致，见`baseline-exit-7b9962c.json`；官方路径没有重新评分。
门禁后的提交只更新本验收记录和索引，保留上述源码身份，不重跑产品全仓。

`offline-exit-04`（3dc90cc）快速通过；完整离线2196项、2failure、0error、42skip，
1967.057秒，源码无漂移。发布阶段因完整阶段失败未执行。正式断言分别为形式化子尝试
已完成但公共Job仍running，以及关闭干预权限用例的20秒公共观察超时。
前者以真实重试完成后暂停收尾1秒的探针稳定复现：`gate04-formal-red`失败，等待同一
child完成且Job终态后`gate04-formal-green`通过，产品状态机不变。
后者的旧策略夹具在关闭干预后仍连续要求CONTINUE；单次诊断实测40次调用中33次Meta、
约19.618秒，线程仍在正常提交Meta，见`gate04-serial-baseline`。这不能归因于流分片
或已确认的数据库死锁。该测试只验权限隔离，现将关闭场景的脚本裁决改为合法ABORT，
启用场景仍CONTINUE，保留40次根预算、无实验与刷新零调用断言，并断言普通Reasoner确实
执行；不增加等待、不改生产逻辑或旧Run。更正夹具单次诊断4.520秒、8次调用，见
`gate04-serial-corrected-fixture`。33项相关回归通过（`gate04-focused.json`），Ruff与
两轴复审无剩余问题（`gate04-observation-review.json`）。关闭权限夹具不再覆盖旧模式
CONTINUE耗尽预算轨迹，不能据此声称旧模式循环已修复。

`offline-exit-03`（dfe8018）快速通过；完整阶段出现失败标记后主动停止以隔离回归，
最终报告为 worker中止错误、0项汇总，未完成全套、不计通过。第101个失败标记对应的
Planner用例由命名回放确认并修复。另一个并发收尾用例在命名回放中出现10秒等待超时，
后续6项诊断回放及限定3次重复均通过；线程快照已保留，间歇故障根因仍未确认，
没有增加等待时长或改变验收断言。见 `meta-minimum-compat-green.json`（该报告实际为失败）、
`native-gate-diagnostic/`和`native-gate-diagnostic-02/`，不按文件名推断结果。

历史 `offline-exit-02`（b69022b）：快速通过；全套2180项、1failure、0error、42skip，
1957.101秒、源码无漂移。唯一观察超时用例单独通过21.068秒，但根因未确认，不拼成
单次全套通过。`offline-remaining-01`仅补到未执行的mutation/CLI/发布阶段并通过；
中止的gate-01/offline-exit-01也保留。新证据不覆盖或抹去这些失败。

## 最小要求映射与适用范围

| #185要求 | 入口与证据 | 结果 |
| --- | --- | --- |
| 现有缺口与最小策略 | 合同；显式配置与新Run冻结字段 | 实现并有聚焦检查 |
| 简单轻量、中等修正/规划、深度成果与合法继续 | live-15/10；live-02；live-08及live-14 | 轻量正确交付；自然升级与局部成果可达；完整深度交付未覆盖 |
| 模型/源码/策略/输入/预算/动作/核对 | 各批次identity、原输入及独立核对 | 已记录，provider用量未知 |
| 保护边界、重复状态与unknown不重发 | 各红绿反例、49项最终Meta回归及相关边界 | 覆盖内通过；SQLite根因仍未知 |
| 根资源与修复收尾 | reserve-policy及原deadline、真实成本记录 | 工程边界通过，不保证所有困难证明闭合 |
| 诚实报告结果 | 41个提交Job全量记录，不筛去失败 | 已完成；不作统计能力结论 |
| baseline与最终检查 | baseline-exit-7b9962c.json；offline-exit-05；各切片双轴审查 | 11个字节校验一致；3/3离线阶段通过；42skip不计通过 |

未触发能力保持未覆盖，不无限重跑直到碰巧成功。SQLite历史故障及模型误判是明确限制；
本票的增量工程证据不替代 #183 整体服务或 #157 独立数学效果验收。
GitHub Issue状态未由本次本地检查自动变更。
