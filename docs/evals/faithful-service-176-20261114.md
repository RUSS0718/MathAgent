# #176 串行自主干预与成果采用验收

日期：2026-11-14（Asia/Shanghai）。状态：实施中，尚未达到退出条件。父规格 #168 D1；[任务合同](../engineering/faithful-service-176-contract.md)及[接续合同](../engineering/unattended-ticket-loop.md)定义要求。起点 `64a8c98c72252c2d8501e147b231489a462b7106`；真实 GitHub 依赖仅 #170，已 closed；核验快照 `artifacts/issue-176/dependencies-before.json`。

## 现有证据

- 合同提交 `58f9255`；前端 `5f11096` 及空原因字段兼容 `6384a54`。新增只读干预状态和来源/采用记录，接入主工作台及持久报告；保留实验性和最终整题审查说明。
- 前端失败见证 `artifacts/issue-176/ui-red.log`：缺少干预组件。`node --experimental-strip-types --test tests/serial-intervention.test.ts tests/execution-switch.test.ts` 两项通过，`ui-green.log`；nullable reason 的最终聚焦检查一项通过，`ui-null-reason.log`。
- `npm run typecheck` 与 `npm run build` 通过，日志 `ui-typecheck.log`、`ui-build.log`；构建保留既有 chunk 大小提示。
- `npx playwright test tests/browser/serial-intervention.spec.ts --workers=1 --output ../../../artifacts/issue-176/ui-browser` 一项通过，覆盖 320/768/1024/1440 宽度和只读重开，零写请求、零浏览器错误。`ui-browser.log` 与对应截图；仅受控 public report 数据，不是自然模型自主触发证据。

## 真实验收准备

尚未启动真实模型运行。`artifacts/issue-176/live01/contract.json` 登记普通输入、独立答案和判据；核对正整数方程 `x²+y²+1=3xy` 的完整解及穷尽证明，期望答案不注入模型。复用原服务配置、48 调用/2400秒上界与固定 Python 镜像，凭证仅检查是否配置，不输出。源码、配置 hash、Run/Job/Attempt 与终态在实际运行后记录；已完成的 #175 旧运行不恢复、不重复派发。

## 待完成

后端集成、真实场景、Standards/Spec 双轴审查、冻结源码最终门禁及退出映射均待完成。`not_run` 不计通过；当前文件不声明数学能力提升、#176 完成或 #168 完整服务交付。
