# #176 串行自主干预与成果采用验收

日期：2026-11-14（Asia/Shanghai）。状态：实施中，尚未达到退出条件。父规格 #168 D1；[任务合同](../engineering/faithful-service-176-contract.md)及[接续合同](../engineering/unattended-ticket-loop.md)定义要求。起点 `64a8c98c72252c2d8501e147b231489a462b7106`；真实 GitHub 依赖仅 #170，已 closed；核验快照 `artifacts/issue-176/dependencies-before.json`。

## 现有证据

- 合同提交 `58f9255`；前端 `5f11096` 及空原因字段兼容 `6384a54`。新增只读干预状态和来源/采用记录，接入主工作台及持久报告；保留实验性和最终整题审查说明。
- 前端失败见证 `artifacts/issue-176/ui-red.log`：缺少干预组件。`node --experimental-strip-types --test tests/serial-intervention.test.ts tests/execution-switch.test.ts` 两项通过，`ui-green.log`；nullable reason 的最终聚焦检查一项通过，`ui-null-reason.log`。
- `npm run typecheck` 与 `npm run build` 通过，日志 `ui-typecheck.log`、`ui-build.log`；构建保留既有 chunk 大小提示。
- `npx playwright test tests/browser/serial-intervention.spec.ts --workers=1 --output ../../../artifacts/issue-176/ui-browser` 一项通过，覆盖 320/768/1024/1440 宽度和只读重开，零写请求、零浏览器错误。`ui-browser.log` 与对应截图；仅受控 public report 数据，不是自然模型自主触发证据。

## 真实验收

live01 使用源码 `803cc001783d096ab98590fa34387624558b7559`，配置 SHA256 `9170fa5f39e8262e2ea780a54478bdd14d10e4c6da6531381d3f9a055cf97364`；48 调用/2400秒上界和固定 Python 镜像沿用既有授权。普通浏览器输入正整数方程 `x²+y²+1=3xy` 的全部解及穷尽证明，期望答案不注入模型。Run/Job `run_bb98df2f10cbb06134a7c30bf929e9df` 失败，5 个物理 Attempt 的传输记录均为 success，但 Planner 逻辑调用记录为 timeout / `unknown_outcome`，不能据物理传输成功升级求解结果。未进入干预、未交付答案，unknown 不恢复或自动重发。

证据为 `artifacts/issue-176/live01/diagnosis.json`、`job-final.json`、`persisted-latest.json`、`report.json`、`interventions.json` 与 `job-reopened.json`；五个 Attempt 完整 ID 见 diagnosis。原观察脚本的 GBK 编码错误、重接时误用资源路径导致的 404/401 分别保存在 `observer-failure01.json` / `observer-failure02.json`；修复后只读接回原 Job，刷新前后 Attempt 身份不变，零写请求。可选 goal-cache GET 出现 SQLite 锁错误，不能称干净 UI 正向通过。观察进程最后为 PID23440，服务 PID24012；终态已停服务并删除 `MathAgent-Issue176-live01` 临时检查，见 `service-closure.json`。旧失败不覆盖。

live02 合同已准备但尚未派发：缩为四次实多项式的两参数恒非负条件题，目的是降低原题规划负担，检验有效串行步骤；使用新 Job，不重试旧 unknown。源码待身份修复集成后冻结。

## 初审及修复

`artifacts/issue-176/reviews/standards.md`：一项 P2 重复适用性检查的判断性建议，未确认硬性标准违规，11个 baseline 文件哈希匹配。`spec.md`：P1 实验身份缺少 Run 命名空间、P2 采用后父审查硬编码轮次导致身份冲突。已交由新的隔离实现代理修复；尚未复审，不作为通过。

## 待完成

后端集成、真实场景、Standards/Spec 双轴审查、冻结源码最终门禁及退出映射均待完成。`not_run` 不计通过；当前文件不声明数学能力提升、#176 完成或 #168 完整服务交付。
