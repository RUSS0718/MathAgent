# S02 上下文与容量治理工程退出验收

日期：2026-11-08（Asia/Shanghai）。集成分支：`mathagent-faithful`。状态：工程退出通过（`engineering-preview`）。完整门禁冻结源码 SHA：`d19aa56f35e0d0e3d6ccaaa53d7d56e57d06101a`；文档交接提交 SHA 另见最终 Git 状态，不混作门禁源码 SHA。

## 源码与合同

开工 HEAD 为 `fa314fe3ff54bd1ecdd20e692337d028d7b7e901`，工作树干净；未回退交接源码。实现提交 `5f6e581`、公共 Job 验收 `efaf297`、终审修补 `29f0e73`；冻结源码为 `d19aa56f35e0d0e3d6ccaaa53d7d56e57d06101a`。本记录承接 [S02 完整退出合同](../engineering/faithful-s02-exit-contract.md)，依据 #136、#144 和 #146，不把 S01 旧 SHA 的门禁结果当作本版本证据。

修改集中于 Showcase 的 ContextPack、会话历史治理、Run 策略冻结、调用审计、最终序列化准入及 report/Evidence 白名单。共享 `llm_client.py` 只增加显式可选的最终 bytes 回调，未启用时保持原请求内容和预算。`user_agent.py`、`implementations/`、`BASELINE.json` 及官方冻结文件无差异；用户保留的 `tests/test.md` 未读取、修改、提交或删除。

## 容量依据与输出边界

服务端通过 `SHOWCASE_STAR_FEATURES` 的 `context_pack` 和 `SHOWCASE_STAR_CONTEXT_CAPACITY` 显式启用；默认关闭，full core 不自动启用。新 Run 保存完整策略和策略 hash，恢复读取原策略；旧 Run 不回写或热切换。

本地策略只支持 `context-capacity-v1` 和 `utf8-bytes-per-three-v1`。最终完整序列化请求体包括系统提示、权限/响应协议、工具 schema、消息、历史视图、当前草稿及回执。先记录真实 UTF-8 bytes，再估算 `ceil(bytes / 3)`。这是启发式估算，没有已标定的 tokenizer 误差上界，不能称为精确 token 数或硬容量保证。

窗口准入计算为：`available_input_tokens = max(0, input_cap_tokens - max(policy.output_reserve_tokens, payload.max_tokens) - safety_margin_tokens)`。输出预留只扣一次。因此本实现的 `input_cap_tokens` 应填写扣除输出预留前的窗口预算，不能把来源未说明的独立输入上限直接当成已标定总窗口。策略绑定 provider/model/endpoint/profile 版本、来源和日期；cap 为未知时保持 `uncalibrated`，已知本地配置通过时为 `admitted_estimate`，两者均明确 `capacity_is_hard_guarantee=false`。测试中的 cap 只是受控夹具，不是 Intern 托管 endpoint 的实测容量。

固定层与当前工作保持完整：原题全部要求、目标、定义域/量词/假设、未解决异议、角色协议、草稿、最近完整交换、当前依赖及工具请求/回执闭包。超限拒绝本次派发并返回 `context_capacity_exceeded`，保留已提交成果和来源，提供拆分建议；不静默截断原题或答案。Whole Verifier 仍独立接收完整原题、答案和必要证据；超限时不执行该次审查，不产生整题通过或 exact-text 绑定。

## 历史、摘要与来源

沿用既有持久 session 保存精确历史，先去重和确定性选择，再至多尝试一次有界历史整理。默认只有完整已结束 exchange 能整体装入限额时才形成带来源的原文摘录，否则整体回退到 `reference_only/index`。没有启动付费语义摘要；受控 summarizer 注入仅用于验证失败、超限、单次尝试和确定性回退。整理不改变固定假设，也不把历史、失效或未验证内容提升为已证前提。

旧派生摘要及历史中的嵌套旧摘要在重建前清除；来源变化、回退、空历史、禁用摘要、摘要失败或输入超限时不得复用旧摘要。工具闭包从当前回执及保留历史查找对应 `review_call_id` 请求。

pack 保存题目 hash、独立规格版本（尚未提供则未知）、配置/策略版本、源状态版本、角色、profile、完整 payload hash 和 pack hash。归档按去重历史的 1-based 索引记录准确 ranges、逐项 refs/hash；保留、归档、摘要来源和实际出站 refs 分开记录。report/Evidence 仅公开白名单元数据，不公开摘录正文、完整 prompt 或凭证。

## 已执行验收

