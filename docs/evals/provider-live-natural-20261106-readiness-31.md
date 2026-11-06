# readiness-31：较简单数论题的交接与格式交付实验

归档：2026-11-06用户要求暂停线上实验、整理仓库并集成PR #129。北京时间14:56:35终止，simple成功，自然题计划6步、前5步已审查（2 ACCEPTED、3 REVIEWED），第6步Verifier流中connectivity异常，unknown_outcome；不是1200秒截止或已确认输入超限。末次调用14:53:44.921派发、首正文14:53:52.754、末正文14:56:34.312、末活动14:56:34.923，200事件/2033正文bytes，无finish/completion。连接异常细分原因未确认。

自然题17模型/HTTP、2工具，local charged1046223/67108864、1265.61/28800秒，预算充足；1个未决请求、未知工具0，usage UNKNOWN。最终生成/整题审查/同文本绑定NOT_RUN，失败说明不是最终答案。零模型独立严格task/coverage/process_path FAIL、transport PASS、usage UNKNOWN；工程分母2：simple PASS、自然题UNKNOWN，批次FAIL。保留旧Run，不恢复/重发。#127保持open，#128两臂NOT_RUN；没有数学能力提升结论。服务身份核对后停止，provider-live监控按用户归档要求删除，其他窗口任务未改。详证在ignored artifacts本批terminal-diagnosis.json及两份independent报告。

用户在readiness30单调用截止后明确授权换一道更简单的题，观察自然多角色交付；本批不受此前“仅同因上下文超限才换题”的条件限制。只换样本，不改产品源码、框架、压缩或记忆系统。不能承诺触发所有角色；若FASTPATH则如实报告未覆盖，不强迫planner、Meta或工具。

## 预登记

完整分母2：原simple控制题与pell-bounded数论题。新题为本轮自拟工程样本，无竞赛来源或外部难度评级；要求枚举正整数Pell方程x²−2y²=1在x≤10⁶内的全部解、证明完整性、标记y可被5整除者，简洁推导并给出有限列表。原八边形题涉及D8×S3作用和逐类不动点，本题只有一个二次方程、标准递推和有限范围，预期更简单；这是事前结构判断，不是实测等难或能力结论。原题失败证据保留，两批分别报告，不拼接结果或分母。

冻结Run：issue127-natural-20261106-readiness-31-run01，端口8146。revision 0eba346d5227babf86b662922e553cb102e2fb81；source SHA 8b8056345174cb7b628e936d49da535d29ae787bda6f9fca388b7d82c9e42163；manifest SHA 8a9f7bba1ca2ecd09c1ce2ac76910608e46c048b6ec2a13273fccd692a20e1fa。原样本文件未改，新样本按FileSampleHashResolver实际字节冻结并read_text预检，不按内存换行计算哈希。

配置保持intern-s2/thinking=false/temp0.2/output32768/stream_first；每题512模型HTTP、128工具、67108864本地token预留、28800秒，批次双倍；单调用1200秒、连续30秒无流停止。上次停止为单调用截止，总预算仍充足，因此本批先保持时限以区分样本影响，不盲加总预算。best-effort=false，官方baseline、身份、工具隔离、审查、同文本绑定保留，usage UNKNOWN只观察。显式handoff-v1工程合同不替代旧#127验收，#128两臂NOT_RUN。

启动前确认旧30本地Job均终态、runner退出；旧unknown远端结果不推断已知，不恢复或重发旧请求。新批独立身份、独立服务数据目录，只派发一次。此批若失败先诊断报告，不自动循环换题。

## 监控和终态验证

北京时间14:35:09启动，真实服务PID10504/创建06:34:38.705189Z，真实runner PID14468/创建06:35:09.852470Z，均经CIM核对；启动包装进程不是运行身份。初始simple 3调用完成整题审查并成功，实际limits匹配manifest；Pell自然进入PLAN，未强迫路线。实际capabilities模型与传输、服务源码/data目录已核对。live_attempt=22，repair_round=13不变。

只读独立代理Zeno复核旧30：33次调用包括explore1/planner1/reasoner15/step_verifier15/researcher1。拆账为探索规划2、12步首次推理12、11步首次验证11、协议修复6（4次invalid_json、2次invalid_role_schema，修复均completed）、工具结果额外续接1、反例检查1。没有无限重试证据。plan14步把不同旋转/反射类型分别推导和复核，粒度偏细且格式修复增加成本，但不能仅凭耗时归咎已证实循环bug。旧step11耗时约42分55秒包括推理/核验/核验修复，不能等同单次调用耗时。旧Run前11步实际为6 ACCEPTED/5 REVIEWED，不能将steps字典长度在任意时刻都称审查完成。

唯一provider-live每10分钟监控转至本批，真实PID/创建时间见ignored artifacts本批process.json及service-startup.json，仍须CIM核对。手动命令：`powershell -NoProfile -File .review/issue127-natural-20261106-readiness-31/monitor.ps1`。终态依次运行verify_terminal.py和verify_handoff.py，均零模型派发；检查实际配置、调用与工具、角色触发/未触发、最终生成、整题审查及同文本绑定，按完整分母2报告。旧Issue未满足仍open。
