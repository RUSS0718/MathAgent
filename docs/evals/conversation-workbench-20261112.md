# 对话式工作台集成验收（2026-11-12）

## 源码与交付范围

主工作树：`D:\project\工程化MathAgent\Challenge-Cup-2026`。
分支：`feat/conversation-workbench`。起点：`822069d031859bed9af834755b69aa26dbf7a55`。
该起点包含原主目录 `290da4a` 之后 `mathagent-faithful` 的 18 个提交。
本次 OpenDesign 原型是非 Git 输入，按源码迁移，未执行 cherry-pick。
正式主页由 Vue 对话式工作台取代，旧 MessageList 与 Inspector 不再作为主页渲染。
运行详情、会话、报告、输出模式与已有任务控制继续复用。

验收要求见 [集成合同](../engineering/conversation-workbench-contract.md)。
本记录证明工程合同；真实 provider 联调及数学正确性评测均为 `not_run`。

## 接口与状态变化

复用认证、CSRF、创建 Job、详情、SSE、取消、恢复和报告接口，没有另建任务协议。
外层 SSE 类型与 `solver_event_type` 保持分离。
可选 `workbench` 字段采用 `workbench-v1`，含稳定线程与消息 ID、角色、计划版本、
尝试编号、步骤标签、消息分类、分类摘要、线程状态、裁决枚举及已知回退范围。
`content_status=not_published` 明确表示详细正文未获公开。
终局 `evidence_chain` 只关联 `ACCEPT` 且 `valid=true` 的步骤标签。
`evidence_kind` 提供运行来源事实。前端同步校验以上字段，并兼容最小 interrupt 载荷。

共享投影驱动事件、计划与两种星图。计划使用完整快照，并防止旧详情覆盖较新 SSE。
重连按持久事件 ID 去重，终局后继续消费尾事件至 EOF，动画按稳定消息 ID 去重。
最终答案由持久任务报告读取，不用 `final_result` 的运行摘要代替。
fake、受控数据、历史回放、实时运行及未知来源分别显示。

## 修改文件

| 范围 | 文件（相对仓库根目录） |
| --- | --- |
| 后端公开投影 | `showcase/workbench_projection.py`、`showcase/star_product_events.py`、`showcase/star_product_pipeline.py` |
| Vue 页面与组件 | 前端 `src/components/ChatWorkspace.vue`、`ConversationWorkbench.vue`、`AgentConstellation.vue`、`ComposerBar.vue`、`StarModeSelector.vue` |
| 事件与状态 | 前端 `src/runtime/jobs/workbench.ts`、`sse-transport.ts`、`job-controller.ts`、`star-event-presentation.ts`，`src/stores/jobs.store.ts` |
| schema 与主题 | 前端 `src/api/workbench.schemas.ts`、`events.schemas.ts`、`src/styles/tokens.css`、`src/main.ts` |
| 后端测试 | `tests/test_conversation_workbench.py` |
| 前端测试 | 前端 `tests/workbench.test.ts`、`sse-runtime.contract.test.ts`，浏览器 `conversation-workbench.spec.ts`、`fixtures.ts`、`interactions.spec.ts`、`states.spec.ts`、`visual.spec.ts`、`star-decisions.spec.ts` |
| 截图与文档 | 浏览器 `snapshots/win32` 更新 10 张，删除旧 observer 截图；`docs/README.md`、集成合同和本记录 |

表中“前端”根目录为 `showcase/frontend/chat-frontend`，“浏览器”为该目录的 `tests/browser`。
完整提交路径清单保存在 `artifacts/workbench-validation/commit-paths.json`。

## 合同验收映射

| 合同 | 公共入口 | 断言 | 测试及证据 | 结果 |
| --- | --- | --- | --- | --- |
| C1 | SSE transport、JobController | 终局尾事件不丢失，跨连接保持终态，重复 ID 不重复插入 | `tests/sse-runtime.contract.test.ts`、浏览器工作台用例 | pass |
| C2 | 默认主页、共享投影 | 时间顺序、快照、角色与步骤筛选、大小星图、回放共用事件；切视图不建任务 | `tests/workbench.test.ts`、`tests/browser/conversation-workbench.spec.ts` | pass |
| C3 | 任务来源投影 | fake 与 scripted 不标为 live，明确 replay 与未知来源 | 投影单测、实际 HTTP fake JSON | pass |
| C4 | 创建 Job、详情和报告 | 真实输入与 CSRF 提交；只建一个任务；报告答案独立于终局摘要 | 后端公共 Job 测试、浏览器提交用例、实际 HTTP 脚本 | pass（受控求解） |
| C5 | `solver_progress.workbench` | 同线程关联稳定，不发布模型回复、内部 step ID 或隐藏参数 | `tests/test_conversation_workbench.py`、schema 与浏览器用例 | pass（分类载荷） |
| C6 | 回退公开投影 | 只报告已撤销的步骤状态，不生成未来 add 或重算结果 | `test_rollback_reports_only_known_changes` | pass |
| C7 | waiting_input、恢复控制 | 无文本采纳承诺；恢复执行与追加约束明确区分 | UI 提示及恢复交互用例，断言仅发送空 answer | pass |

## 检查与证据

