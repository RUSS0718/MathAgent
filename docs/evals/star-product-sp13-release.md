# SP-13 最终门禁与真实 Intern 批次证据

日期:2026-10-24。固定提交 `71fcce8`(分支 `showcase-star-product`),含 SP-12(`f77c3ec`)、恢复缺口(`344449b`)、完整 preset(`ef92490`)与终审修复(`f107d78`/`c15cd51`/`9437107`)。本文件记录该固定提交上的最终发布门禁与真实 Intern 公共 Job 小批次;不声明数学正确率提升或论文成绩复现。

## 最终门禁(全部新鲜执行)

| 门禁 | 结果 |
| --- | --- |
| `uv run python scripts/check.py --offline` | PASS:503 tests,483 通过/20 跳过(612.9s)。20 个跳过全部为 Docker 镜像 env 门控(star_product_python 3 + full_modes 11 + python_executor_docker 6),其中 9 项在下一行门禁真实执行。 |
| `uv run python scripts/check_showcase_release.py` | PASS:workspace 干净契约、`SHOWCASE_RELEASE_GATE=1` 全量套件、`check_solver_release`、BASELINE.json 逐文件 sha256、`import user_agent` 导入边界(showcase 不入 sys.modules)、replay 凭证扫描、发布证据链。 |
| 固定镜像 Docker 隔离(`MATHAGENT_TEST_PYTHON_IMAGE=sha256:fc913659…31673a2d`) | `tests.test_star_product_python` + `tests.test_python_executor_docker`:**9/9 通过,0 skip/xfail**(46.5s);engine 29.6.1,镜像 ID 精确匹配。 |
| 前端 `npm ci --no-audit --no-fund` | 66 packages,9s。 |
| 前端 `npm audit --audit-level=high` | 0 漏洞。 |
| 前端 `npm run check` | 依赖合同/类型检查/14 unit/构建 PASS。 |
| 真实公共浏览器 `npx playwright test -c playwright.product.config.ts` | **12/12 通过**(42.0s,真实 create_app+SQLite+InternChatClient→本地有限提供方)。 |

终审两轴审查(Standards/Spec)在 `ef92490` 上完成;全部发现由 `fix/star-final-review` 修复并合入(`71fcce8`),其中 reference 生效特性回归恰 9 核心、无 pipeline 时 capabilities 表达 `star_not_enabled`、预检 S3 账本内容寻址持久化(`budget_ref` 可审计)、合同镜像指纹锚定 `CONTRACT_PYTHON_IMAGE_ID` 均有 RED→GREEN 记录(见 `docs/evals/star-product-sp13-preset.md` 第五节)。

## 真实 Intern 公共 Job 批次

启动器:仓外 `star-public-live-runner.py`(经 `create_app`、认证 ChatSession、公共 Job/Run/report/Evidence 路径;无 mock、无私有求解循环)。每批先落 `preregistration.json`(硬预算 12 调用/12 HTTP/2 工具/300s/65536 tokens,超时 180s,retry=1,`automatic_unknown_retry=false`)再提交;未知请求零自动重发;`cost=null` 保留(`cost_missing_is_not_zero`);产物脱敏落 `artifacts/<batch>/` 并附 sha256 清单。模型身份 intern-s2(提供方返回 Intern-S2)。

| 批次 | 模式/题 | 结果 | 调用/tokens/工具 | 说明 |
| --- | --- | --- | --- | --- |
| `star-public-live-20261023T193454Z-9b917966` | star_limited / 简单 | **succeeded** | 3 / 3054 / 0 | unknown safe;工具未触发属自然选择 |
| `star-public-live-20261023T193546Z-f6e9d2d9` | star_reference / 简单 | **succeeded** | 3 / 3785 / 0 | 完整模式真实解锁:入队前真实 Docker 预检通过,完整预算 48/48/8/262144/1100s 实际生效;unknown safe |
| `star-public-live-20261023T193634Z-7fb65ebd` | star_reference / 工具题 | failed(needs_review) | 1 / 2755 / 0 | explore 回复 `finish_reason=length` 被 2048 输出上限截断,严格 schema 拒绝,unknown 保留、零重发 |
| `star-public-live-20261023T193804Z-67c3bec3` | star_best_effort / 简单 | **succeeded** | 3 / 3431 / 0 | unknown safe |
| `star-public-live-20261023T193835Z-dc9d7d21` | star_reference / 工具题(新预登记,单响应上限 4096) | failed(needs_review) | 1 / 958 / 0 | 回复完整(`finish_reason=stop`)但无法严格解析,按 unknown_outcome 进 needs_review,零自动重试 |

合计 11 次真实逻辑调用、13,983 charged tokens;3 成功 2 失败,失败与 unknown 全部保留原文产物。工具题两次失败均为诚实失败路径(截断拒绝/不可解析不猜测),真实自然工具选择在 live 未覆盖,记 `not_covered`,不以 scripted 覆盖冒充。

### AC-20 公共配对证据

同题(简单题 sha256 预登记)、同模型(intern-s2/Intern-S2)、同公共路径的跨模式配对:star_limited(3/3054)与 star_reference(3/3785)、star_best_effort(3/3431)各为同题配对运行;`usage.json`/`preregistration.json` 提供可导出的模型/题目/版本/预算/用量来源与失败分类(含两次失败批次的 category/stop_classification)。旧 standalone paired runner 未使用。边界:仅 1 题、简短题型;工具题配对因两次诚实失败未形成成功对。

## 结论边界

- `star_reference`/`star_best_effort` 经服务端 `SHOWCASE_STAR_FULL_ENABLED` 显式开关 + 真实 Docker 隔离预检 fail-closed 解锁;默认关闭,HTTP 不可设置。受限模式行为与官方冻结路径不变(BASELINE sha256 零差异、导入边界通过)。
- 真实批次证明公共全链路集成与预算/unknown 合同;不构成数学能力、正确率或论文成绩声明。
- 仍未覆盖:live 自然工具选择、live Trace-Back/重规划触发(记 not_covered);完整机制矩阵见 `docs/evals/star-product-sp13-preset.md`、`star-product-recovery-gap.md` 与仓外证据矩阵草稿的最终状态。
