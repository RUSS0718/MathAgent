# #188 用户答疑实施设计

2026-11-16；实施合同，父规格 [#188](https://github.com/RUSS0718/MathAgent/issues/188)。仅限 Showcase。

## 任务图与所有权

- #194：`workspace.py`、`presentation*.py`、新增规则及生成模块、对应 Python 测试；终态自动交付。
- #195：`flask_app.py`、`job_events.py`、新增授权与普通投影模块、对应 Python 测试；技术入口授权。
- #196：前端源码及浏览器测试；依赖前两票的最小 HTTP 合同检查通过后做集成。
- 集成后统一双轴审查、修复、冻结源码门禁与普通/审阅端到端检查。三票验收不替代父规格退出。

## 共享合同

沿用 Job 创建、幂等查找、状态、事件及控制 URL，普通身份的返回值按白名单投影；身份和 SSE 游标可供客户端恢复，但不显示在界面。技术报告、Evidence、原始事件、输出来源详情及系统/实验审阅入口需审阅授权。普通结果通过只读 `GET /api/agent/jobs/<job_id>/answer` 获取：`{job_id, status, mode, answer, presentation_status, notice}`，其中 `answer` 是唯一展示正文，`presentation_status` 为 `pending/ready/failed/legacy/stale/unavailable`。生成中不回传重复正文。`notice` 是简短用户可读边界说明。普通进度保留现有角色、阶段、计划与协作投影的最小结构；不传预算、用量、哈希或原始响应。前后端实现者在编码前通过共享笔记明确白名单字段。

审阅采用独立配置的随机密钥，在已认证且 CSRF 合格的 POST 中兑换服务端持久会话授权。密钥不得在 capabilities、页面、日志或仓库出现；无密钥配置默认拒绝审阅。普通 cookie 不自动取得权限；审阅页面和接口统一校验。现有本地用户归属检查继续生效。此机制仅为单机展示权限边界。

## 输出规则与成本

项目内版本化 solve/teach/report 规则作为受控输入。新任务冻结新策略和规则版本，旧 Run 不回填、不自动生成；旧结果可只读展示并说明历史格式。新终态由工作线程触发生成及持久保存，GET、刷新、视图切换不触发工作。按 Job、模式、规则和来源快照幂等占位，提交前校验来源；进程中断或未知远端结果保留失败/待复核，禁止自动重发。来源失效不冒认当前结果。

默认求解可直接采用已经生成的原答案并应用默认规则的保守边界，零额外调用。教学/报告使用一次有界表达调用（无工具、无求解重启、无自动重试），独立记录输出成本，不提高原 Run 预算。最大输出 4096 token、请求期限不超过 120 秒；使用现有模型适配器的超时/未知语义。离线 fake 使用显式标注的确定性生成接缝，只证明工程合同。缺少模型、容量不足、超时、协议无效或来源失效均保存失败并回退已有原答案；不得称为格式成功。生成身份、规则版本、来源指纹和成本保存在 PresentationArtifact，普通结果不暴露内部身份。改写数学段落保持未验证，不继承原答案文字审查等级。

## 验收

公开 Job/answer HTTP 与普通工作区浏览器为已确认接缝。各切片先保存稳定失败证据，再最小实现与聚焦回归。覆盖三模式、幂等、失败、部分结果、来源失效、刷新/历史无调用、普通/审阅正负权限、IME、键盘、题图、示例、角色筛选/计划/星图/回放、桌面/窄屏及 UTC 浏览器下北京时间。源码门禁按 development-gates.md。证据仅证明工程合同，不声称数学或教学效果提升。

## #194 输出细化

规则由 output_rules.py 版本化；每个新 Job（含省略 mode 的 solve）冻结规则正文、版本、SHA256、4096 输出 token、120 秒及一次 attempt。来源指纹包含冻结规则；_presentation_identity 在结果替换时保留它。solve 原文交付零新增调用；teach/report 复用现有 InternModelAdapter 及独立输出预算，客户端副本限制一次 attempt，不修改求解器客户端。上下文仅含脱敏原题、当前答案、范围及公开证据摘要，超过 64KiB 保存失败，不截断来源。

output_generations 在网络前持久占位，每个 Job 不自动重发；启动时 generating 转 unknown。生成不修改 Job status/updated_at，不新增来源事件；保存产物沿用来源 CAS，附加规则身份比较。来源变化保留 stale 回退。产物记录独立模型、角色、attempt、usage 和预算；数学表达无 claim refs，保持 not_verified。

#195 调用 presentation_api.get_final_answer(workspace_service,user_id,job_id,public_report=None)，注册只读 /answer。helper 使用 store Job + current_solver，避免读接口执行恢复对账；public_report 参数仅为兼容保留。pending 正文为空；ready 唯一正文；failed/stale/legacy 使用当前原答案。新规则任务的旧技术输出 POST/GET 也仅读取已保存自动产物；历史无规则任务保留旧显式技术接口。