| 验收 | 源码与结果 | 证据边界 |
| --- | --- | --- |
| 首轮相关回归 | `5f6e581`，98 项通过 | 覆盖 session、Adapter、协议、预算、恢复、最终绑定等旧行为；不是最终 SHA 的全仓结果 |
| 集成 S02 聚焦 | `d19aa56`，27 项通过，0 failure/error/skip，7.157 秒 | `artifacts/faithful-s02/integrated.json` 与 `integrated.log` |
| 公共流式 Job | 上述 27 项包含 4 项 Job 组合 | 正常三调用/绑定；同 key 重放与查询不新增调用；固定层零 HTTP/零预留拒绝；Whole Verifier 巨大答案只发前两次；unknown 原预留与 deadline 保留、普通 resume 拒绝 |
| Chromium 恢复 | `d19aa56`，1 项通过，5.3 秒 | 受控 API 的刷新/SSE 重放与显式重试；不替代 provider-live |
| 静态与官方隔离 | `d19aa56`，改动 Python 的 Ruff、差异检查通过，官方冻结文件无差异 | 不替代完整回归 |
| 长历史与巨大当前字段压力验收 | `d19aa56`，1000 条完整历史输入、1 条最近 exchange 保留；完整序列化 183623 UTF-8 bytes，返回 `context_capacity_exceeded`，provider calls=0 | 可复现脚本 `artifacts/faithful-s02/stress_context.py`、输出 `stress-context.log`；受控本地 cap 仅测拒绝和保留边界，不是 provider 容量证据 |
| 唯一六阶段门禁 | `d19aa56`，6/6 阶段通过，耗时 1441.219 秒，`source_changed=false` | runner PID 35116，2026-11-08 00:16:55 启动；阶段日志、manifest 和结果在 `artifacts/final-gates/faithful-s02-exit-d19aa56/` |
| 门禁离线全仓回归 | 1401 项，0 failure、0 error、42 skipped | 42 项均依赖 Docker：22 项要求独立验证的镜像 ID，10 项要求设置 `MATHAGENT_TEST_PYTHON_IMAGE`，8 项要求可用的精确本地镜像，2 项要求显式启用 Docker 集成；均未算通过 |
| 快速/发布/前端阶段 | fast 5 项通过；release 27 项通过；`npm ci` 成功；npm audit 0 vulnerabilities；前端检查构建成功 | bundle 有单 chunk 超过 500 kB 的非阻塞 Vite 提示；门禁阶段均退出 0 |

浏览器命令：`npm run test:browser -- tests/browser/faithful-s01-recovery.spec.ts`。集成聚焦命令：

```powershell
uv run python scripts/run_unittest_report.py --summary-json artifacts/faithful-s02/integrated.json --diagnostics artifacts/faithful-s02/integrated.log tests.test_faithful_s02_context tests.test_faithful_s02_job tests.test_faithful_s02_review_fixes
```

长门禁命令：

```powershell
uv run --frozen python scripts/run_final_gate.py --root . --output-dir artifacts/final-gates --run-id faithful-s02-exit-d19aa56
```

runner PID 35116，开始时间 2026-11-08 00:16:55（Asia/Shanghai）。原始状态、源码 manifest、各阶段日志及测试诊断位于忽略目录 `artifacts/final-gates/faithful-s02-exit-d19aa56/`。仅启动这一份长门禁，当前工具不支持单次运行里程碑自动化，未伪称创建每30分钟应用自动化；由本任务持续跟踪至结束。

门禁结束状态为 `passed`、6/6、`source_changed=false`；全仓 unittest 为 1401 项、0 失败/错误、42 项跳过，用时 1313.602 秒。跳过项均依赖经验证的本地 Docker 镜像或显式启用 Docker 集成，未把这些项当通过。runner 总用时 1441.219 秒。全门禁冻结在 `d19aa56`；之后只提交文档，不把后续文档 SHA 表述成源码经过全门禁。

## 双轴审查

### Standards

初审 0 项硬性违约、1 项 Duplicated Code 启发式发现：同次容量拒绝重复写入调用级审计。`29f0e73` 先失败验收后归一调用级事件，终止转移使用独立 `context_capacity_terminal`；同时修复两处新 import 排序。集成回归验证每次拒绝只记一次。

### Spec

初审 1 项 P2 来源缺陷和 1 项部分要求：非连续归档区间及 refs 不准确、默认纯索引被误称摘要。`29f0e73` 修补后，原 Spec 审查者只读复核 `efaf297..d19aa56`，确认两项均解除。复核者没有运行测试；实际测试结果由上表单独留证。

## 退出与下一前沿

按上述退出映射，C01–C12 均取得工程证据，S02 工程退出通过，状态限定为 `engineering-preview`。真实 provider 接收、容量标定、SLA、自然题、数学效果均未在本轮通过，分别保持 `not_run/unknown`；受控测试与摘要估算不证明能力提升。历史真实工具跳过不自动升级为通过。

S02 工程退出解除 S03 依赖。已准备 [S03 规格与工作块交接合同](../engineering/faithful-s03-handoff-contract.md)；启动 S03 前需重新检查现有窗口及依赖图，避免重复启动，并将其指向集成分支最终交接 SHA。S04/S05 等待 S03，F1 仍等待 S03、S04。不关闭 #146 或宣称完整并发实现。
