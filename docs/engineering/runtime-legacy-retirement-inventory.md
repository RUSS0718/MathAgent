# Runtime 旧资产退役记录

**状态：** 旧版 Showcase 与官方评分的可执行实现已从 `runtime-research-loop` 移除。此文件记录本次处置范围、保留项、验证边界和回滚依据；它不授权清理 Git 历史、远端发布或未跟踪的用户文件。

## 退役依据

- 退役验收要求首轮获批先导与干净检出的独立复跑都完成九个矩阵条件和两个回退条件。两批需能根据 Run、请求账本和脱敏 Trace 复核共享预算、失败及 `unknown`，并观察到证据进入后续请求、固定机会下的搜索排序与隔离干预。独立复跑还需提供父路线反馈采纳的可核对证据。
- [Runtime 规格 #236](https://github.com/RUSS0718/RiCL/issues/236)及[机制证据顺序 #232](https://github.com/RUSS0718/RiCL/issues/232)界定研究边界。
- [DeepSeek 真实配对先导](../evals/runtime-deepseek-paired-pilot.md)记录两批获批运行：首批 26 个响应、独立复跑 27 个响应；每批覆盖九个矩阵条件和两个合成 Checkpoint 回退条件。
- 独立复跑的原始记录保留两项 `unknown` 和零次自动计入的采纳。离线复核通过 Provider 请求关联、显式证据引用及等式检查确认一例父路线采纳。
- [DeepSeek smoke](../evals/runtime-deepseek-smoke.md)与[MiniMax smoke](../evals/runtime-minimax-smoke.md)分别记录 ModelPort 的首、第二模型验证。
- 真实先导可支持有限运行事实：请求、共享预算、部分路线/证据行为及相应失败。它们不是预注册论文实验，不建立普遍稳定性阈值，也不证明总体数学收益。

## 逐项影响与处置

| 路径 | 处置 | 影响与边界 |
| --- | --- | --- |
| `showcase/`（退役前 521 个跟踪文件，含前端和旧 Solver Harness） | 从当前分支删除 | Runtime 的状态、验证、APRS、Population、反事实与 Provider 接口由 `ricl_runtime/` 承载。旧实现仍可由 Git 历史追溯；不保留旧 Web/浏览器执行路径。 |
| `demo_server.py`、`showcase_server.py`、`showcase_cli.py`、`presentation_pages.py` | 删除 | 旧本地服务、命令行与展示入口不再可执行。 |
| `user_agent.py`、`implementations/candidates/sl_v3_cont/`（5 个文件） | 删除 | 当前分支不再复跑旧官方打榜程序。官方历史基线记录 `BASELINE.json` 保留，但不再作为 Runtime 验收门禁。 |
| `llm_client.py`、`llm_response.py`、`implementations/postprocess/` | 删除 | Provider 传输改由 `ricl_runtime/providers/` 负责；不迁移旧 Intern 适配。 |
| `scripts/start_showcase.py`、`scripts/run_solver_intern_live.py`、`scripts/run_solver_pair.py`、`scripts/run_capability_probe.py`、`scripts/run_s1_probe.py`、`scripts/run_s2_live_gate.py`、`scripts/run_star_readiness_97.py`、`scripts/star_recovery_spike.py` | 删除 | Showcase/Intern 专属运行器和 Spike 不再是当前入口。 |
| `scripts/check.py`、`scripts/check_fast.py`、`scripts/check_experiment_setup.py`、`scripts/check_workspace.py`、`scripts/check_test_seams.py`、`scripts/check_showcase_release.py`、`scripts/check_solver_release.py`、`scripts/run_final_gate.py`、`scripts/run_unittest_report.py`、`scripts/star_docker_spike.py` | 删除 | 删除旧产品、官方基线与混合全仓门禁。通用 Runtime/Provider 检查改为 `ruff`、`unittest`、CLI 与离线配对夹具；只读 Issue 状态工具仍保留。 |
| `tests/` 中旧 Profile/产品测试与辅助 worker | 删除；保留 8 个 `test_runtime_*.py`、`test_deepseek_adapter.py`、`test_minimax_adapter.py` | 保留迁移后 Runtime 与两个 Provider 的聚焦合同。用户管理的 `tests/test.md` 明确排除，未读取、修改、暂存或删除。 |
| `.env.example`、Showcase 可选依赖、`requirements-local.txt` 中的旧依赖、旧前端/发布 CI | 删除或改写 | 开发环境只安装 Runtime 与工具依赖；CI 运行 Runtime/Provider 测试、CLI 与配对离线夹具。bootstrap 保留为环境安装入口。 |
| `README.md`、`README.zh-CN.md`、`docs/README.md`、`docs/engineering/development-gates.md` | 更新 | 首要运行与验收说明只指向 RiCL Runtime。文档索引将旧记录明确标为归档，不再把它们描述为当前可运行实现。 |

## 保留材料与未决权利

- 保留 `BASELINE.json` 作为官方历史基线记录；删除其对应的旧可执行源码不等于改写历史结果。
- 保留 `requirements.txt` 的原始字节供 `BASELINE.json` 校验。RiCL Runtime 通过 `uv.lock` 安装，当前使用标准库。
- 保留 `docs/adr/`、Runtime/Provider 设计和当前验证合同。
- 保留 `docs/evals/`、`docs/replay/`、`docs/experiments/`、`examples/` 中剩余的 JSON 配置、`docs/experiments/archive/intern-s2-campaign.json` 与 `docker/`，作为历史或潜在复现材料。`examples/showcase.ipynb`、旧根级产品文档及环境/门禁模板已退役。现有仓库信息不足以逐项证明题目、答案和旧运行资料的权利/复现必要性，因此其余资料未删除，也不作权利结论。
- `artifacts/` 是被忽略的本机运行资料，本次不清理；未跟踪用户文件、Git 历史和远端发布均不在本次范围。

## 回滚与后续核验

本次改动通过一个普通 Git 提交回滚即可恢复当前分支文件。[退役前的源码与文档](https://github.com/RUSS0718/RiCL/tree/8318be2a22122ebf9e33e6eef66691461c7c5255)可用于核对历史引用。删除后应在干净检出运行 `uv sync --locked --all-groups`、Runtime/Provider 单元测试、CLI help、单题离线 CLI 和 `ricl_runtime.experiments` 离线配对夹具，并静态检查活跃代码/CI/README 中不再引用被删除入口。上述通过只证明所测研究路径可运行；本记录不把离线检查或既有小样本先导升级成正式论文结论。
