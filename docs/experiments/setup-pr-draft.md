## Summary

为 Intern S2 五方向研究建立可审查、可停止和可归档的开发合同，解决不同方向共用基线、预算与证据口径尚未固定的问题。

```text
preflight(config)
  require offline and five disabled research features
  validate model, budget types and 15 direction documents
  compare protected file hashes with the pinned develop commit
  emit JSON with zero network requests and planned_not_implemented
```

包含总计划、PRD/技术文档/ADR、API 合同审计、离线预检和六项 CLI 合同测试。质量 CI 取得完整 Git 历史，支持 detached HEAD。

## Evidence

- **Before:** 新增小数预算反例时，512.5 token、12.5 道题、0.5 次请求均误通过，三个子用例失败。
  **After:** 计数与 token 字段要求正整数，六项 CLI 合同测试通过。
- **Before:** 原 develop 离线检查有 98 项测试；没有这套五方向离线合同检查。
  **After:** 干净 detached worktree 的 104 项测试通过，repository_check=PASS，showcase_release=PASS，新增文件 Ruff 通过。
- 官方 BASELINE manifest 和 11 个受保护文件一致。配置默认 allow_network=false，五个研究特性关闭；本轮模型 API 调用为 0。
- 原始离线日志在 ignored artifacts/setup-20261021/，摘要和内容哈希见 docs/experiments/setup-status.md；双轴审查与修复见 docs/experiments/review-and-handoff.md。
- 计划与配置不表示 S1–S6 已完成。真实 S2 usage、工具闭环、预算控制、数学效果与展示 live 证据仍待各自切片。

## Merge Danger

**Door:** two-way

文档、独立 CLI、合同测试及 checkout 深度可按逻辑提交回滚；没有数据迁移。

**Blast Radius:** tooling

质量 CI 会多取 Git 历史并运行新增离线测试。官方求解器、默认预算和运行时依赖未修改。该草案面向 develop，不自动启用研究策略，也不代表已经创建或合并 PR。
