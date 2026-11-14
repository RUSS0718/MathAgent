# #181 答案表达与证据深链验收

日期：2026-11-15（Asia/Shanghai）。起点 `d1ece939131dfd7f1df31f1f6554660c7cbb7d6d`，范围为 #168/G1；[合同](../engineering/faithful-service-181-contract.md)。本票未新增模型讲解、求解或验证能力。

## 公共验收映射

| 合同 | 公共入口与断言 | 证据（artifacts/issue-181/） | 状态 |
| --- | --- | --- | --- |
| G1-1 | 普通 Faithful Job 显式 POST teach/report，来源指纹与独立 output/artifact 身份，保存复用 F6 竞争校验 | focused.json、teach.json、report.json | pass |
| G1-2 | 模板整理标实验性；文字审查与形式化范围不混淆，缺失用量保持未知；来源规格1/图1/状态302 | 同版本产物、read-final.json、workspace-final.png | pass |
| G1-3 | GET 恢复、切视图、刷新不生成；表达失败保留答案；跨用户/错误身份不可借用 | backend-final.json、f7-green.json、frontend-green.log、live-summary.json | pass |
| G1-4 | #169 真实答案5显式表达、固定输出/段落链接、重开、刷新和错误身份 unavailable | live-browser.mjs、live-summary.json、deep-link.png | pass |

## 真实来源与限制

复用 #169 的真实 Run `run_2fa0391d0ebdf22aac27bf15dd833482`，Session `session_44937cbc096761daf8ce6fab908ee6bc`，原始记录位于 `artifacts/issue-168-work/`。在本票当前源码启动同一数据库，由 Chromium 普通界面点击生成两种表达；仅两次表达 POST，未重新提交数学题。读取前后答案5、四份 Request Attempt 及整个预算相同，浏览器 errors=[]。原 Provider usage 缺失，不能以本地 token 计费估算代替。

teach 输出 `output:45eb9480dc9cb614ec6522fffe337bbd5ae30f55cf4d9fea8df44219a055aaef`；report 输出 `output:e5f453cd09005c5817675f9d7a7dd434365233d385363f33a81b05dee4331f04`。精确 artifact SHA、来源版本和固定链接见 live-summary.json。原整题文字审查为 REVIEWED，形式化未验证，历史根义务0/1原样显示，不因表达改变历史判定。真实数学生成来源为 #169；本票的表达是确定性模板，无新模型调用，不代表独立教学质量或数学收益。

## 失败与验证边界

red.json 是测试夹具补丁过早退出导致的运行失败，修正后 red-02.json 稳定见证缺失只读输出端点。green.json 的答案字符串预期错误已改为与原答案逐字比对；这些失败均保留，不追改。后端 focused.json 为26项通过，backend-final.json 为普通任务公共输出和失败回退复验；F7选择器最初误填8项而拒绝执行，f7-green.json 才是12项实际通过。前端 red/green 保留受控浏览器反例与复验，不作为真实 provider 证据。

Standards 无阻塞。Spec 发现原报告被表达区域遮住、Provider 用量仅有泛泛说明两项 P2，已分别保留完整原报告并逐项投影 provider_known；spec-recheck.md 确认解除。最终真实只读 UI 复验 read-final.json 确认原报告可见、三个 Provider 字段为未知、四次原请求、零写请求及零脚本错误。受控前端4项通过、聚焦前端24项通过、typecheck通过；旧S06用例适配及最终冻结门禁结果待退出时补记。

未执行项目不计通过；复杂路线、澄清与形式化新版本归 #182，#168 和最终服务 #183 保持开放。
