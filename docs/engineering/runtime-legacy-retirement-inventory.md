# 旧 Showcase 与官方入口退役预审

本清单以真实先导源码 `f748d4b` 为盘点基点。候选路径用于核查影响和数据权利，最终删除清单需逐项确认。[旧资产退役 #246](https://github.com/RUSS0718/RiCL/issues/246)

## 退役门槛

| 证据 | 当前状态 |
| --- | --- |
| 真实先导具备统一预算、可复核 Run 和失败记录 | 九个矩阵条件和两个回退条件已完成。26 个 Provider 响应可追溯 |
| 关键机制在真实条件中执行 | 观察到搜索扩展、APRS 选路、证据进入后续请求和同源干预分支。第二批的真实父回复显式引用处理证据并给出匹配的重组等式，已对原产物离线复核 |
| 独立复跑能复核同样的边界 | 已从干净检出完成第二批真实先导，九个矩阵及两个回退条件均结束。两批使用公开加法题和合成 Checkpoint |
| 数据处置和回滚边界齐备 | 路径候选已初步识别。混合目录、旧数据权利和共享引用仍需逐项核查 |

[真实先导记录](../evals/runtime-deepseek-paired-pilot.md)

## 路径候选

| 路径或资产 | 影响及候选处置 | 核查条件 |
| --- | --- | --- |
| `showcase_server.py`、`showcase_cli.py`、`demo_server.py`、`presentation_pages.py` | 旧服务、命令行和展示入口。可作为第一批移除候选 | 核对脚本、容器入口、README 和外部调用者 |
| `showcase/` | 521 个跟踪文件，其中 `showcase/frontend/` 259 个。包含旧界面和求解 Harness | 核对独立复跑用途与仍需保留的算法来源；按功能拆分后逐项处理 |
| `user_agent.py`、`implementations/candidates/sl_v3_cont/` | 官方提交入口与历史候选。可在研究分支退役可执行入口 | 核对历史分数对应源码、形式验证和复现实验依赖 |
| `BASELINE.json`、`implementations/postprocess/`、`llm_client.py`、`llm_response.py` | 历史基线、后处理和共用传输组件 | 基线记录作为复现材料保留；组件按现存导入者决定处置 |
| `scripts/start_showcase.py`、`scripts/check_showcase_release.py`、`scripts/check_solver_release.py`、`scripts/run_solver_intern_live.py`、`scripts/run_solver_pair.py` | 旧服务、发行门禁和旧 Provider 实验入口 | 核对 CI、工程文档及需要独立保留的复跑能力 |
| `scripts/check.py`、`scripts/check_fast.py`、`scripts/run_final_gate.py`、`.github/workflows/quality.yml` | 混合门禁，含旧后端、前端和共用检查 | 保留通用质量检查。单独移除旧入口后验证 CI 引用 |
| `pyproject.toml`、`uv.lock`、`requirements.txt`、`requirements-local.txt` | 共享依赖与旧 Profile 的依赖 | 删除前核实 Flask、LangGraph 等依赖的最后一个调用者，再重生成锁文件 |
| `docker/lean/`、`docker/math-python/`、`.devcontainer/`、`.env.example`、`scripts/bootstrap.ps1`、`scripts/bootstrap.sh` | 环境构建、验证容器与本机配置模板 | 核对 Lean、数学执行、安装脚本的研究用途，按用途保留或退役 |
| `tests/` | 422 个可盘点跟踪文件，10 个 Runtime 或 Provider 聚焦测试，另有共享及旧 Profile 测试 | 保留 Runtime 套件和公共合同测试；旧套件逐项分类。用户管理的 `tests/test.md` 排除 |
| `examples/faithful-service*.json`、`examples/showcase.ipynb`、`experiments/campaign.json` | 旧示例、配置和活动清单 | 核对样例数据和 Notebook 的来源、许可及历史复跑用途 |
| `docs/evals/`、`docs/replay/`、`docs/experiments/` | 历史样本矩阵、结果、重放和验收材料。候选包括 `showcase-solver-v1.2-matrix.json`、`showcase-replay-v0.1.json`、`demo-coverage-matrix.json` | 优先保留必要的脱敏证据。题目、答案、日志及其他内容逐项核对权利后决定保留或归档 |
| `README.md`、`README.zh-CN.md`、`docs/README.md`、`DEMO_SCRIPT.md`、`PRODUCT.md`、`DESIGN.md` | 活跃索引和历史产品文档 | 更新活跃运行说明，保留历史设计与源码引用 |
| 未跟踪的本地日志、题集、答案及结果 | 此处只盘点了跟踪路径 | 单独确认位置、所有者和处置权限。远端发布和 Git 历史各有独立边界 |

执行时将入口、调用者迁移和数据处置拆开提交。回滚以确认时的分支提交为锚点，逐批回退提交并复跑受影响的入口。已迁移研究算法、ADR、真实先导和脱敏失败证据列入保留范围。

## 可执行入口的直接引用

第一批退役候选应从 `showcase_server.py`、`showcase_cli.py`、`demo_server.py`、`user_agent.py` 四个入口的直接调用者开始核对。静态扫描在 6 个脚本和 7 个测试中找到了相关引用。需要逐项判断是旧入口调用、边界检查还是历史复现：

- 脚本包括 `check_experiment_setup.py`、`check_fast.py`、`check_showcase_release.py`、`check.py`、`check_workspace.py`、`start_showcase.py`。
- 测试包括 `test_boundary_check_path.py`、`test_campaigns.py`、`test_demo_server.py`、`test_faithful_s10_run_memory.py`、`test_fast_gate.py`、`test_showcase_cli.py`、`test_showcase_run.py`。
- 其他跟踪引用位于 `pyproject.toml`、`implementations/candidates/sl_v3_cont/__init__.py`、`showcase/__init__.py` 和 `showcase/experiment_sources.py`。还需核对 README、开发门禁和旧 Notebook 的引用。

## 逐项影响与建议处置（2026-11-25；仅盘点，未删除）

基点为当前集成提交 `051a317`。两批真实先导各覆盖九个条件和两个回退臂，足以核对 Runtime、共享账本及若干机制在这两次小批次中的运行事实；它们不是预注册论文实验，也没有给出可推广的稳定性阈值或数学效果结论。#233 冻结的条件语义以其决议评论为准。

| 处置批次 | 精确路径 / 可复核数量 | 依赖与处置建议 | 未决风险 |
| --- | --- | --- | --- |
| 删除候选：展示入口 | `showcase_server.py`、`showcase_cli.py`、`demo_server.py`、`presentation_pages.py`；`showcase/` 共 521 个跟踪文件，其中 `showcase/frontend/` 259 个、`showcase/solver_harness/` 113 个 | 删除前迁移/移除直接调用者；新 Runtime 核心位于 `ricl_runtime/`，历史提交仍可追溯 | Showcase 中的求解 Harness 是旧实现来源；需确认哪些历史源码只需留在 Git 历史、哪些必须作为复现材料保留 |
| 删除候选：官方执行路径 | `user_agent.py`；`implementations/candidates/sl_v3_cont/`（5 个跟踪文件） | 可执行入口可退役；`BASELINE.json`（1 个文件）建议保留为官方基线哈希与历史结果记录 | 删除会使当前分支不能直接复跑旧官方程序；此影响须在最终清单明确接受 |
| 删除候选：旧模型/后处理支持 | `llm_client.py`、`llm_response.py`、`implementations/postprocess/`（2 个跟踪文件） | 仅在引用者均随旧 Profile 迁移或退役后删除 | AST 导入盘点显示旧测试有 68 个文件导入 `llm_client`、2 个导入 `llm_response`；与 Showcase 测试集合存在重叠，不能按计数直接相加 |
| 删除候选：专属脚本 | `scripts/start_showcase.py`、`scripts/check_showcase_release.py`、`scripts/check_solver_release.py`、`scripts/run_solver_intern_live.py`、`scripts/run_solver_pair.py`、`scripts/run_final_gate.py` | 逐个移除入口，并保留或改写其中仍承担通用 Runtime 检查的行为 | 其中发布/最终门禁被共享 CI 调用，不能先删脚本再修 CI |
| 改写而非整体删除：混合检查与 CI | `scripts/check.py`、`scripts/check_fast.py`、`scripts/check_experiment_setup.py`、`scripts/check_workspace.py`、`.github/workflows/quality.yml`、`.pre-commit-config.yaml` | 保留通用 lint、Runtime/Provider 测试和离线 CLI 验收；移除旧入口及 Showcase 前端门禁引用 | 静态字符串扫描找到 143 个含旧入口名称的跟踪文件，含历史文档引用；需区分活跃调用与历史叙述，不能机械全局替换 |
| 改写依赖配置 | `pyproject.toml`、`uv.lock`、`requirements.txt`、`requirements-local.txt`、`.env.example`、`pytest.ini` | 确认被保留脚本/测试无引用后，再删除 Showcase 专属可选依赖并重建锁文件 | 旧测试及门禁仍引用 Flask/LangGraph/DeepAgents；先裁剪调用者和测试，再调整依赖 |
| 逐项分类旧测试 | `tests/` 共 422 个跟踪文件；保留 8 个 `test_runtime_*.py` 与 `test_deepseek_adapter.py`、`test_minimax_adapter.py`；`tests/test.md` 永远排除且不得读取 | 删除与退役代码强耦合的旧测试；保留能独立证明迁移后算法/通用合同的测试 | AST 显示 386 个测试/辅助 Python 文件直接导入 `showcase`；应按具体测试职责裁定，不把辅助脚本误计为可执行测试 |
| 保留/待权利确认的历史材料 | `BASELINE.json`；`docs/adr/`；当前 Runtime/Provider 文档；`docs/evals/`（129 个跟踪文件）、`docs/replay/`（1 个）、`docs/experiments/`（21 个）、`examples/`（4 个）、`experiments/campaign.json` | 先保留必要的历史设计、已脱敏能力/失败证据和研究复现材料；数据处置前核查来源、所有权、许可与复现用途 | 现有仓库证据不能替代数据权利确认；不能据文件名推断可删除或可公开 |
| 明确不处理 | Git 历史、远端发布、未跟踪或被忽略的本机文件、`artifacts/` 中已有运行资料 | 不清理、不改写、不迁移 | 这些范围不在当前分支退役授权内 |

执行建议按可回滚切片进行：先移除 Showcase 入口和调用者，重写混合门禁并验证 Runtime；再处理官方入口/专属依赖；历史测试与数据单独分类。每片执行前记录当前提交，执行后跑聚焦回归。该表仍是建议处置，不会自动删除表中路径。

## 配对实验能力边界补充

离线矩阵已验证 Baseline 通过受控 `ToolExecutor` 取得真实回执；已批准的两批真实先导明确将工具调用上限设为 0。因此真实先导不能作为“Baseline 具备常规工具能力”的证据，也不应用于比较工具可用时的机制效果。当前报告保留这一限制；任何启用真实工具的后续 Provider 配对都需要独立确认新的请求与费用边界。
