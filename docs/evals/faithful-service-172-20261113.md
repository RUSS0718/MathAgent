# #172 必要条件澄清验收（2026-11-13）

范围为父规格 #168 的 B2，起点 `4b4ab94`，集成分支 `faithful-clarification`。合同见 [B2 合同](../engineering/faithful-service-172-contract.md)。本票已达到工程退出，仅交付 #172；父规格 #168 完整服务仍未完成。

初版产品源码 `0649be6`。原公共用例在基点失败，实现后 29 项聚焦 Python 检查、9 项受控 Chromium 检查及前端构建通过。证据已从实现工作树复制到 `artifacts/issue-172-work/implementation/`；受控响应不代表真实模型闭环。

双轴审查发现公开 Run 快照可能绕过澄清回答脱敏，以及无效回答适用性、回答排队后到期、排队后重启恢复操作三个行为缺口，已在 `8a4b194`、`7bb9cbc`、`e2d4984` 修正。两轴定点复查无剩余阻塞，后续真实协议修正也已复查。报告原件为仓库外 `C:/Users/CQX/.codex/172-standards.md`、`172-spec.md` 及同前缀的 `*-final.md`、`*-live-fix.md`。修正检查为 75 项任务回归、21 项规格/候选回归、10 项受控浏览器与对应最小反例；精确命令和首轮失败保存在 `artifacts/issue-172-work/172-review/`。

| 合同 | 公共边界与证据 | 当前结果 |
| --- | --- | --- |
| B2-1 | 浏览器普通输入后生成实际尺寸问题，公开身份和允许动作；`live-05-clarification/waiting-job.json` | 真实通过 |
| B2-2 | 同 Job 的回答经 intake 复判进入规格 v2；旧依赖、候选及表达撤销 | 规格消费真实通过；失效公共反例受控通过 |
| B2-3 | 原预算/deadline/授权；重复幂等、冲突拒绝、到期保存及关联新任务；无关回答继续澄清及 unknown 显式恢复 | 必要公共反例通过；真实成功 Run 未重置根预算 |
| B2-4 | `live-05` 提问、`live-06-continue` 同任务回答/求解、`completed-readonly-03` 结果及刷新 | 真实通过；刷新 0 POST、同 Attempt、无页面错误 |

真实运行复用 #170 的配置 `artifacts/issue-170-work/service.json`，使用独立端口 8092 与 `artifacts/issue-172-work/live-data/`。模型为既有 `intern-s2`，预算仍为 48 次模型/HTTP、8 次工具、1100 秒。成功源码为 `f6b327d`，源码/配置散列与文件清单见 `completed-readonly-03/summary.json`，未改变模型或预算。

真实 Job/Run 为 `run_7486dade58087f24baa4119b8289b231`。原输入“求这个三角形的数值面积。”；模型实际询问尺寸/边长/坐标，浏览器补充“底为6厘米，对应的高为4厘米”。同 Run 的第二次 intake 提取该条件，规格 v2 保留原题，假设中出现原回答，随后 Explore、polish 和独立 whole_solution_verifier 交付 12 平方厘米，符合 `6×4/2`。五个 Attempt 均 success，whole_review=accepted、binding=same_artifact。该简单题未调用计算工具或形式工具，不将其称为工具/数学效果验证。公开报告与 Evidence 已保存在 `completed-readonly-03/`；只读截图 `answer-visible.png` 显示实际答案。

失败记录不覆盖：live-01 因 Docker 引擎关闭在提交前被就绪检查阻止；live-02 驱动缺服务配置身份，提交前退出；live-03 真实复判返回空问题对象和泛化条件，诚实失败，修正 `59ba09a`、`ef9db26` 后增加具体用户条件引用与阶段组合校验；live-04 真实首次规格返回空根义务，修正 `f6b327d` 使非空目标进入 schema 和既有有界修复。live-05 的有效英文问题被脚本中文匹配误拒绝，因此 live-06 继续原等待 Job，没有重提题目。live-06 求解实际成功，但脚本遗漏英文完整单位；后续只读复核确认结果，不新增模型调用。只读复核前两次分别因未建立认证和定位器命中两处失败，第三次通过，均未提交求解。

最终冻结门禁源码为 `1c37325`，命令 `uv run --no-sync python scripts/run_final_gate.py --root . --output-dir artifacts/issue-172-work/gates --run-id gate-01`。`gate-01` 六阶段全部通过，`source_changed=false`，耗时 1845.062 秒；完整测试 2016 项、0 failure/error、49 skip（不计通过）。快速 baseline/官方导入边界、发布检查、前端安装/审计/检查均通过。门禁后只有文档交接更新，保留此源码 SHA，不因纯文档重跑产品套件。

8092 临时服务、真实验收与最终门禁的每 30 分钟任务均已停止或删除，两个本票实现工作树已清理。失败、成功、unknown 和初始空环境诊断保持原记录。独立数学评测 `not_run`，不声称数学能力提升。官方 baseline 字节门禁通过；`tests/test.md` 未读取或修改。交接继续使用当前选择的同一模型；本会话无法确认具体代理型号，不猜测型号。
