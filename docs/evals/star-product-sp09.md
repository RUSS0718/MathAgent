# SP-09 生成 Python 与执行产物验收记录

日期：2026-10-23。工单[#65](https://github.com/RUSS0718/MathAgent/issues/65)，合同见[SP-09合同](../engineering/star-product-sp09-contract.md)。证据来自 scripted public Job、拒绝反例和本地 Docker 对抗执行；没有真实模型 API 调用，也不证明数学正确率提升或完整 STAR 能力。

## 固定执行环境

| 项目 | 实际值 |
| --- | --- |
| Docker Linux engine | `29.6.1` |
| Python base image | `python@sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377` |
| 最终数学镜像 ID | `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d` |
| Python / SymPy / NumPy / mpmath | `3.11.17` / `1.14.0` / `2.3.4` / `1.3.0` |
| sandbox policy label | `docker-python-v1` |

配方通过 `docker build --pull=false --tag mathagent-python:sp09 docker/math-python` 构建。最终镜像的本地 ID 和标签由 `docker image inspect` 复核。测试执行器只接收该完整 ID，额外再次核验本地镜像 ID 和标签；缺失、损坏或标签不符时不创建容器。

## 公共产品路径

`$env:MATHAGENT_TEST_PYTHON_IMAGE='sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d'; uv run python -m unittest tests.test_star_product_python`：3 项通过。测试经真实 `ToolRegistry` 和 Flask authenticated Job 执行固定因式分解脚本，模型 HTTP 由有限 scripted replies 提供。公开结果观察到同一 Job 的 S3 `tool_calls=1`；Docker daemon events 独立观察到成功和输出越界两条运行各一次 container `create` 和一次 `destroy`。

该 Job 的执行 receipt 显示 `executed=true`、退出码0、`cleanup_verified=true`，验证标签范围是 `finite_computation`。独立 HTTP 请求下载 code、canonical Registry input、stdout、stderr 和 receipt 五种 artifact；响应 bytes 的 SHA-256 与引用一致，input 内容精确等于 `{"code": CODE}`。新 app 实例重新打开同一 Job 后仍可下载相同 stdout。Job、report 和 SSE 不含 code 或 stdout 原文。

同一公共 Job 接缝强制发出 `python_math` 请求而关闭 `local_code_tool`：产生 `tool_not_allowed` receipt，S3 工具动作0，Docker event为0。另一公共 Job 运行原始 FD 输出越界探针：receipt 为 `output_limit`，保留输出不超过16000字节、观察字节多于16000、`assertion_matched=false`，且仍可完成后续审查。artifact HTTP 对无认证请求返回401；认证请求的格式错误 digest 返回409，缺失 digest 返回404。Tampered bytes 的 hash 检查另由 artifact store 回归用例覆盖。纯推理/不支持角色在工具表和执行准入两侧拒绝；MetaGuidance 对纯推理的触发归 SP-07，本票不宣称该完整切换已通过。

追加的公共 Job 故障注入回归覆盖两种私有值：step ID 在 Job/Run 的内嵌工具 receipt 中显示为“步骤 1”；未知模型工具名在 top-level name 与 receipt 中显示为 `unsupported`，且工具/S3/Docker 均未派发。Report、Evidence 和事件中不包含该私有工具名。私有工具名用临时 schema bypass 注入，仅用于验证准入栅栏；正常 Intern 响应仍受受限枚举校验。该组测试只覆盖工具 receipt 与工具名投影；`request_attempts.solver_call_id` 的公开投影归 SP-04 处理。

## Docker 对抗执行

命令：`$env:MATHAGENT_TEST_PYTHON_IMAGE='sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d'; uv run python -m unittest tests.test_python_executor_docker`。最终批次6项通过，41.103秒，共15个容器；每次结束后独立查询 `docker ps -a`，没有保留该 Run 标签的容器。

| 检查 | 观察到的结果 |
| --- | --- |
| 导入锁定数学库并分解表达式 | 运行时 Python 与三个数学库版本匹配镜像标签；输出正确，退出0 |
| 合并 stdout/stderr 限制 | 保留总量不超过8192字节；越界状态为 `output_limit` |
| raw FD、FD10 等效直写、无换行及无效 UTF-8 | 外部 drain 仍检测并截断；SP-01 原 `/proc/1/fd/10` 失败敏感性记录未修改 |
| 无限输出 | 容器被实际终止；不把被截断输出计作 success |
| 只读 root、网络、宿主/跨题命名路径 | 写入和连接失败；命名探针不存在于容器挂载中 |
| 512 MiB 分配和超限子进程 | Docker memory 与 PID 限制阻止成功执行 |
| 忙循环 | 2秒 CPU 软限制在8秒外部 deadline 前结束执行 |
| 父进程和sleep子进程、主动取消 | 整个容器停止并删除；状态分别报告 timeout/canceled，未残留带标签容器 |

另一次聚焦 CPU 重跑用于修正并确认 0.5 CPU quota 下的 CPU 时间窗口，1项通过，7.273秒。最终完整 Docker 批次在该修正后重新执行。没有删除 SP-01 对原型旁路的失败记录；产品测试通过 `dup2(1, 10)` 再直接写入来验证外部上限覆盖同类原始文件描述符输出。

## 其他检查

最终聚焦回归：`uv run python -m unittest tests.test_python_executor tests.test_star_product_runtime tests.test_star_product_jobs tests.test_star_product_tools tests.test_star_product_python`，21项通过，18.933秒。全部变更 Python 文件的 `uv run ruff check` 通过，`git diff --check` 通过。

`uv run python scripts/check.py --offline`：378项通过，9项跳过，233.459秒，`repository_check=PASS`；脚本也确认 Demo 和 Showcase `--help`。随后 `uv run python scripts/check_showcase_release.py`：`showcase_release=PASS`。Release 脚本与 offline 检查顺序执行，未并发重复跑全量测试。

## 证据限制

- HTTP 回复是 scripted；没有真实 Intern 请求或受控模型策略能力结论。
- 认证模型当前为本地单用户；已覆盖无认证拒绝，没有声称不同用户之间的隔离验收。
- Docker namespace 和资源反例证明这些配置路径有效，不证明不存在内核逃逸。
- 有限计算结果不构成证明；`star_reference` 和 `star_best_effort` 仍保持入队前拒绝。
