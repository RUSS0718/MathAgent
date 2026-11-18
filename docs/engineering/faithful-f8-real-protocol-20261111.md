# F8 真实题集试点合同

日期：2026-11-11。状态：frozen；版本 `faithful-f8-real-v1`。接续 [#157](https://github.com/RUSS0718/MathAgent/issues/157)，不修改 [已冻结工程协议](faithful-f8-protocol-20261111.md) 或其 98 个未运行槽。实际源码、配置、runner 与本文 hash 由新批次 manifest 绑定。

冻结审查：固定点 `84b7df40b3b3e1e640c89aa3a9724dee5e7714c9`。Standards（Fermat）无阻塞；Spec（Russell）发现 G 记忆捕获时序、F 条件执行出口、G 表达 rubric 三项问题，均已修正并经原审查者定向复查解除。审查输入为本文新增全文及 #157／工程合同；审查只解除合同阻塞，不代表实验通过。后续语义变化另建版本，不能覆盖本合同绑定的批次。

## 已确认的授权和范围

用户授权继续真实运行及使用、调整资源；沿用 #134 已有资源决议。官方平台无法重评分，记 `unavailable`，不再作为本轮待执行实验；11 文件 baseline 只核对字节，不声称重新获得 88 分。provider 未返回 usage 不阻塞：`usage_policy=observe_only`，实际 token 和费用未知保持 null/unknown，本地预留及调用、工具和时间约束仍有效。断流导致请求结果未知与单纯缺 usage 分开，前者零自动重发。

已完成两道自拟开发控制题的真实 Intern 链路及独立整数答案匹配，共六次 HTTP；不计入竞赛样本。具体 agent 型号无法独立确认，记 unknown，继承当前选择不主动更换；solver 请求 `intern-s2`，已观察返回 `Intern-S2`，精确快照 unknown。

## 输入、参考答案与评分

使用已核验上游固定版本的 14 道候选题；输入文件 SHA256 为 `345b891e3c45f6a95a5b69107d294f7a2f61bd29843c5ba2a82b9c8cd4a0cd7f`，上游 commit 为 `5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d`。这是便利样本，项目开发使用历史 unknown，不称独立留出集。题面、参考材料和答案只保存在 ignored artifacts，不进入公开包；solver 只接收题面，参考答案和证明不进入其上下文。公开文档只留身份、hash、统计和限制；不作题库再分发授权声明。

9 道最终答案题、5 道证明题事前分开。私密参考文件 SHA256 为 `99ad996c413dd5510a34893038c9d13a30f0e4eab9881a9f87aca6ac53f0ea8c`，包含逐题 input hash、来源 URL、下载字节 hash、来源类型及答案或参考证明。AIME 采用已发布答案表，三题由独立枚举再核对；HMMT 采用赛事官网链接的官方解答，其中两题另作独立精确计算；Putnam 为 MAA 官方解答；IMO 为 Evan Chen 署名解答笔记，不冒称官方；Apex 为 MathArena 固定修订 `ac8a641db12cc87be39e61ea89f2e04c80c5f2e7` 的参考答案，题面逐字匹配，只作为 curated reference，不冒称官方证明。任一参考争议保持 unresolved，不能按模型多数票替换。

数值提取器只接收全文单个有理数，或答案中唯一一个平衡的 `\\boxed{...}`，允许整数、小数、a/b、`\\frac{a}{b}`、`\\dfrac{a}{b}`、正负号和首尾数学定界符；采用整数/Fraction 精确比较，不用 eval、浮点容差、符号猜测或从推导中挑数。多 boxed、嵌套不完整、多个候选和其他表达式一律 unresolved，保留原答案 hash。开发验收覆盖负分数、前导零、两个 boxed、截断和恶意文本。引用参考相符记 correct，不相符记 incorrect；执行或提取未决不冒称数学错误。

每组数值主率为 correct/14（scope=all_registered），同时列 correct/9（scope=answer_items）与 correct/N_decidable（scope=decidable_answers）；证明题不进入数值可判定分母。7 组共 98 登记槽、63 答案槽、35 证明槽。六种执行状态与 comparison_status 沿用工程协议，计数守恒；模型辅助证明判决单独汇总，不拼入数值正确率或真人 L3。

## 固定分组和条件任务

| 组 | 本批策略、对照和执行条件 |
| --- | --- |
| A | 显式 star_limited；stream_activity、context_pack、problem_spec、progress_scheduling、final_generation、final_solution_review、strict_completion 开启。固定隔离 Python 工具在 A/B/C/G 一致启用。它是 Harness 对照，非官方 ReasoningAgent。14 题必需执行。 |
| B | A 加 proof_graph，14 题必需执行；对照 A。 |
| C | B 加 serial_routes，14 题必需执行；对照 B，serial-aprs-v1 不称并发。允许记录 checkpoint，但不注入干预。 |
| D | 先在新身份下用两道开发控制题并发进行容量探测；保存实际请求重叠、终态及绑定。仅探测成功且有可验证重叠时，登记 max_inflight=2/worker_slots=2 的观测容量证据，再冻结 D 子批次配置运行 14 题。观测不是 provider 限额或 SLA。失败则保留 14 not_run 和阻塞。concurrent-aprs-v1 会同时改变 challenge=1、context_pack/stream_activity 等 preset；列完整差异，对 C 记 not_comparable，不归因单一并发。 |
| E | 14 原题不属于当前 rational-polynomial-identity-v1 整题模板，original_problem 槽记 unsupported，不造一个旁支恒等式冒充整题。另以固定真实 Lean 专项核对已支持形式目标和缓存当前复核，单列受控工具证据，既不填自然题槽也不升级真人 L3。 |
| F | parent=C 的串行专项。只在真实公共失败来源、合法暂停 checkpoint、可登记 reasoning_method 干预及两臂预算齐备时，追加独立 F manifest 冻结源事件、假设、动作、两臂顺序和控制变量后执行。无合法失败来源时 not_run/no_eligible_checkpoint，不人为制造失败。完整 Population→干预组合明确 unsupported；不与 E 作单因素比较。 |
| G | parent=C；14 题必需执行。每题独立全新空 scope，C 启动前显式开启 population memory scope 与 injection，核对 C 实际注入零条；C 收尾按既有规则捕获来源观察后，在同一 session 运行同题 G 暖条件，并请求独立 F6 表达/记忆视图。相同问题历史有意用于暖条件，必须报告 C/G 实际 advisory 条数、来源 Run 和权限；没有合格记忆即 not_covered，不能声称记忆增益。不同题 session 隔离。Global Goal Cache 自然题无支持目标，记 unsupported；真实缓存复核仅见 E 专项。对 C 属组合机制/暖启动比较，不作单一因素因果结论。 |

先登记全部 98 槽。顺序按输入文件的 14 个 sample ID，每题 A→B→C→G；只保留一次预登记主运行，无自动数学重跑。D 容量探测独立进行，随后 D 题序相同。F 为条件专项而非任意连续 A–G 累加。故障停止受影响批次，余槽 not_run 并保留原因；修复需要新版本，不能覆盖失败或把不同版本拼为可比主批次。

## 配置、工具与资源

Intern provider endpoint 为 `https://chat.intern-ai.org.cn/api/v1/chat/completions`；temperature=0.2、thinking=false、max_output_tokens=32768，stream_first 与 faithful-stream-v1；真实应用的 timeout/retry、profile 指纹及 prompt 源文件 hash 在 manifest 保存。凭证只从进程环境读取，manifest 只记变量名。

ContextPack 使用现有 context-capacity-v1 / utf8-bytes-per-three-v1；input_cap_tokens=null、cap_source=unknown、source_date=null，output_reserve_tokens=32768、safety_margin_tokens=0。这是未标定策略，记录 uncalibrated/capacity_is_hard_guarantee=false，不伪造 provider 容量；每次仍核对真实 model/endpoint。新真实合同允许该现有未知容量模式，不把旧受控容量当作线上证据。

每个自然题 Run 沿用已授权 readiness-31 任务容器上限：512 model calls、512 HTTP、128 tools、67108864 本地 token reserve、28800 秒。不是 provider/账户硬限制，后者 unknown。批次总 deadline 为启动后所有预登记必需 Run 时长上限之和，保存实际绝对截止；不因新身份、恢复或缺 usage 重置。仅一个批次后台协调器，各普通题串行；容量探测和 D worker 才允许冻结的两路并发。机器资源和镜像状态事前快照，遇冲突先归因，不抢占用户 UI 工作。

固定 Python 镜像 `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d`，原有 docker-python-v1、20 秒、16000 bytes 输出限制；网络禁用和隔离策略不变。Lean 复用 artifacts/faithful-s09-environment-final-02/deployment.json 的精确镜像、Mathlib、公理及原有 30 秒工具限额，不扩目标域。模型未自然请求工具则记 not_covered，不以另外的工具测试补标自然调用成功。

停止条件：未知远端/工具结果、已知执行协议失败、未完成交付、binding 缺陷、源码/config/prompt/模型漂移、硬截止或预算违规。仅答案 incorrect 不停批。usage 单纯缺失不停批；不释放未知预留、不按零计费。遇问题按 #157 归因、索引和最小修复循环处理。

## 辅助审查、验收和导出

固定 seed=`faithful-f8-real-20261111-v1`。9 道数值题和 5 道证明题分两层，各层按 SHA256(seed+':'+sample_id+':1') 排序，各取前 2 题跨 A–G 共同抽查，共 28 槽；每组 4 槽，明确未覆盖的领域，不按结果或成功状态替换。R1/R2 两个隔离子智能体独立审查同一封存题面、实际答案、私密参考及来源身份；看不到对方判决。R3 在二者封存后核对全部 28 槽，逐项解释分歧。没有产物仍 unresolved。判决 pass/fail/unresolved；理由只写可公开的数学结论和可核对缺口，不存隐藏推理。角色、实际可确认模型或 unknown、输入/输出 hash、时间、Run/answer/source 身份必须齐备。模型同源和共同错误风险保留；independent_math/human_L3=not_run。

G 抽中且有表达产物的 4 个槽，R1/R2/R3 另按 `faithful-explanation-rubric-v1` 各项 0–2 评分：忠实于原答案、来源可追溯、推导覆盖、等级／限制准确、表达清晰。保存逐项理由、产物/段落/原答案身份、缺失数和分歧；无产物保持 null/unresolved，不插补。解释评分不进入数学正确率。

L1 固定 25 ID 与入口复用工程合同；源码未变可引用已封存完整门禁及 L1，不重复跑 F7。另跑精确提取器/登记守恒/manifest、持久 Job→report→evidence→交付绑定可执行验收。L2 专项的 target/hash/environment 和分母在派发前冻结，目标 pass 不填入 original_problem；自然 L2 不支持保持 0/98，并报告 eligible=0。工程、真实工具、provider-live、自然题数值、辅助数学和真人判断六栏分开。

每批 schema 为 faithful-f8-real-manifest-v1，结果为 faithful-f8-real-results-v1；均使用 UTF-8 规范 JSON、SHA256 旁置回执及禁止覆盖写。manifest 至少包含 protocol/hash、source_identity/lock/baseline hashes、每组完整 requested/applied config/hash、provider/model/prompt 身份、输入/参考 hash、种子/顺序/重复/98 登记、工具镜像/环境/预算/停止条件/审查抽样。实际结果只追加，保留 intent UUID、Job/Run、原始脱敏公共 job/report/evidence、交付文本 hash、执行/结算/数学/比较状态、真实 HTTP/tools/usage 和所有缺失原因。

出口：A/B/C/G 的 56 个必需主槽获得终态；D 容量条件任务和 E 工具专项有实测或具体失败/不适用证据；F 按 14 个 C 来源逐题筛查并保存来源/暂停资格/预算原因，有合格 checkpoint 时必须完成冻结双臂执行及结果报告，无合法来源才允许条件性 not_run/no_eligible_checkpoint，已有来源但因预算或停止条件未执行继续阻塞。全部 98 槽状态守恒，参考数值与辅助审查、解释 rubric、完整性校验和公共来源绑定完成，双轴问题解除。若必须任务因停止条件仍未运行，#157 保持开放，不以补 not_run 宣称完成。没有产品源码变化时引用原工程门禁；如修复产品，按工程门禁先聚焦、双轴复查，再冻结最终源码运行唯一完整门禁。更新验收记录/索引、中文 conventional commit 并推送当前分支，不合并 main。
