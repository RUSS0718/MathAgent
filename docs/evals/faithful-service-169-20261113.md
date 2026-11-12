# #169 普通输入基础闭环验收（2026-11-13）

范围为 #168 的 A1 首票 #169。集成起点 `1ca4fea64e72635b58b6720f32de3508be4d3527`，在当前工作区复用已有草稿；后续 #170–#183 和 F8 独立数学评测未由本票完成。

## 验收映射

| 合同 | 公共入口及可观察断言 | 证据 | 结果 |
| --- | --- | --- | --- |
| A1-1 | 可信配置、能力缺失原因、实验性标记、无 legacy 回落 | 配置/API 聚焦；8 项前端入口浏览器检查；真实普通提交 | pass |
| A1-2 | Job 创建冻结能力快照和输入版本，GET 由持久状态投影阶段/原因/动作及规格来源 | `test_faithful_service_job.py`；真实 `live-job.json` | pass |
| A1-3 | intake→Explore→final generation→whole review 共享同 Run 及根预算 | `live-job.json` 四份 Request Attempt 与 ContextPack，规格版本 1 | pass |
| A1-4 | 浏览器 Enter 提交“计算 2+3，给出最终答案。”，答案 5，经独立整题检查绑定 | `live-report.json`、`live-evidence.json`、`live-summary.json` | pass |
| A1-5 | 幂等提交复用 Job；刷新、GET 和报告读取不新增调用；预算/unknown 故障保持边界 | 公共 Job/API 聚焦与 intake 预算故障；真实刷新请求数不变、浏览器 errors=[] | pass |

证据目录为被忽略的 `artifacts/issue-168-work/`。本轮已运行前端 `npm run check`、8 项入口浏览器检查及快速门禁；后端最终聚焦 25 项通过，相关回归 5 项通过。完整冻结源码门禁及双轴审查结果在退出前补记，不由上述结果替代。

## 真实运行与失败保留

首轮 Run `run_417559829b68dedbf009fde7ba4ef092` 因配置组装非流式 adapter 与 `stream_first` 不匹配而失败，模型调用数为 0；旧就绪检查误报 ready。保留在 `live-01-failed/`，增加配置到公共 Job 的反例后改用 `InternStreamAdapter`，并在准入检查拒绝不支持的传输。

修复后 Run `run_2fa0391d0ebdf22aac27bf15dd833482`，Session `session_44937cbc096761daf8ce6fab908ee6bc`，四次真实 HTTP 均 200、`finish_reason=stop`、返回 `Intern-S2`。完整答案为 `5`，`whole_review=accepted`、`binding=same_artifact`、`formal_verification=not_verified`。用时约 12.1 秒，工具调用 0。模型 usage 缺失保持 null，账本本地估算收费 token 164386 不能当提供方实际用量；无 unresolved attempt。简单题无需规划，UI 的“计划尚未生成”如实保留。事件流仍较冗长，后续进度整合由 #170/#182 负责。

真实执行配置为 `service.json`，与 `examples/faithful-service.json` 同源：48 模型调用、48 HTTP attempts、8 工具调用、262144 token、1100 秒上限；上下文硬容量未知。Python 镜像为既有固定 sha256，Docker 启动后准入。普通提交不手填规格或技术模式，没有使用脚本 provider 或拦截 API 响应。浏览器驱动只输入题目、按 Enter 并读取公共响应。源码在真实运行时尚有本票未提交修改，最终提交和门禁身份另行记录，不能称为当时干净提交运行。

## 独立审查与修复

以 `1ca4fea` 和本票工作区差异为基点，Standards 与 Spec 由两个新上下文独立审查。Standards 发现预算终止原因丢失、允许动作遗漏恢复两项 P2；Spec 同时发现这两项，并补充公共恢复绕过 pending intake 的 P1。修复由第三个新上下文执行，复用既有恢复准入及根预算，不新建控制器。

`review-budget-red/green`、`review-intake-red/green2`、`review-actions-red/green` 保存公共 Job/API 反例及复验。后续 Spec 内存探针的历史观察见 `spec-probe.md`，退出码不能当通过断言。旧未知请求保持旧身份与预留，显式重试以新身份先补齐规格，成功后才派发 Explore。恢复动作预览采用只读准入检查，不保存重试决定。复查结论以 `standards-review.md`、`spec-review.md` 及最终门禁结果为准。

## 使用与后续边界

启动配置及命令见 [README](../../README.md#faithful-普通输入服务)；合同见 [入口合同](../engineering/faithful-service-entry-contract.md)。停止再以相同数据目录启动可读取既有结果。经验捕获、澄清消费、热切换、自然形式目标等后续票未完成；本票不宣称完整架构、数学正确率或效率提升。

下一 session 继续当前工作区和集成分支，先核验 GitHub 真实依赖再领取下一票，使用 `implement-spec`，不创建 worktree，不读取用户保留的 `tests/test.md`，继续使用当前选择的同一模型；当前具体 agent 型号无法可靠确认，不猜测。
