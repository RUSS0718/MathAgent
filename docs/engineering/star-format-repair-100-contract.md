# #100 纯序列化修复实施合同

基点：`dc9dc807314ad3fe27373e9a5111fdf3dcc6752a`（#98 已验收）。本票只交付离线工程候选，不执行真实 provider，不修改历史消耗记录。

## 接缝与步骤

1. 公共 `InternModelPort.complete/verify`：完整可见坏回复与受限引用；验证严格解码、内容相等、角色 schema / 工具参数语义。此接缝不证明数学正确。
2. 公共 Job 创建 / GET / report / evidence / cancel：验证 opt-in、一次持久额度、原 Run 的 logical/HTTP/token/deadline、并发与公开脱敏。此接缝不证明真实 provider 兼容。
3. 公共 Harness 恢复与现有 CLI 离线入口：验证恢复不重置额度、unknown 零自动重发；CLI 仅检查离线默认入口，不启动真实批次。

每片先失败测试，再最小实现与相关回归，提交中文主题及 `Refs: #100`。最终完整组合门禁由主聊天协调。

## 范围与拒绝条件

新增 `serialization_repair`，默认 false，显式开启时替代旧同角色重问。要求 `stream_recovery` 审计并强制 #98 strict completion。原始完整 UTF-8 可见文本单独存入私有目录，不复用可下载工具目录；公开审计仅存绑定 Run/call/problem 的 SHA-256 引用，不留原文或片段。目录使用 POSIX 0700/0600 或 Windows 当前用户和 SYSTEM ACL；ACL/存储失败即拒绝候选。生命周期跟随本地工作区，由管理员离线清理整个私有目录，无 HTTP 下载接口。

可证明子集：严格 JSON 对象，或完整的单个 Markdown JSON fence 内严格 JSON 对象。仅移除确定的外层 fence/空白；重复键、NaN、非法转义、尾随内容、空、length、无终止/用量、半截 JSON、schema 回显、缺字段及无法确定原值均拒绝。候选通过严格角色 schema、工具参数、提议标签/数量/引用语义，并与原文解析值做类型敏感的全结构相等比较；不从模型自述推断保真。

修复请求不含原题、会话、其他题目、隐藏推理、完整 prompt 或工具能力，仅含此回复的完整可见原文、目标 schema 与安全错误分类。原文一律标为不可信数据。修复只返回数据，经原角色正常权限与审查流程消费；提议不成为工具回执或已证事实。

请求根沿既有 retry 谱系归一，CAS 持久消费一次额度后派发独立 `:serialization-1`，失败/重启不恢复额度；未知保留原 attempt/预留/deadline，不自动重发。预算、取消和终态继续受 S3/#98 栅栏约束。

## 验收映射

| 条件 | 可执行证据 |
| --- | --- |
| F05 已知完整坏 JSON、长证明/代码/参数保真 | Port 与 Job 测试；独立字面量和修改候选负例 |
| F06 length/空/半截禁止修复 | Job/Port 分类及零新增派发断言 |
| F08 无工具权限、取消/并发/身份、一次额度 | Job 与公共 Harness 恢复测试，原 Run 账本断言 |
| F10 schema 回显、指令/跨题/转义/重复提议/篡改 | Port 与 Job 负例；公开输出/证据/下载扫描 |
| 官方边界 | baseline、Ruff 与相关模块完整回归；不声称全仓门禁通过 |
