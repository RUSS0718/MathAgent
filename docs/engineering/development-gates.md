# RiCL Runtime 开发检查

检查范围匹配本次改动。当前分支的默认验证只覆盖 Runtime 与 Provider 适配器；历史 Showcase 全仓、前端和官方评分门禁已退役。检查通过只说明命令覆盖的行为，不代表 Provider 普遍可用、机制自然参与或数学收益。

## 纯文档改动

- 检查 `git diff --check` 与最终差异。
- 核对改动涉及的相对文件链接、锚点和命令。
- 运行 `uv run python scripts/check_runtime_docs.py` 检查活跃 Runtime 文档的相对文件链接。历史导航使用固定版本。
- 文档中的 Runtime 命令发生变化时，使用临时输出目录运行对应离线命令，确认描述一致。

## Runtime 与 Provider 切片

```powershell
uv run ruff check ricl_runtime tests
uv run python -m unittest discover -s tests
uv run python -m ricl_runtime --help
uv run python -m ricl_runtime --problem "Compute 2 + 2." --offline-answer "4"
uv run python -m ricl_runtime.experiments --order-seed 17
```

将运行产物写到仓库外的临时目录，或确认 `artifacts/` 保持被忽略。机制改动还应覆盖对应聚焦合同；离线替身只证明确定性路径。

## 真实运行与实验边界

本检查流程不授权 Provider 请求或付费实验。按 [Runtime 规格，#236](https://github.com/RUSS0718/RiCL/issues/236) 和根 [AGENTS.md](../../AGENTS.md) 的人工停点，先取得模型选择、本机凭证、非敏感样例、明确预算和明确批准。真实运行、机制参与、数学正确性与研究效果分别记录。缺失的用量、成本或运行结果保持 `unknown`，不从离线验证推断。
