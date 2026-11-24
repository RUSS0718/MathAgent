# RiCL Runtime 开发检查

检查范围应匹配本次改动。日常 Runtime 研究不运行旧 Showcase 全仓、前端或发布门禁；检查通过只说明命令覆盖的行为，不代表 Provider 就绪、机制实际参与或数学收益。

## 纯文档改动

- 查看 `git diff --check` 和最终差异。
- 核对改动新增或修改的相对文件链接、锚点及命令。
- 如果文档中的 Runtime 命令发生变化，用临时目录运行一次离线 CLI，并确认命令和输出描述一致。不要让运行产物进入仓库。

## Runtime 代码切片

从根目录 [AGENTS.md](../../AGENTS.md) 的离线验收命令开始。只运行覆盖当前切片和不变量的检查：

```powershell
uv run python -m unittest discover -s tests -p "test_runtime_cli.py"
uv run python -m ricl_runtime --help
uv run python -m ricl_runtime --problem "Compute 2 + 2." --offline-answer "4"
```

需要时把 `--output-root` 指向仓库外的临时目录。涉及机制时，按[机制证据与渐进验收顺序，#232](https://github.com/RUSS0718/RiCL/issues/232)补充对应聚焦检查。检查依赖、公共接口或停止语义时，验证受影响的不变量，不以整仓通过替代。离线替身只证明确定性路径，不证明真实模型可调用或数学能力提升。

## 真实运行与实验边界

本检查流程不授权 Provider 请求或付费实验。按 [Runtime 规格，#236](https://github.com/RUSS0718/RiCL/issues/236) 和根 [AGENTS.md](../../AGENTS.md) 的人工停点，先取得用户选择的模型、凭证配置、非敏感样例、明确预算和明确批准。真实运行、机制参与、数学正确性与研究效果分别记录。缺失的用量、成本或运行结果保持 `unknown`，不从离线验证推断。

## 旧 Showcase 与发布门禁

以下是独立的旧版产品/发布检查，不属于 Runtime 日常研发门禁。仅在工作明确涉及这些路径或其阶段验收时使用，并遵循对应验收合同：

```powershell
uv run python scripts/check_fast.py
uv run python scripts/check.py --offline
uv run python scripts/check_showcase_release.py
uv run python scripts/run_final_gate.py --root . --output-dir artifacts/final-gates --run-id review-01
```

`check_fast.py`、全仓离线检查、Showcase 发布检查及最终门禁覆盖旧产品、baseline、前端或发布条件。不要因纯 Runtime 或文档切片默认运行这些命令；历史通过记录也不能替代当前切片的验证。
