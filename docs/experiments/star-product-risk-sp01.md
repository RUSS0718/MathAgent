# SP-01 控制与隔离执行风险基点

日期：2026-10-23。实现基点：`606d874fcee11bc161d68aa001cd706de63afbe2`，工单：[SP-01 #57](https://github.com/RUSS0718/MathAgent/issues/57)。

结论：固定来源审计和可执行风险材料已交付；Docker网络/文件/资源/超时通过对应反例，但任意代码输出上限存在实际旁路，风险门槛blocked；旧产品安全checkpoint和未知请求策略通过真实进程中断实验。**STAR已接受步骤、动作、账本与checkpoint的联合恢复门槛仍为blocked/unverified。**公共Job在基点没有STAR步骤，不能把旧planner恢复当成第二步接受后续算第三步。

## 证据边界与预算

两份脚本都是可执行验收，不新增求解循环，也不接入官方入口。恢复脚本使用真实产品 worker/LangGraph/SQLite 与公开 Job、Run、report、SSE、Evidence 接缝；仅 HTTP 提供方替换为可控回复。`SHOWCASE_MODE=live` 表示经过现有生产 pipeline，**证据来源仍是 scripted，不是真实 Intern**。

执行前上限为：恢复两场景各一次中断和一次重启，4次scripted HTTP、0工具、120秒；首批Docker11个容器，最终对抗批次12个，每个运行8秒、64MiB、16PIDs。普通stdout/stderr文件各8192字节；对抗探针仅一次16384字节写入以有界验证旁路。真实API调用为0，费用为0；不读取宿主凭证。Docker拉取公开Python镜像不是模型调用。

## 固定来源核对

全量 [SC-001..043 / AC-01..44 来源与责任映射](star-product-source-audit.md) 给出固定论文、上游 SHA、本地文件、默认配置、差异及未来唯一责任。编号为项目合同编号，不是论文原生编号。固定上游整题审核失败仍接受答案的分支已单列为有意加强，不复制到本地。

## 公共恢复：实际进程中断

执行：

```powershell
uv run python scripts/star_recovery_spike.py --output artifacts/star-sp01/recovery-1
```

输出目录必须不存在，避免混用两个批次。脚本启动独立 Python 进程，经公共 API 创建 Job；父进程在观察到指定边界后直接 kill，随后用相同 SQLite 目录启动全新产品实例并调用公共 resume。未修改数据库，也没有额外模拟求解器。

| 场景 | 触发 → 决策 → 实际动作 → 持久状态 → 用户结果 |
| --- | --- |
| 安全 planner checkpoint | `run_20f62a2fd8eb8c1a0c0ba01cfe99a7bb` 在 planner 已完成、waiting_input interrupt 后 kill → 重启识别安全 interrupt → resume HTTP 202 → 原 Run、deadline 和 checkpoint 延续，HTTP 从1累计到3，provider tokens从10累计到30 → Job succeeded，planner未重复 |
| 未知 HTTP 在途 | `run_d152023dcb12e178674af54fecad946a` 请求已被 scripted 提供方接收、未响应时 kill → 重启 needs_review → resume HTTP 409 → 原1次请求与548 token预留保留、deadline不变 → report/Evidence可查且无新派发 |

两场景 10 个可执行断言全部通过。`dispatch.jsonl` 在提供方边界独立记录实际 dispatch；断言同时核对账本，不能仅相信产品 PASS 字段。STAR 的步骤接受、Trace-Back 或重规划未触发，原因是基点公共路径尚未接入，未伪造这些事件。

## Docker：实际限制和旁路反例

执行：

```powershell
uv run python scripts/star_docker_spike.py --output artifacts/star-sp01/docker.json
```

初次 image inspect 返回不存在，未继续执行、未回退宿主。执行 `docker pull python:3.11-slim` 后重跑；本次成功批次先解析并固定镜像 ID：`sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377`。Docker Linux engine 为 29.6.1；后续 tag 更新不能冒充相同环境。脚本不自动拉取镜像。

每个受限容器启用 network=none、read-only root、cap-drop ALL、no-new-privileges、非root UID65534、memory/memory-swap=64m、CPU0.5、pids16、CPU soft1/hard2秒、文件大小硬上限8192、独立1MiB noexec/nosuid/nodev tmpfs，无宿主或其他题目 bind mount，Docker log-driver=none。

stdout/stderr在子进程开始前重定向到普通文件，Linux RLIMIT_FSIZE在写入普通文件时拒绝超额；但这不限制所有输出通道。实际对抗探针发现shell在`/proc/1/fd/10`保留原Docker stdout管道，同UID代码能重开它绕过普通文件上限。`/proc/1/fd/1`当时恰为重定向文件，该特定尝试未绕过。代码未获得Docker socket。容器退出或超时后检查Docker State与top，再删除本批容器。

| 实际反例 | 观察 |
| --- | --- |
| 连接1.1.1.1:443 | 1.094秒，非超时异常退出，网络拒绝 |
| 写只读root | 1.000秒，Read-only file system |
| 读取 `/host/sp01-canary` / `/other-task/sp01-canary` | FileNotFoundError；这些命名空间未挂载。没有使用真实宿主秘密作为探针 |
| 分配256MiB | exit137，Docker OOMKilled=true |
| 建立40个子进程 | Resource temporarily unavailable，触及16 PIDs限制 |
| 无限CPU循环 | 2.828秒，exit152，CPU time limit exceeded；未等到外层8秒deadline |
| 无限stdout / 无限stderr | 各在8192字节停止并异常退出；0.860/0.906秒 |
| 父进程与sleep子进程持续运行 | 8秒deadline后 docker kill，exit137、State.Running=false、docker top拒绝，无残留容器进程树 |
| 重开父shell保存的stdout管道 | 单次写入16384个B，超过8192上限；实际任意代码输出门槛失败 |
| 实际移除read-only的对照 | 同一root写入代码成功退出，而受限运行失败；原只读断言能识别该旁路 |

首批11个容器、12个固定脚本断言通过，不足以证明任意代码输出上限。最终对抗批次12个容器，12项通过、`arbitrary_stdout_bounded`失败，命令退出1；不把已发现旁路包装成通过。SP-09必须实现容器外有界drain/kill监督器，不能让同UID可访问的shell保留未受控输出管道。该原型尚不是产品Registry工具，不提供数学库镜像、内容寻址产物或工具Evidence合同；不得据此声称SP-09/SP-AC-15/16/17已完成。Docker配置也不证明不存在内核逃逸漏洞。

最终反例命令为 `uv run python scripts/star_docker_spike.py --image sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377 --output artifacts/star-sp01/docker-adversarial-final.json`。该命令**预期当前失败**，修复不能删除或放宽失败断言。额外诊断曾读取容器内父进程FD列表，并运行一次未成功绕过fd1的12容器批次；这些不是新能力通过记录。

## 冻结的恢复窗口与后续退出条件

无需再让用户选择状态权威：ADR-0014 已确认 Solver 数学状态、S3账本/控制、Job投影和LangGraph位置的职责。当前缺少的是产品集成，不是Docker环境失败。SP-02/03可开展桥接和控制切片，但完整参考模式必须保持拒绝启动，直到缺失的运行条件通过；不能把本报告当作完整恢复已通过。

| 崩溃窗口 | 所需恢复处理 | 最小实施位置 / 最终责任 |
| --- | --- | --- |
| S3已准入、远端结果未知 | 保留原调用/attempt/预留/deadline；needs_review，拒绝自动重发 | 复用 `run_budget.py` 与 `calls.recover_inflight`；SP-03/08 |
| 角色响应已持久化、StepReport尚未归一化 | 使用原稳定call_id读取已完成响应；不能再预留逻辑调用/HTTP | `calls.dispatch` 已有completed-response缓存，产品桥须先恢复动作而非重新计费；SP-08 |
| StepReport已保存、Verifier尚未执行 | 从STEP_VERIFY继续；Reasoner不重复；新Verifier经过原S3 | `step.py` / `verification.py` 的持久phase；SP-04/08 |
| step_accepted提交后、checkpoint尚未提交 | 以Solver最新revision和已接受步骤确定下一步；checkpoint为落后的执行投影，不倒写数学状态 | 桥接在 `WorkspaceService._execute` 原预算/控制绑定中；checkpoint关联solver_revision、stable action/call和S3 action身份；SP-02/08 |
| checkpoint指向的Solver revision不存在或身份冲突 | fail closed进入needs_review，不猜测完成情况、不新建Run | 同上；SP-08 |
| 取消/deadline后迟到输出 | 禁止数学推进/接受，仍可结算迟到usage；Job终态单调 | 原S3准入加数学commit前控制检查；SP-03/08 |

`SolverStateStore.commit_event` 已以事务提交数学快照和事件；`calls.dispatch` 先持久调用响应、再由角色归一化状态。两者**不是已经验证的跨checkpoint原子事务**。最小新生产接缝为可恢复STAR桥：沿用job_id/SQLite/原S3，记录phase及对应solver_revision/action/call身份；调用结果复用必须先于预算准入；checkpoint可落后但不能成为第二份数学权威。无需新增测试专用求解循环或复制预算账本。

联合门槛的退出用例必须从公共 Job 运行三步计划，在第二步接受后、checkpoint更新前杀进程；恢复后实际第三步被派发，前两步与接受事件各一次、账本累计和deadline不变；在响应缓存与数学接受之间另杀一次，证明缓存复用不新增调用。在接缝具备前状态为blocked/unverified，不由本次旧planner实验替代。

针对性旁路验收须包括：把过期checkpoint当权威应重跑步骤并被实际派发计数发现；在读缓存前扣预算应被累计计费断言发现；未知请求自动重发应被提供方计数发现；取消后数学commit应被接受状态反例发现。最终恢复责任为SP-08，首次可运行桥接为SP-02，独立复核为SP-13。输出旁路阻塞完整模式和SP-09隔离发布验收，不阻塞保持fail-closed的SP-02/03开发。

## 实际证据位置与结果

原始产物仅留 ignored `artifacts/star-sp01/`，不进入提交：

| 文件 | SHA-256 |
| --- | --- |
| `docker.json` | `d5085f4984c5789ab7e0f2628d6f72dfbc9416a7b1a39fe9cb12e6aa270cc612` |
| `docker-adversarial-final.json` | `b944425a7a756d4702d5c1b916157ce9f8857b9c48bdec4c5076431ad809aa5c` |
| `recovery-1/summary.json` | `90f0d49a9e0622bd5887ace59ebc096162d5c5de546b441d56379bef8b6eb936` |

`recovery-1/<scenario>/` 保留before/after公共观测、独立dispatch计数、进程日志和SQLite。复核脚本可重跑生成新批次；含时间/UUID的raw哈希自然会变化。上述哈希只绑定此次观察，不要求未来复现实验产生相同字节。

聚焦验证：`uv run python -m unittest tests.test_run_control tests.test_run_control_accounting tests.test_baseline_snapshot`：12项通过（7.400秒）；恢复spike通过，Docker任意代码输出反例实际失败并保留；`uv run ruff check scripts/star_docker_spike.py scripts/star_recovery_spike.py`通过；SC表43行、AC表44行且所有本地路径存在；`git diff --check`通过。隔离实验共38个容器（首批11、fd1尝试12、最终12、FD诊断3），另有1个镜像版本检查容器，均已清理。没有新增官方调用、修改冻结文件、伪称真实模型运行或数学正确率提升。全量基线由集成维护者在同一基点运行，343项通过；本票聚焦公共控制/基线回归已通过。风险基点退出为完成：已定位风险、执行可用反例、冻结后续合同；完整STAR恢复发布门槛及任意代码输出隔离门槛仍blocked，不循环要求SP-08先于SP-02实施。