- `uv run ruff check`：修改的 Python 文件通过。
- `uv run python scripts/check_fast.py`：通过，含 baseline 字节与官方边界。
- `uv run python scripts/run_unittest_report.py --expect-count 5 tests.test_conversation_workbench`：5 项通过。
- 前端目录 `npm run check`：依赖合同、类型、57 项单测和生产构建全部通过。
- `npm run test:browser -- tests/browser/conversation-workbench.spec.ts tests/browser/star-decisions.spec.ts`：10 项通过。
- 320、768、1024、1440 四种宽度验证无横向溢出、视图与筛选、线程顺序、主题及回放清空连线。
- 实际 HTTP：`artifacts/workbench-validation/real-http-test.cjs`，Flask fake 服务无 API mock；一次创建、3 个事件、报告结果可读取。输出 `real-http-fake.json` 和 `real-http-fake.png`。
- 最终门禁：`workbench-20261112-02`，6/6 阶段通过，`source_changed=false`。
  命令为 `uv run python scripts/run_final_gate.py --root . --output-dir artifacts/final-gates --run-id workbench-20261112-02`。
  完整 Python 测试 1932 项，0 failure、0 error、49 skip、0 expected failure。
  跳过项的具体环境条件保留在该目录 `repository-check/diagnostics.log`。
  mutation probes、发布检查、前端安装、审计与检查通过；npm audit 为 0 vulnerabilities。
  前后源码 hash 均为 `21d4a350e63b794ed436a1f5fd3f3dcdb0e0f11b3048653d439b71e9f017e57c`。
  源指纹和命令日志保存在同目录，最终提交 SHA 与推送、归档结果另记于
  `artifacts/workbench-validation/delivery.json`。门禁后仅补充本验收记录，未修改产品源码。
- 旧主页相关浏览器回归：以下命令在前端目录运行，53 项通过，未使用更新截图选项：
  `npm run test:browser -- tests/browser/actions.spec.ts tests/browser/states.spec.ts tests/browser/interactions.spec.ts tests/browser/visual.spec.ts tests/browser/conversation-workbench.spec.ts tests/browser/star-decisions.spec.ts`。
  该组验证新主页和已迁移的 10 张截图，移除主页不再使用的旧观察抽屉截图。
  其他依赖独立 provider 服务的专项浏览器套件本轮未运行。

首轮 `workbench-20261112-01` 保留失败：1912 项，1 failure、1 error、49 skip。
failure 来自索引提前引用尚未落盘的本记录；error 来自 Docker daemon 未启动。
本记录落盘并启动 Docker 后，两个受影响测试分别隔离复跑通过。
首轮源码 hash 为 `4572bc0aba24e2b34f8bd91131195013365632eb19c8f987acc7b7fe8a49c467`，
其 `source_changed=false`，不将首轮失败计作最终通过。

截图位于 `artifacts/workbench-full-page.png` 和 `artifacts/workbench-{320,768,1024,1440}.png`。
以上运行产物保留本地，不进入版本提交。

双轴独立审查分别核对规范与需求。已修复终态跨连接丢失、Meta CONTINUE 原线程关联、
线程分组打乱时间顺序及回放读取未来连线四类问题，复查无剩余阻塞项。
浏览器补充交错线程顺序和“已有两条连线后回放归零”的断言。
审查摘要保存在 `artifacts/workbench-validation/review-record.md`。
早期 STAR 浏览器失败来自 fixture 缺少可选 API 与预期的 404，补齐合同后 5 项通过。
扩大截图检查时还发现 fixture 的 report.evidence_id 未匹配 Job ID，已修正为真实接口的绑定关系。
只忽略 fixture 明确返回的可选 memory、goal-cache 和 interventions API 404，其他 console 错误仍失败。
旧主页截图在替换后出现预期差异；原失败证据保留在
`artifacts/workbench-validation/initial-browser-red/`，更新后另行复验。

## 未完成与配合事项

- `provider-live` 联调、自然题数学正确性及能力提升评测：`not_run`。
- 计划数学标题与正文仍需公开摘要协议。既有隐私合同禁止直接暴露 `plan.objective` 和模型报告。
- 回复正文、Meta 的可公开依据、数学逐行差异尚未接入。目前只展示真实分类事实与撤销范围。
- 任意文本插话未传入求解器，不提供“已生效”回执。恢复执行发送空 answer，仅控制既有任务。
- 后续前后端应共同确认公开摘要白名单、插话接收和生效时点，再扩展 schema 与公共合同测试。
- 证据步骤标签不构成形式化证明。节点亮起只表示已有公开事件到达，不推断智能体正在运行。
- 生产构建保留现有大 chunk 提示，未因此增加拆包重构。

## 工作树归档

用户明确选择旧未提交实验与 UI 草稿保留到可恢复归档，不进入产品。
归档计划包含 18 个现存附属目录及 11 个已不存在的失效注册。
C 盘归档：`C:\Users\CQX\Documents\Codex\archives\mathagent-worktrees-20261112`。
D 盘归档：`D:\project\MathAgent-worktree-archive\20261112`。
同卷整体移动保留未跟踪与忽略文件，并保存已验证 bundle、原 HEAD、分支、补丁、
Git 工作树元数据和恢复说明。主目录与原型输入目录保持原位。
实际移动结果以两个归档目录的 `manifest.json` 为准；恢复入口为 D 盘归档的 `RESTORE.md`。
归档同时保存本次输入原型的 10 个交付文件和两轮门禁证据。
临时长测试计划任务和监控脚本已在门禁完成后移除，测试 HTTP 服务已停止。
本次未读取或改动用户保留的 `tests/test.md`。
交接继续使用当前选择的同一模型；本记录无法核实具体型号。
