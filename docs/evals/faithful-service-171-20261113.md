# #171 提交找回验收（2026-11-13）

范围为父规格 #168 的 B1，起点 `d95d507`。合同见 [服务入口合同](../engineering/faithful-service-entry-contract.md)。本票不代表完整服务或数学能力提升。

当前仍在验收，尚未达到工程退出。产品初版 `0a9f859`，审查修正源码 `0e41ccb`；最终门禁结果待补。

| 合同 | 公共入口、状态与证据 | 结果 |
| --- | --- | --- |
| B1-1 | 公共 GET `/api/agent/submissions/<key>` 找回持久 Job；浏览器发送前保留输入、摘要和身份，丢失回执后刷新/重开核对；实现工作树 `artifacts/issue-171-work/red-green.txt` | 受控通过 |
| B1-2 | 同身份同输入复用、不同输入冲突；浏览器显式再次求解使用新身份 | 受控通过；输入保留修正后 13 项浏览器通过 |
| B1-3 | Web Locks 串行化同源标签提交；3 个浏览器案例、公共 API 单项及 7 项 Job 回归；真实旧 Run 只读恢复 `artifacts/issue-171-work/read-only-ui.json` | 受控及真实只读通过 |
| B1-4 | 复用 #170 的真实 Run，未为刷新另开模型；响应丢失为公共边界受控注入 | 通过（证据类型分开） |

## 真实旧 Run 的只读恢复

在 `0a9f859` 构建前端，沿用 `artifacts/issue-170-work/service.json`，通过 SQLite backup 将原数据复制到 `artifacts/issue-171-work/live-data/`，在 8091 启动独立服务，未替换 8090。原真实 Run 为 `run_e15b36f035378d6adabbf3e0f4a384f7`，会话为 `session_8be53078caa0fffa35e2238a077599fc`；模型和工具证据沿用 [#170 记录](faithful-service-170-20261113.md)，本轮无新增模型调用。

执行 `node artifacts/issue-171-work/read-existing.mjs`，实际打开会话、刷新、在同一浏览器上下文重开第二标签，并读取原 Job。`read-only-ui.json` 记录 `same_attempts=true`、`posts=0`、`errors=[]`、`numbers_visible=true`，原答案 338350 与 57240530425 可见；截图为 `answer-visible.png`。首次脚本在服务未监听时连接失败；扩充第二标签时误用 Playwright 单页上下文导致脚本报错，改为显式 context 后通过。两者不计验收成功，也没有创建求解。

## 受控反例与审查

公共查询反例首次为 HTTP 404（预期 200），实现后单项通过。浏览器首次响应丢失后只显示网络错误、未核对，修复后 3 项通过；另有入口回归 8 项通过、类型检查通过。受控 API 使用 fake 执行，不将其表述为真实模型成功。

Standards 审查发现核对期间缺少 `aria-busy`；Spec 审查发现再次求解丢失附件和表达模式，以及本记录/最终门禁证据尚未完成。前两项已在 `0e41ccb` 修正，两项新增回归先失败后通过，13 项浏览器和类型检查通过；复查及最终验收补齐后退出。报告原件在仓库外 `C:/Users/CQX/.codex/171-standards.md` 与 `171-spec.md`。

最终冻结门禁：`not_run`。独立数学评测、新题真实求解：`not_run`，不是本票恢复能力的替代证据。官方 baseline 字节核对以最终门禁为准；受保护 `tests/test.md` 未读取或修改。

