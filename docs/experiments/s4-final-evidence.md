# S4 最终答案与验证 Evidence 合同

状态：实现检查点；权威规格为 GitHub #23 / #29。工程合同不构成数学效果证据。

## 身份与范围

最终公开文本先脱敏，再规范化 Unicode NFC 和 CRLF/CR 为 LF，UTF-8 SHA-256 构成 artifact 身份。空格、数学内容和 Markdown 改写都改变身份；不推断自然语言数学等价。身份只表明同一公开对象，不证明数学正确。

`verification.artifact` 是当前对象；`history[]` 保留每次检查的对象身份、checker、checker_version、Python 环境版本、scope、limitations 和稳定 check_id。`binding=artifact_changed` 时，历史检查仍保留，当前 status 降为 unknown、acceptance 为 needs_review。`same_artifact` 只允许沿用同一对象上的同一检查范围。

`polynomial_check` v1 仅支持候选代回、定义域与重复检查。candidate_status=pass 与 coverage_status=unknown 独立保留；即使文本身份相同也不接受完整最终答案证明。轻量结构检查的 pass 仅作为 history 中 shape_and_tool_consistency 范围的观察保留，最终 status 仍为 unknown、acceptance 为 needs_review；不证明数学正确性或完整解集。

## 追加与查询

`POST /api/agent/jobs/<id>/polynomial-check` 只对 terminal Job 追加；运行中返回 409 verification_requires_terminal_job，避免 worker 完成时覆盖追加历史。每次 POST 形成历史条目，内容相同的检查拥有相同 check_id，但保留独立的请求事件。

SQLite BEGIN IMMEDIATE 事务中读取最新 Job、追加 history、同步 Run、追加事件并提交；异常回滚。原答案、工具和历史 Evidence 保留。GET report/evidence 不执行 provider 请求，重复读取和进程重开保持历史一致。Live 在 synthesizer 之后按最终文本重新绑定；同步 Run 同样持久化绑定结果。

## 验收接缝与检查点

测试沿 Flask Workspace/Run/report/Evidence 公共合同，使用临时 SQLite、fake HTTP 与确定性 Tool Registry：

- test_final_evidence.py：合成改写失效、NFC/LF 身份、候选有效与完整性分离、不增加请求。
- test_evidence_history.py：并发追加、原答案与事件保留、Job/Run 一致、重开与幂等查询。
- test_sync_evidence.py：同步 Run 候选 scope、持久证据与事件状态一致。

不新增在线调用，不实现 R4/R5，不改官方 baseline。完整门禁结果由最终提交记录。
