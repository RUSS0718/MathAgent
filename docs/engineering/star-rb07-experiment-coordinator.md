# RB07：固定实验协调器

对应 spec #87 的 ROB-AC-19–24。实现入口为 `showcase.star_experiment.ExperimentCoordinator`，由受信任的本地操作程序调用；不向普通 HTTP 用户开放核心 feature 或预算配置。

## 题目与数学复核

仓库只保留注册结构和固定预算协议，不携带真实题文、具体答案或解法。操作者在工作树外保存冻结 JSON，通过 `registration(manifest_or_path, expected_sha256=...)` 显式加载；hash 使用 `digest` 的 canonical JSON SHA256。入口核对版本、题文 hash、非空唯一义务、十个固定位置、预算和条件。E1 两题各非流式/流式，E2 三类按固定顺序重复两次；每个位置创建独立会话与 Job。

外部 `independent_oracles` 按题目 ID 保存精确有理数或 null，仅用于独立评分与归档。独立参考材料可由本地复核者持有；solver 只接收注册的 `prompt`。数学检查仅支持受限的最终整数/有理数（含 LaTeX frac/dfrac）表示，不支持的表达记 undecided；数值相符不能代替解释义务。

复核函数接收题目和公共产物，返回 `reviewer`、`reason`、`question_sha256`、`answer_sha256`、逐义务 `pass/reject/undecided`。解释正文中的结论可由复核者另给 `conclusion_span={"start": start, "end": end}`，使用 Python 字符索引、end 不含；评分只解析该答案真实子串，支持常见数学/Markdown 外层标记。没有 span 且全文或显式最终结论无法解析时记 undecided；可解析的显式最终结论不能被中间数值 span 替代。结论定位依赖复核者诚实指出实际结论，不能由 hash 证明其判断正确。缺少复核、错 hash 或未决义务不能通过。复核人身份是操作者声明，不能从字符串证明其独立性；RB08 须记录实际复核者与论证。模型自身整题 ACCEPT 不替代独立复核。

## 入口与门禁

先用 `star_experiment_gates.qualify(saved_batch, original_runner_version=..., evidence_kind=..., manifest=..., manifest_sha256=...)` 执行只读 E0 重判。live 资格还要求固定历史样本、实际证明绑定、RB06 完整公共故障/真实 Docker/进程矩阵与五项旁路，无 skip/xfail，再运行来源回归。scripted 资格仅运行聚焦公共回归，不能授权 live。

资格同时绑定注册 manifest 身份、Git SHA 和 Python/依赖源码 hash，派发前再次核对；修改源码使资格失效。`ExperimentCoordinator(path, adapters={"nonstream": ..., "stream": ...}, qualification=..., manifest=..., manifest_sha256=..., evidence_kind="scripted").run(reviewer)` 只创建一轮。scripted 模式强制提供方 URL 为 loopback，测试使用真实 HTTP 但模型回复为受控数据。live 模式留 RB08 按门禁显式调用。

两个服务实例分别使用 `InternModelAdapter` 与 `InternStreamAdapter`，条件固定为 Intern S2、180s、8192 输出、retry=3、thinking=true、temperature=0.2。协调器使用认证/CSRF 公共 Job、Run、报告、Evidence；完整模式真实隔离预检有独立 S3 账本及可核验回执。

## 预算与停止

| 范围 | logical / HTTP / 题目工具 | tokens | 秒 |
| --- | --- | --- | --- |
| E1 每 Run | 6 / 8 / 1 | 32768 | 300 |
| E2 每 Run | 12 / 16 / 3 | 65536 | 600 |
| 全轮 | 96 / 128 / 22 | 524288 | 4800 |

最多十 Run、两个服务启动探针与十个 Job 探针；环境工具加题目工具最多34次。墙钟从服务启动前开始，含预检、等待和退避。协调器按下一 Run 完整额度检查剩余空间，S3 执行实际逐动作准入。`charged_tokens` 已包括未知预留，不能再加一次。已知 tokens、估算、预留分别导出，费用始终 null。

每 Run 在 Job 预检前固定自己的绝对截止，与整轮原截止取较小值；题目和环境预检各自的 S3 都遵守该上界。注册的300/600秒限额保持原值，恢复不覆盖既有 deadline。E1 每个 Run 还须同时满足三调用、已知8192 tokens、包含 Job 预检的120秒交付时间、无额外工具、答案/解释/审查/同文本绑定。独立复核等待同样受整轮原截止与取消约束。

首 unknown、产品/协议/配置缺陷、取消、硬限或 E1 失败停止后续派发。E2 数学 REJECT 如实记未解，整阶段按每类至少一次完整独立通过判断；自然快通道可计正确性，不能计自然非快通道。Challenge/Traceback/Replan 的 live 覆盖默认 `not_covered`。

## 归档与证据范围

目标目录必须不存在。注册、独立真值、资格、派发意图、Job 身份、公共产物、评分和停止清单采用独占创建，终态生成 SHA256 清单。停止或进程退出后拒绝复用该目录；不自动续跑、换题、扩预算或新建轮次。运行 SQLite/真实工具产物保留在受控目录；公开提交只包含代码和脱敏说明。隐藏推理、完整角色 prompt 和凭证不进入提交。

`tests.test_star_experiment` 验证真实 loopback HTTP、真实控制器/SQLite/S3/S4 与 Docker。scripted 题目答案及人工复核夹具只证明协调与故障行为；真实模型数学能力、自然罕见分支、最终全量/前端/浏览器及发布验收属于 RB08。


同 Run 来源资格从服务端只读 snapshot 与实际出站上下文调用 RB01 `evaluate_delivery`，只归档脱敏摘要，HTTP 不开放原始上下文。自然非快通道还须独立数学通过。

关闭后迟到用量通过短生命周期连接更新同一 S3 原 attempt；禁止新动作。`supplemental-usage/` 以独占文件追加身份、用量和观察时间，独立于终态 hash 清单；原始结果与 unknown 停止理由保持不变。该补记不代表恢复实验或接受迟到文本。
