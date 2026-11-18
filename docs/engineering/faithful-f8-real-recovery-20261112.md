# F8 既有格式恢复与接续条款

日期：2026-11-12。状态：frozen；版本 `faithful-f8-real-v1.2`。补充 [v1.1](faithful-f8-real-continuation-20261111.md)，原合同与三份已派发首次记录不变。原因：B 首槽一次已知 invalid_json 后，产品已成功执行既有有界格式修复；实验协调器却因历史 protocol_failures 主动取消。该取消是观察规则过严，不能归为模型数学失败或产品格式恢复失败。

冻结审查：Spec（Russell）无阻塞；Standards（Fermat）要求明确格式修复标签不改变六态，已修正并经原审查者解除。此次只读评审核对 B 原封存记录，没有运行请求；冻结不代表新glue或实验已验收。

## 最小修正

协调器不因“存在历史 protocol_failures”取消仍在工作的 Job。已知格式失败必须有完整成功 HTTP/finish=stop、真实返回模型匹配；运行时继续按原次数、账本及 deadline 修复，协调器不新增请求、重试或格式改写。processing_failures 仍是本地工程错误，硬停止。HTTP未知、流截断、缺终态、工具未知、清理/隔离/来源/绑定/预算异常仍硬停止。

历史格式失败在结果中始终保留：Job 成功时仍为 `execution_status=completed`，另记 `completion_note=completed_with_protocol_repairs` 及失败调用/修复身份，不新增第七种执行状态、不抹除失败调用；Job 最终因已知模型 schema/规划/推理错误安全结束时，按完整终态归因记 failed，再接续未派发槽。不能只因 recovery=safe 就豁免；必须核验全部物理请求的已知完成、当前终止原因、模型身份、工具环境/回执和预算未耗尽。无法归因仍停止。自然题结果正确性仍由独立参考决定，格式修复成功不是数学通过。

被协调器取消的 B 首槽保留原 cancelled/failed 快照和策略故障归因，数学 unresolved，不重派该槽。A/D 原失败同样保留；接续只登记剩余67个未派发主槽，原98总分母、题集、配置、prompt、模型、工具、重复、原绝对deadline和预登记顺序不变。实际源码内容不变；新旧纯文档revision分别报告。此为实测后的协议修订，不称原v1或v1.1完整预注册执行。

## 验收

先用 B 的封存 Job 重放观察分类：包含 protocol_failed+已完成修复的安全在途状态不能触发取消；processing failure、真实unknown、模型漂移、工具未知和预算原因必须拒绝。再做既有公开准入/取消、已知模型失败分类和原67槽唯一性检查。原 runner/manifest不改；新glue、条款和manifest另存hash，经原双轴审查解除后派发。

其余退出条件沿用 v1/v1.1：所有必需主槽获得首次终态，F合格暂停点必须完成双臂，E支持域与G实际注入/解释评价分开，28槽辅助审查和完整性/来源链完成。真人L3不冒称已验收，官方重评分unavailable，usage缺失observe_only；仍有必需not_run或未处置硬停止时不关闭#157。
