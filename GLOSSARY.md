# Glossary

- **Run**：一次隔离的研究任务执行，包含输入标识、配置快照、结果、独立验证状态、预算账本和脱敏轨迹。
- **ModelPort**：Runtime 调用模型的窄接口；Provider 差异由 `ricl_runtime/providers/` 中的适配器处理，不进入求解机制。
- **Request Attempt**：一次实际发往 Provider 的 HTTP 请求；请求失败、远端结果未知和有界修复分别保留其状态与账本记录。
- **独立验证**：不依赖模型自评的适用判据。验证状态与结果文本分开记录；没有适用判据时使用 `unknown`。
- **Evidence / Result ID**：可在运行轨迹中引用的证据及结果标识；存储存在本身不证明其已进入后续模型请求。
- **Verified Result**：通过适用独立检查的结果；其适用范围和依赖必须与内容一同记录。
- **Candidate**：同一 Run 中可被选择或淘汰的一份解题提案；不是已证定理。
- **CandidateRoute**：带有父子谱系和停止原因的求解方向；路线被选择不代表其答案已验证。
- **APRS**：依据验证证据及当前 Run 状态为固定候选排序的机制；排序证据不证明生成候选或提升数学正确率。
- **Population**：在同一 Run 和共享预算下串行扩展、评价并选择候选路线的过程。
- **Counterfactual Control**：从同一 Checkpoint 派生相互隔离的对照/处理分支；只有通过适用验证的反馈才可供父路线使用。
- **Checkpoint**：保存一次求解阶段及其可复核证据的状态快照；同源分支应明确关联共同 Checkpoint。
- **共享预算**：主求解、验证及已启用干预共同消耗的 Run 级请求、Token、工具、时间和费用限额。
- **配置快照与哈希**：复现 Run 所需的配置内容及其摘要；不包含凭证、完整 prompt 或私有推理。
- **Unknown Outcome**：请求已发出但响应结果无法证实。不得将其当作成功、自动重发或静默切换 Provider。
- **Known Protocol Failure**：Provider 已返回响应，但响应不符合 Runtime 所需协议；失败与已知用量按原请求记录。
- **BASELINE.json**：保留的官方历史基线清单。对应的官方可执行入口已从当前分支退役；此文件不代表 Runtime 的当前质量门禁。
- **legacy archive**：旧 Showcase、产品、比赛或 Provider 记录的文档和材料。当前索引明确标为归档；它们不代表当前代码仍可运行。
