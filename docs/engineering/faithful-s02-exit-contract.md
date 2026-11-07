# S02 上下文与容量治理工程退出合同

日期：2026-11-07（Asia/Shanghai）。状态：实施中，未退出。集成起点 `fa314fe3ff54bd1ecdd20e692337d028d7b7e901`，分支 `mathagent-faithful`，开工工作树干净。

依据：[#136 完整决议](https://github.com/RUSS0718/MathAgent/issues/136#issuecomment-6686300952)、[#144 阶段决议](https://github.com/RUSS0718/MathAgent/issues/144#issuecomment-6703147321)、[#146](https://github.com/RUSS0718/MathAgent/issues/146) 及其 Faithful implement-spec。S01 已按流式范围工程退出；其历史冻结门禁不作为 S02 当前源码证据。

## 计划与公共验收接缝

1. 核验并复用 `sessions.py` 的身份/历史、`context_injection.py` 的当前状态与失效过滤、原预算和 final binding；补充版本化策略与 pack。
   验证：公共 Job/Run 创建、持久恢复及 SolverHarness.prepare_request；默认关闭、冻结策略、不回写旧 Run。
2. 按失败验收、最小实现推进最终 payload 准入与历史治理。
   验证：实际角色出站与 Adapter/client 序列化后的完整 bytes，包含系统协议、工具 schema、当前字段和回执，不以单独消息长度代替完整请求。
3. 执行聚焦回归、集成完整门禁与独立 Standards/Spec 审查。
   验证：唯一后台六阶段 runner、测试报告和跳过清单、官方 baseline 字节与 JSON 合同、已验证 SHA；失败回到最小所属切片。

上述沿用已授权公共产品接缝。纯 pack 函数测试只补充确定性算法证据，不能替代实际 Job/出站组合验收。report/Evidence 验证公开状态与脱敏，原 final binding 接缝验证 exact-text 未被治理改变。

## 必须全部满足的退出清单

| 编号 | 可验证合同 | 退出所需证据 |
| --- | --- | --- |
| C01 | 显式新 Run 冻结版本化 context/capacity policy；默认关闭；旧 Run 不迁移、运行中不热切换 | 新/旧 Run、关闭服务配置后恢复、配置验证 |
| C02 | 最终序列化完整 payload 统一计量 UTF-8 字节和版本 token 估算；说明误差，输出预留只扣一次 | 中文、工具/schema/协议开销、边界值及实际 bytes 捕获 |
| C03 | cap 绑定 provider/model/endpoint/profile，记录来源、日期、安全余量；未知保持未标定 | 错配拒绝、未知容量投影；不虚构 128K/256K |
| C04 | 原题全部要求、当前目标、假设/量词/定义域、异议、权限协议完整保留 | 各角色出站逐字/结构断言、巨大固定字段拒绝 |
| C05 | 当前草稿、最近完整质疑往返、直接依赖闭包和工具请求/回执成对保留 | 巨大当前字段、配对与证据来源断言 |
| C06 | 已结束历史先精确去重/选择/外存，再至多一次有界摘要；不递归摘要，摘要输入独立限额 | 长 history、输入超限、摘要失败确定性回退，无额外循环调用 |
| C07 | pack 保存角色、题目/规格/源状态版本、included refs、摘要来源区间/hash/version、估算/字节/profile 与 hash | 可复现 pack；回退及源事实失效后旧摘要不复活、不升级未验证事实 |
| C08 | 固定层或当前工作超限停止派发，返回 context_capacity_exceeded，保留成果及分块建议 | 零远端发送、清晰公开状态，不截断题意/草稿 |
| C09 | Whole Verifier 保留完整原题、答案与必要证据，独立整题交叉核验 | 实际出站与绑定；答案超限明确未验证/拒绝，局部通过不得冒充整题通过 |
| C10 | 原 deadline、共享预算、unknown 预留、调用身份与 exact-text binding 不变 | 相关恢复/预算/绑定回归；刷新和重连续读不新增求解 |
| C11 | 官方路径、implementations、baseline 字节及默认预算不变 | 官方差异检查与工程门禁 |
| C12 | 完整工程退出证据可重现且双轴审查无未解决阻塞 | 聚焦、完整/发布/前端门禁，浏览器相关回归，跳过逐项保留 |

70% 触发及 50%–60% 整理目标只能作为待校准初值；不能为比例裁掉不可摘要层。优先采用确定性整理；如果支持摘要，摘要只能处理已结束历史、带非权威标签，失败回退不可改变数学假设。Whole Verifier 超限允许直接诚实拒绝，不要求本阶段引入按义务分块的新求解机制。

## 证据与交接边界

运行 raw 仅保存 `artifacts/<run_id>/`。Python 使用 `uv run`。长门禁唯一后台运行，公开 PID、创建时间、阶段、完成计数和日志末尾监控；当前工具不支持为单次任务里程碑创建自动化，不能伪称已建立每30分钟应用自动化，改为本任务持续跟踪直至结束。

不得启动付费 provider 或标定实验。工程退出仅为 `engineering-preview`；provider-live、真实容量/SLA、自然题和数学效果分别为 `not_run/unknown`。42 项 S01 跳过不因本阶段自动通过。

只在 C01–C12 全部得到实际证据后更新退出结论与 #146，解除 S03 的工程依赖。随后先检查现有窗口与最新验证提交，避免重复启动；S04/S05 等待 S03，F1 仍等待 S03、S04。不关闭总票，不宣称完整并发实现。
