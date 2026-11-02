# RB-03：短题完整交付与证明义务合同

适用范围：[RB-03 #90](https://github.com/RUSS0718/MathAgent/issues/90)，对应父规格 #87 的 ROB-AC-07、08、09。本合同描述协议和控制行为，不代表真实模型能力验收。

## Explore 与整题审查

`SOLVED.solution_candidate` 包含满足原题要求的完整推导、条件、定义域、答案形式和所要求的简要解释。`explore_polish` 在原 Explore 会话中保留这些内容，输出可独立阅读的完整候选。新会话的整题 Verifier 审查实际候选；即使数值正确，缺少必要解释仍应 `REJECT` 并进入既有 Plan 路径。

正常完整候选沿用 Explore → 同会话润色 → 新整题审查的三调用路径。运行时没有算术特判、逐题难度分类调用或强制三调用接受逻辑。计算、Challenge、反例搜索、Meta 和最终绑定仍按原合同执行。

## `answer_claim.claim_type` 增量字段

该字段仅位于步骤 Verifier 的 `answer_claim` 中。既有四个必填字段 `claim_index`、`both_directions_proved`、`assumptions`、`approach` 保持不变。`claim_index` 必须是当前 StepReport 的有效零起始整数索引；控制器从该索引取得真实 claim 文本，不接受另行提供的 claim 或 scope 来替换目标。

| `claim_type` | 适用义务 |
| --- | --- |
| `numerical_evaluation` | 普通有限数值求值，无需双向证明。`both_directions_proved=false` 不触发双向反例搜索，也不免除 Goal Gate、Logic Gate 和整题审查。 |
| `sharp_bound` | 界成立及 sharpness。仅给出界或等号例均不完整。 |
| `extremum` | 界成立及取得性，或命题要求的极限论证。 |
| `necessary_and_sufficient` | 必要性和充分性，即两个蕴含方向。 |
| `general_proof` | 其他证明声明，保守沿用原义务检查，不提供有限求值豁免。 |
| 字段缺省 | 旧声明保守沿用原行为；不从文本、标签或数字推断有限求值豁免。 |

Verifier 声明数学适用性；控制器检查结构、枚举、目标索引和所指报告。数字是否出现不参与路由。`claim_type` 不是确定性数学分类器，模型误分类仍需独立数学验收；受控提供方不能证明真实模型正确分类。

## 缺方向与矛盾声明

适用声明的 `both_directions_proved=false` 不能被 ACCEPT 提前推进。合法 Gate 下执行既有独立、无工具的有界反例搜索。`FOUND_COUNTEREXAMPLE` 形成 FAIL 的 Challenge；`NOT_FOUND` 形成 UNCERTAIN 的 Challenge，不能补齐证明。

分类账本拒绝把缺方向的目标升级为任何已证类别，包括 Lemma 和 Answer。声明引用目标索引、声明同一文本或未指定索引时均受此限制。独立索引上的已证部分成果仍可保留，Conjecture 仍为未证。

ACCEPT 与 Goal Gate 或 Logic Gate 矛盾时，裁决无效，保留原 Gate，不额外派发反例搜索。非法索引使裁决无效；非法字段或枚举仍经严格 schema 处理，至多一次既有格式修复。反例与 Challenge 沿用原 Run 的调用预算、次数上限和截止，不扩额或自动重试未知请求。

## 历史与证据边界

新字段可选，旧回复、fixture 和快照无需迁移。已完成调用和历史账本不会因本变更重写；只读读取和 replay 不派发调用。本修复不追溯改判历史错误账本。

公共测试位于 `tests/test_star_rb03_obligations.py`，只替换外部提供方 HTTP，实际运行 Adapter、控制器、SQLite、S3 预算、S4 绑定、Job、SSE、报告和 Evidence。测试覆盖 17×23 完整解释的三调用、遗漏解释后的 Plan、含数字的数值与 sharp/极值/iff 对照、NOT_FOUND 升级拒绝、矛盾声明与有界终止。

外部请求断言证明指令实际发送；脚本回复证明控制行为。两者均不证明 live 模型自然遵循指令或获得性能提升。真实 E1 与 E2、完整发布检查由 RB-08 执行。
