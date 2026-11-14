# #178 自然题形式目标与验证范围验收

日期：2026-11-14（Asia/Shanghai）。任务为 [#178](https://github.com/RUSS0718/MathAgent/issues/178)，父规格 [#168](https://github.com/RUSS0718/MathAgent/issues/168)；[任务合同](../engineering/faithful-service-178-contract.md)。本票接通普通输入到受限目标、真实 Lean 与持久公开证据。真实代表题取得正确答案及 L2，未取得原题对应独立审查 L3；不据此宣称一般自然语言形式化或数学能力提升，#168 完整服务未完成。

## 源码与行为

起点 `fa7739ba8cfafd10b9498dc856aee1db79923a8d`；产品提交 `209640d` 和 `19666bf`。最终产品源码为 `19666bff3f30ad4ea26e67920e2b9806a2e50937`，随后测试响应修复 `f00842000c666c9cdc785a7c41bdb073d9d8925e` 为最终门禁源码。交付后的文档提交另记实际 Git HEAD，不改写运行身份。官方 baseline 未修改，最终字节与导入检查见门禁。

普通 faithful problem_intake 在原调用中提出 proposed、unsupported 或 not_selected，并区分数学证明与明确机器要求。服务器校验受限单变量有理多项式全称等式，冻结原题、有效规格、义务、生成调用及策略哈希；不额外调用模型。澄清后重绑最终规格，关联改题重新生成，不沿用旧题策略。

生成、独立对应审核与 Lean 执行分责。共享要求判定核对当前有效回执、等级、指定对象及覆盖；局部 L2 或来源不足的 L3 不能满足整题要求。必要验证未满足时保留答案并明确失败；可选验证失败保留合法普通答案。重试清除旧 assessment，保留原 verification_mode；只有同源整题审查接受的失败 Job 才可进入既有重试路径，CAS 与所有者检查保留。unknown 不自动重发。

## Issue 验收映射

| 条件 | 公共入口与可观察状态 | 检查与证据 | 结果 |
| --- | --- | --- | --- |
| 1 来源、保留条件、分责、原任务计账 | 普通提交后的 policy.source、ProblemSpec、Attempt、根预算 | test_faithful_formal_generation；test_clarification_172 的有效规格重绑；live03 Job、Report、持久快照 | pass：同一 intake，4 模型调用与 1 工具调用 |
| 2 受限后端与审查边界 | supported 目标及 unsupported 原因；L2、not_reviewed | 公共生成案例、live03 内核回执、三个对应记录 | pass：真实 L2，没有 L3 冒认 |
| 3 用户要求与整体满足 | assessment 与 Job/Report semantics；必要失败保留答案 | test_faithful_formal_requirement；公共 required retry；coverage-red/green、retry-red/green、retry-mode-red/green | pass：局部成功反例与重试边界 |
| 4 普通输入、Lean、答案与刷新 | Chromium Enter 提交，公共 Job、Report、Evidence；同 Attempt 刷新 | live03 全链、acceptance-reconciliation.json；live02 可选失败；受控公共必要未满足 | pass：本例 L2 与正确答案；一般 L3 未实证 |
| 5 公开范围与错误含义 | Run 页形式验证区的目标、L2、对应待复核、覆盖为空、等级说明 | readonly-ui-result.json、readonly-formal-section.png；frontend-final.log | pass：实际浏览器只读重开，无写请求、无脚本错误 |

所有本票运行证据位于忽略目录 `artifacts/issue-178/`。受控模型只证明工程合同，不能作为真实数学证据。测试入口使用 `uv run python scripts/run_unittest_report.py --expect-count N <selectors>`；具体 selector、命令、数量及失败详情保存在各 JSON 报告。聚焦回归 regression 为 45 项，澄清复核 9 项，重试模式复核 3 项，意图修复复核 2 项；均无 failure、error、skip。前端聚焦 16 项、类型检查及构建通过。最终全仓结果见下节。

## 三次真实运行与原失败

三次均从普通 Chromium 输入进入标准 faithful 配置与官方工具装配，没有请求拦截或替换模型回答；根上限均为 48 模型调用、48 HTTP、8 工具、262144 tokens、1100 秒。provider 为 Intern-S2，usage 缺失时使用已有保守预留，不声称实测 token 数。provider 名称不等于助手型号。

| 目录 | 源码 | Run/Job | 配置 SHA256 | 实际结果 |
| --- | --- | --- | --- | --- |
| live01 | 209640d | run_a5f20fef2683a0b9d19382e9a8e4db50 | 810e667f1161ab8acb584b41e225dce1b66e6525541411a6d8a22f5dc338adf9 | 平方恒等式；5 模型调用后预算耗尽，没有通过整题审查的答案；Lean 30 秒 timeout，unknown 不重发 |
| live02 | 19666bf | run_536de2f7ce747fa943a3c27cf536f12d | cbccbac856dea20098ffda20a8b38b3f3eed6523b8c35ba9c5c9a05e2fb0b359 | x+x=2*x；正确答案，4 模型调用；require_formal=false；512 MiB、90 秒配置下 Lean exit152，stderr 为 CPU time limit exceeded |
| live03 | 19666bf | run_72ce600c5b590273aa100f782fea0893 | 45a917d23852677489311e7c7134c4c0d349f2bb85c294fa2eb8e9e351d65e53 | 同题、同根预算，仅独立新任务工具内存改为允许的1024 MiB；正确答案，4 模型调用，真实 Lean solved/L2 |

live01 暴露 intake 将工具指令误当用户机器要求，最小提示修复及2项聚焦验证见 intent-focused。live02 的 CPU 限制退出是已确认事实；内存压力导致耗时只是诊断推测，不将其写成 OOM。live03 是有明确资源诊断目的的最后一次尝试，不复用旧 unknown 身份。

live03 的 Formal Attempt 为 `formal_037b1ab5ec044ec08d1e672ab8b55835`。真实 ProofArtifact accepted=true、kernel_exit=0、cleanup_verified=true；耗时3.875秒，内存峰值740966400字节。Lean4.19.0、Mathlib v4.19.0、模板 rational-polynomial-v1；镜像 `sha256:ee09c4046b8edace6a8a8ae9cb9ff620ae576595c4f22f64b19b1faa36636101`，manifest `d3df9408de92f16af1757aa97a574bff1fd8b47a00625759e64fd55309d15c75`。公开回执与持久快照一致。

答案以分配律给出 `x+x=(1+1)x=2x`，对全部有理数成立；该简单恒等式已人工核对。整题 LLM 审查绑定相同答案，仍仅为 LLM_REVIEWED。自然生成规格含 output_requirements，固定模板审核未批准对应链，三个 review_status 均 not_reviewed，因此只授 L2。assessment 为 default、formal_grade_insufficient、整题覆盖为空，不能称整题 L3 满足。

原 live03 acceptance.json 保持 failed：初始脚本额外要求实际 L3，且只接受连续子串 x+x=2x，没有接受带中间步骤的等式。独立 acceptance-reconciliation.json 记录 Issue 所需 L2 路径及答案核对，不覆盖原失败、不升级等级。合同取消额外的自然 L3 成功要求，保留真实 L2、正确答案、来源与恢复要求；一般原题对应 L3 仍未实证，留 #183 核对，不成为本票虚假完成证据。

原刷新 mutation_delta=0、Attempt 不变、无 pageerror。随后停止并按同配置重开服务，仅 GET 既有 Run 页；readonly-ui-result.json 六项检查通过，截图明确显示 L2、目标、原题对应待复核、空覆盖和错误不作反证。只读复核没有派发新任务，之后服务已停止。

## 双轴审查与门禁

Standards 和 Spec 分别审查同一纵切。Standards 发现旧 assessment 和重试模式问题；Spec 发现澄清后选择未重绑，均已修复并作受影响复核。Standards 撤回原先关于未持久顶层 status/error 的判断，保留审查更正。最终 standards-recheck-02.md、spec-recheck.md 和 spec-intent-recheck.md 无剩余阻塞；全部审查代理已关闭。报告及文件哈希位于 reviews/。

最终冻结源码 f008420 的 gate-02 六阶段通过，source_changed=false。完整测试2087项、0 failure、0 error、49 skip；skip不计通过。快速检查、mutation probes、CLI、发布检查、前端安装、audit（0漏洞）、测试、类型检查与构建通过。证据 `artifacts/issue-178/gate-control/runs/gate-02/`。原 gate-01 为2087项、1 failure、0 error、49 skip，保持failed：标准配置的受控HTTP fixture缺少新增必填formalization。仅修复该fixture，fixture-green 1项通过，fixture-recheck.md增量审查无阻塞，再冻结最终源码运行gate-02。最终命令为 `uv run python scripts/run_final_gate.py --root . --output-dir artifacts/issue-178/gate-control/runs --run-id gate-02`。门禁后仅文档变更，不重跑产品检查。

## 未实证范围与所有权

一般自然语言对应 L3、实际明确机器要求的自然正向成功、复杂题质量或准确率提升未验证，不从本例外推。#183 继续按完整服务合同补齐必要能力，复用本票真实 L2 与只读恢复证据，不重复已有通过项。#168 保持开放。

本票 live01/02/03 及只读恢复服务均已结束；临时检查完成后删除，不交接留守代理。共享 Docker Desktop 保持运行，不停止其他项目容器。`tests/test.md` 保持未跟踪，未读取、修改、提交或删除。最终提交、远端核对及下一票入口见[接续交接](../engineering/unattended-ticket-handoff.md)。
