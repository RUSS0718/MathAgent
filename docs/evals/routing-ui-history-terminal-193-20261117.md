# #193 默认历史恢复终态修复自测

日期：2026-11-17；基线 d21e9daeac0cc0d78033bfab422d01de959a99e2。

公共接缝为完整构建 SPA 的普通会话导航 → ChatWorkspace.initialize → 可见计划与显式回放。取消恢复历史任务时自动开启 replay；普通打开显示任务当前终态，显式历史滑块仍只投影所选事件。没有修改步骤证据或 ACCEPT/CHALLENGE/unknown 规则。

执行：在本工作树根运行 `node showcase/frontend/chat-frontend/tests/browser/history-terminal-193.cjs artifacts/issue193-history-terminal/<new-run>`；先在 frontend 目录运行 `npm.cmd run build`。node_modules junction 指向 root 现有目录。此脚本不使用 Playwright 项目配置或 webServer；全部请求 route.fulfill/abort，serviceWorkers block，没有 listener 或真实 API。

最终可执行测试对基线构建 red-02：4 个场景中 failed/canceled 失败，success/unknown 通过，exit 1；源码修复后 final/frozen：4/4 通过，exit 0。每个场景覆盖默认恢复、1440/320、刷新；failed 另覆盖显式历史回放与返回任务状态。滑块必须先 Home 再 End，避免当前位置已为末尾而未触发 input 的假阳性。初次 green 中此交互未触发的失败证据保留。

相关 terminal-plan-193、routing-193、causal-progress、presentation-mode 合计唯一 17 测试通过，0 fail/skip/cancel/todo；连同独立 DOM 的 4 个场景为 21 个唯一场景/测试，重复运行不重复计数。typecheck/build 通过；构建既有大 chunk 警告保留。git diff --check 通过。

证据：ignored artifacts/issue193-history-terminal/ 下 red-02.log、red-02/observations.json、regression.log、typecheck.log、final-build.log、frozen.log、frozen/observations.json、hashes.json。observations 保存实际 fulfill 资产字节 hash、请求、console/pageerror 和截图；HEAD 是构建时基线，workspaceSha256 与 hashes.json 标识实际含修复源码。精确最终提交/tree 在外部 handoff，避免自引用。

仅实现者自测，不是独立审查、自然数学能力或真实服务重启验收。主控另派独立浏览器；8120 被拒 Start 未重试或绕过。没有依赖安装、服务/provider、Python、预算/锁/official 或共享文档修改；root 用户 dirt 未操作。保留本工作树/junction/dist，未创建长测试或定时检查。

继续当前选择的同一模型，不指定型号；不能独立确认父子具体型号继承。
