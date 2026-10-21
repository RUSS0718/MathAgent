# 本轮实验设置状态

日期：2026-10-21。基线：develop 的 5b0e1912e1cc82d7ab1ecd3bcb8ea5ffc10933ae。当前工作分支：chore/experiment-setup-intern-s2。该状态只覆盖本轮离线设置，不代表 S1–S6、五个算法或 live 实验已经完成。

## 已完成

- 读取 AGENTS.md、文档索引、相关 accepted ADR、官方 baseline 与提交规范。
- 从用户指定 develop 创建并签出本地 setup 分支。
- 固定并阅读 Matt Pocock skills 上游版本 5beb35b040e3de97e54fa9e386d7e42d15c295c2，采用当前 to-spec、to-tickets、TDD、双轴审查与 PR 模板。
- 使用 uv sync --locked --all-groups 安装锁定的开发环境，Python 为 3.12.14。
- 执行原仓库 scripts/check.py --offline，98 项 unittest 通过，workspace contract、test seam 检查和两个服务的 --help 通过。
- 新增总计划、仓库审计、Intern S2 合同、五组 PRD/技术规格/ADR 和默认离线的实验配置。

## 检查环境说明

首次默认隔离环境禁止创建本地 socket，导致 7 项 HTTP 服务测试出错及嵌套回归失败。未修改测试或产品代码；在允许 127.0.0.1 临时监听的环境重跑后，98 项全部通过。重跑只使用离线替身，没有调用模型 API。该环境因素不能报告为产品修复。

运行日志位于被忽略的 artifacts/setup-20261021/。配置检查和后续质量结果在收尾时更新本页；日志不提交到 Git。

## 尚未完成

- S1–S6 的 usage 贯通、工具原生协议、Run 预算隔离、live 取消/恢复、最终证据绑定和配对 runner。
- API 短 probe、AC-06 的当前 Workspace live 证据、12 题成本试跑及数学效果评估。
- 五个方向的算法开发与实验分支启动、组合消融、学术结论。
- GitHub Issues、远端推送、PR 和合并。这里没有预造 Issue/PR 编号。

本地没有配置 INTERN_API_KEY，也没有仓库 .env 文件；仅检查是否存在，没有读取密钥。现阶段 API 计量、账号额度和费用均未实测。配置文件中的预算是后续调度合同，不是已经实施的在线限额控制。
