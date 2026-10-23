# SP-09 受控 Python 与可核验产物合同

Issue [#65](https://github.com/RUSS0718/MathAgent/issues/65) 承接父 spec [#56](https://github.com/RUSS0718/MathAgent/issues/56) 的 SP-AC-15/16/17。本文定义受限 STAR 中模型生成 Python 的产品边界；实际证据和未关闭项见 [验收记录](../evals/star-product-sp09.md)。本票完成不解锁 `star_reference` 或 `star_best_effort`。

## 执行边界

- 只有可信 server config 提供本地镜像的完整 `sha256:<64 hex>` ID 时，STAR runtime 才注册容器 Python。Flask app 可从环境变量 `SHOWCASE_STAR_PYTHON_IMAGE_ID` 读取该 ID；Workbench 请求不能选择镜像、路径或 Docker 参数。`SHOWCASE_STAR_ENABLED` 仍须显式开启。
- 运行前通过本地 `docker image inspect` 核对 image ID、`docker-python-v1` policy、Python 版本、基础镜像 digest 和数学库标签。缺镜像、daemon 不可用或标签不符时 fail closed，不拉取镜像、不退回宿主 Python。未配置时不注册 `python_math`，旧 AST 模式不变。
- 容器使用 `network=none`、只读 root、非 root UID、无 capabilities、no-new-privileges、256 MiB memory/swap、0.5 CPU、32 PIDs、CPU 2/3 秒软硬限制、文件大小上限、无执行权限的独立 `/tmp`，没有 bind mount。Python source 通过 stdin 提供；没有 shell 插值。
- Docker CLI stdout 和 stderr 由容器外二进制 drain 线程共用总字节上限。超过、超时或取消时终止并移除实际容器；只有检查并确认清理后才报告 `cleanup_verified`。清理状态未知时保留 `unknown_outcome`，不猜测零退出码。
- 每个 Registry 调用以 canonical JSON 保存实际 arguments（`{"code": "..."}`），并分别保存 Python source、stdout、stderr 和执行 receipt。SHA-256 内容引用归属同一 Run；下载路由先检查登录和 Job 所有权，再核验 digest。Job、报告和 SSE 只投影脱敏摘要与引用，不带代码或原始输出。
- `easy-verify` 仅在真实成功 receipt 与预期有限计算匹配后标记 `verified`，范围为 `finite_computation`。未执行、拒绝、输出越界、非零退出、超时、取消、unknown、损坏或缺失引用都不能提升该标签；有限计算不代表完整证明。

## 受信任运行配置

镜像构建以 `docker/math-python/Dockerfile` 为唯一配方。它锁定 Python base digest 与 SymPy、NumPy、mpmath 版本，并把标签写入 image config。运维先用 `docker build --pull=false --tag mathagent-python:sp09 docker/math-python` 构建；取出完整 ID 后，通过 `SHOWCASE_STAR_PYTHON_IMAGE_ID` 配合 `uv run python -m showcase.flask_app --mode live --star-limited` 启动。STAR 工具与模型调用继续使用 Job 的 S3 预算；容器 Python 的默认工具预算为 2，允许一次工具后继续模型审查。

生产 `create_app` 与 CLI 通过同一个 `create_star_product_pipeline` factory 建立 Registry。镜像缺失时，不创建容器且没有宿主 fallback。此入口保持默认关闭，也不影响根目录官方评分路径。

## 验收接缝

- 真实 Docker 对抗测试直接调用 production executor，镜像只从 `MATHAGENT_TEST_PYTHON_IMAGE` 接收 exact image ID，不自动 pull；容器派发次数通过 Docker daemon events 和独立的 `docker ps -a` 查询观察。
- 产品验收穿过 authenticated public Job、真实 ToolRegistry、S3 账本、Job/Run、报告、SSE 与 artifact HTTP；模型 HTTP 使用有限 scripted replies，不调用真实模型 API，也不读取 private Job state。
- pure-reasoning 及不支持的 role 必须在提示工具表和执行准入两侧拒绝。MetaGuidance 如何触发并持久化 pure-reasoning 切换仍归 SP-07；本票只验证切换后的执行栅栏，不声称 SP-07 完成。
- SP-01 报告中的 `/proc/1/fd/10` 输出旁路保持为风险敏感性证据；产品测试另用 `dup2(1, 10)` 后直接写入，确认外部 aggregate guard 覆盖不经 `print()` 的文件描述符写入。
