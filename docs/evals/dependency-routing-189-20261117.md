# #189 目标依赖分流阶段验收

2026-11-17，Asia/Shanghai。状态：190开发纵切已退出；191/192代码与审查修复已集成，受影响两轴复查零阻断；自然验收、193与整体门禁未完成。能力与效率不作外推。

## 源码与边界

集成分支 `dependency-routing-189`，起点为188交付 `1307aab40b8788cc408ef65fc94dfc7f2b1dc1f8`，PR198堆叠于 `user-solving-188`。不合入main，不改官方baseline、默认路径、依赖或根预算。

190交付975560a；191由fresh merger集成147f8ea，生产仅Intake指令7行；192集成5582e86，生产/测试最终快照b2b1a50。各份检查仍绑定其实际源码，不能把较早回归称为最终源码全组运行。纯文档更新另记交付SHA。

## 合同到公共证据

| 要求 | 公共入口与断言 | 证据 | 当前结果 |
| --- | --- | --- | --- |
| 依赖目标先规划，SOLVED不能短路 | Job/Run/当前Spec；Planner、依赖WorkUnits、Reasoner/Verifier实际派发；未验证材料不进已证账本 | 190最终45项、集成快速5项；[190记录](../engineering/dependency-routing-190-handoff.md) | 受控pass，190已关闭 |
| 自然Intake依赖及Verifier实际作用 | 自然message→Spec→Plan→步骤反馈→最终答复，不能注入Spec/Plan | 191公共12项、角色14项、Intake9项，共35个不同方法、零skip；受控CHALLENGE后重做和后继门控 | 受控pass；自然not_run，191开放 |
| 无依赖简单题有界直解 | 首次2048后独立整题审查，实际payload/Attempt/预算相符，其他角色基础cap不变 | 192最终21项；[192记录](../engineering/initial-explore-192-handoff.md) | 受控pass；自然not_run |
| 未完成/已知截断转规划，unknown不自动派发 | Job及HTTP计数、公开原因、未验证来源；工具/有限修复同语义轮次 | 192最终21项及归档红绿；reviewfix工具续接完整payload/指纹和公开跨进程恢复 | 受控pass；自然not_run |
| 具体数学异议一次修正及后续规划 | 同Run审查反馈、原容量与来源，二次拒绝/无具体异议沿既有规划 | 190/191公共组与192修正用例 | 受控pass，不称自然稳定性 |
| 原预算/截止/旧Run及默认路径 | 新策略仅新Run冻结；旧无策略/190-only/新容量恢复，GET零新增调用 | 190恢复组、192配置/transport/ledger；reviewfix跨进程三场景、集成fast5/5 | 受控pass |
| 普通用户真实路径与权限 | 普通投影/SSE/角色生命周期/唯一answer；ID、用量、hash不进普通DOM | 193仅只读设计 | not_run，193开放 |
| 数学、测量、阶段退出 | 登记题逐角色duration/HTTP计数、来源/反馈/答案与独立人审；双轴及冻结最终门禁 | 下述自然登记与后续记录 | not_run，189开放 |

192回归A为27项、B为47项且1项skip，均在7a87eb2；最终资源切片8项含7个重复方法。最终21项加A/B共95个不同选择器，不将重复检查累加。未验证本地Docker Reference镜像的skip保持未执行；配置准入通过不替代它。191/192 ignored证据分别20/68文件已复制root并核对哈希一致。

## 独立审查与准入

固定比较1307aab…5582e86的规范轴0硬规范/0smell/0阻断；规格轴提出工具续接完整payload/serialized/fingerprint和公开跨进程恢复两项证据限制。唯一fresh实现者补证时复现并修复显式非流指纹漏tools、工具续接协议失败恢复后额外repair两处缺陷，51个不同测试通过、零失败/错误/跳过；生产与测试源码1037ec9，集成0b92236。详见[补证记录](dependency-routing-review-20261117.md)，40份ignored证据已复制root并逐文件校验一致。

两位fresh审阅者对5582e86…0b92236的受影响差异独立复查，规范轴0硬规范/0smell/0阻断，规格轴0已确认缺陷/0阻断，两项受控证据限制解除。原报告及复查报告均保留在仓库外 `C:/Users/CQX/.codex/tmp/189-backend-{review,rereview}-{standards,spec}-20261117.md`；后者已复制到ignored `artifacts/issue189/reviewfix/independent-review/`。自然及193不在此次结论范围。

0b92236上主控复核快速检查5/5、3.097秒、fast_check=PASS，日志及执行源码见 `artifacts/issue189/backend-preflight-reviewfix.json`。先前快速检查的工具返回在交接中未保留结果，因此本次仅重新执行快速入口，不重复51项或最终全仓门禁。

集成快速检查5/5、3.344秒、`fast_check=PASS`；可信JSON新策略经实际loader准入通过，摘要 `artifacts/issue189/backend-preflight.json`。独立临时库、worker关闭且禁止socket出站的运行时检查为ready=true，star_reference enabled、missing_capabilities为空，见 `artifacts/issue189/runtime-preflight-01.json`。没有创建题目或发送provider请求，不称线上能力验收。

## 自然验收登记与时序

S/D预登记于 `artifacts/issue189/preregistration/natural-cases-v1.json`，U另登记 `natural-U-v1.json`，均 `registered_not_run`。运行器只有message可进入公开Job；参考解、观察预期及判断条件不进入任何角色或验证器。D未形成实际依赖，或U自然形成依赖/首次直接完成，按相应路径记not_triggered，不注入Spec/Plan或诱导重跑。

先完成191/192补证和审阅，再冻结同一源码/配置唯一执行S/D/U，每题一次。unknown及提交身份不明不自动重发；失败与原记录保留。193随后使用持久结果做普通UI及只读刷新验收，分别记录自然运行和UI的适用源码SHA，不为界面重复调用模型。

`artifacts/issue189/live01/` 运行器已完成两轮离线公共Flask/Job受控smoke：第二轮0真实provider、3受控Attempt、分页30页、读取新增0次，公共Run保持产品原响应；第一轮保留。配置审计为独立启动快照，不混入Run原生字段。自然服务尚未启动，端口8119和独立data待主控冻结；用户8103不动。长期运行遵循[工程门禁](../engineering/development-gates.md)和现有30分钟检查合同，不用子代理轮询。

## 尚未退出

自然题数学与逐角色测量、191/192真实AC、193普通投影/浏览器与恢复、整体双轴和冻结最终门禁均待完成。2048是工程假设，usage缺失不捏造token测量；没有耗时基线，不声称更快。188门禁只适用于188源码，不能代替本阶段。192工作树清理因自动审批拒绝删除自建ignored `.venv`（`blocked by policy`）暂保留。
