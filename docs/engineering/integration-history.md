# 集成历史与证据映射

本分支从 develop 的固定基点重建为八阶段、每阶段代码/测试/文档三条提交。
原始355条提交保留在 `archive/showcase-star-20261102-pre-consolidation` 标签及
`showcase-cp-checkpoint-integration` 分支。机器映射见 [integration-history-map.json](integration-history-map.json)。

前七阶段的完整检查点与原阶段 Git tree 完全相同，包含合并冲突解决及前端二进制资产。
最后阶段相对原交付只增加本映射、本文、来源回归测试，并迁移发布矩阵的当前源码锚点。
共享客户端另包含固定版本 Ruff 要求的格式及两处等价 isinstance 联合类型写法修正，已核验归一化 AST 相等。
其余业务代码、测试、默认开关及官方 baseline 不变。代码/测试/文档分组的中间提交不保证完整门禁通过；以最终交付验收为准。

## 证据来源

旧矩阵的源码锚点 `6c7a7685495912686a0dc3501a077be14f3c10e6` 不属于重建后的祖先链。
矩阵 `source_commit` 改指向第一阶段的等价新检查点，保留 `historical_source_commit`；
两者 Git tree 相等，原祖先校验仍执行。嵌套历史实测来源、时间、用量、失败与 unknown/not_run 记录保持原样。
这次重排不是重新执行历史 live 实验，也不升级数学正确率或真实提供方能力结论。

使用完整 Git 历史运行来源检查。CI 的 checkout 保留 `fetch-depth: 0`；审计分支和标签随本次交付发布。
冷克隆或单分支浅克隆需要先获取完整分支与审计标签，不能只依赖某台机器残留的 Git 对象：

```sh
git fetch origin '+refs/heads/*:refs/remotes/origin/*' --tags --unshallow
```

完整克隆省略 `--unshallow`。最后阶段文档提交自身的 SHA 通过以下命令确定，避免把自身 SHA 写进其内容：

```sh
git log -1 --format=%H -- docs/engineering/integration-history-map.json
```

运行 `uv run python -m unittest discover -s tests -p test_history_consolidation.py` 核验树等价、
新锚点祖先关系和六文件交付差异白名单。完整门禁使用 `scripts/run_final_gate.py`，记录属于重整后源码的新验收结果。

固定 Docker 数学环境的正向验收改用执行器既有生产默认窗口，避免用3秒测试夹具判定环境不可用。专用超时、CPU、输出、取消和清理用例的原有限制不变，生产执行器无修改。首轮重整门禁的单项超时失败保留为失败证据，不计为通过。
