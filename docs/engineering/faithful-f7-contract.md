# F7 公开系统视图与可恢复深链合同

状态：范围与 URL scheme v1 于 2026-11-11 冻结；工程退出已完成，达到 `engineering-preview`。结果、源码 SHA 和证据见 [F7 分层验收记录](../evals/faithful-f7-20261111.md)。GitHub 合同：[F7 #153](https://github.com/RUSS0718/MathAgent/issues/153)。

## 范围

- 只读 Run 列表与详情、既有依赖图、F6 持久化输出、证据锚点和验证等级。
- 展示等级来自同一公开持久化快照，保留 `VERIFIED L2`、`VERIFIED L3`、`REVIEWED`、`BEST-EFFORT` 之间的边界。
- 只读取已持久化 PresentationArtifact；缺失时显示 unavailable，不调用 F6 POST 表达接口，不新建产物。
- 禁止在线编辑、写 API、新的验证能力、额外打分入口、旧 Run 迁移、隐藏求解与重试。
- F7 API/UI 只投影脱敏公开字段，不包含完整 prompt、凭证、隐藏推理、证明正文或未脱敏内部 payload。
- F7 显式启用且默认关闭；不改变 `user_agent.py` 官方路径、默认预算或 baseline 字节。

## 不可变深链 scheme v1

```text
/dashboard/system?scheme=f7-deeplink-v1&run=<run-id>&output=<output-request-id>&artifact=<presentation-artifact-id>&graph=<graph-version>&node=<node-id>&paragraph=<paragraph-id>&mode=<solve|teach|report>
```

- `run` 是公开 Run/Job ID。
- `output` 是 `PresentationArtifact.output_request.id`，标识 F6 独立表达请求。
- `artifact` 是 `PresentationArtifact.artifact.id`，标识精确的持久化产物版本。
- `paragraph` 是 F6 `paragraph.id`，如 `paragraph:1`；与 artifact 身份联合定位，禁止从数组位置重算。
- `graph` 与 `node` 共同定位公开依赖图快照和节点；二者可选。
- `mode` 只选择已有持久化模式，不触发表达生成。
- 所有参数 URL 编码。v1 的键名与含义永久固定；改变语义必须创建新 scheme 版本。
- 身份字段缺失或互不匹配时留在当前 Run 详情并显示 unavailable，不猜测目标、不跳到另一 Run、不补造身份。

## 验收合同

| 编号 | 断言 | 证据要求 |
| --- | --- | --- |
| F7-01 | v1 深链以 run/output/artifact/paragraph 联合定位；直接打开、刷新、重开恢复同一视图 | 真实 F6 持久化交付物的浏览器测试 |
| F7-02 | graph/node 组合定位已有图快照；未知目标只降级当前 Run | 公开图浏览器与 API 测试 |
| F7-03 | 查询仅读取已有公开数据；不创建表达、不调用模型/工具、不重试 | 新增 API surface 仅 GET；脱敏白名单；浏览器网络断言无写请求 |
| F7-04 | L2、L3、REVIEWED、BEST-EFFORT 按保存等级区分，前端不重算或升级 | 真实 F6 交付快照与分层等级断言 |
| F7-05 | 桌面和移动浏览器加载真实 Run 的 F6 产物、Run 列表与证据锚点 | 实际 Harness → SQLite → F6 → F7；合成图单列 |
| F7-06 | 500 节点图渲染可用性实测 | Chromium 桌面 1440×1000 下 synthetic 500 节点首帧 ≤2 秒；同一冻结样本重复 3 次，记录耗时、P50/P95、浏览器版本和样本标记。真实最大图另记规模/耗时。此为本地渲染门槛，不代表 provider SLA |
| F7-07 | 全量测试零失败/错误、F6 相关回归通过、双轴审查无阻塞 | 冻结源码 SHA、命令、报告、skip 与未验证项 |

Synthetic 图只证明渲染压力结果，不能代替真实 F6 交付物和锚点的浏览器证据。

## 显式入口与复验

前端在 `showcase/frontend/chat-frontend/` 以 `VITE_F7_SYSTEM_VIEW_ENABLED=true` 构建；后端用 `uv run python -m showcase.flask_app --faithful-system-view` 启用。默认构建隐藏并关闭系统视图路由，默认后端不注册 F7 API。F6 表达生成仍只在原有显式写入口完成；系统视图只列出已保存输出，选择具体输出后才展示该产物。

`npx playwright test --config playwright.f7.config.ts` 自动构建显式启用的前端，运行真实本地 HTTP/Harness/SQLite/F6 链路和独立 synthetic 压测。可用 `F7_FORMAL_MANIFEST` 指定已验证的 S09 部署 manifest，配合 `F7_FORMAL_GRADE=L2` 或 `L3`，以 `--grep 'real persisted'` 复验实际 Lean 交付物。它复用已有验证能力，不增加验证通道；本地脚本化 provider 不代表线上模型或自然题效果。
