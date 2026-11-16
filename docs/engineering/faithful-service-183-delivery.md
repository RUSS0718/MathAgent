# #183 当前机器阶段交付

## 2026-11-16 当前入口

用户最新允许受控路由工程验收并要求尽早收尾。能力映射及实际限制见
[阶段记录](../evals/faithful-service-183-20261115.md)首节，退出要求见
[当前合同](faithful-service-183-contract.md)。受控接线不等于自然触发稳定性，
不声明数学正确率或F8通过。live33已有两份真实模型答案、首题真实Lean L2、
真实UI/刷新及独立禁worker重启一致证据；自然缓存未命中，旧失败保持。

当前机器使用以下命令；8103已监听时复用实例，不重复启动：

```powershell
Set-Location -LiteralPath 'D:\project\工程化MathAgent\Challenge-Cup-2026'
uv run --env-file .env python showcase_server.py --mode live --host 127.0.0.1 --port 8103 --faithful-config artifacts/issue-183/live33/service.json --data-dir artifacts/issue-183/live33/data
```

需要既有.env、uv依赖、Docker及固定Python/Lean镜像、已构建前端和上述持久目录。
不部署公网，不把本机配置当作干净环境安装包。新任务保持48模型/48HTTP/8工具、
2097152 token/3600秒、faithful-stream-v1；Lean90秒、1CPU/1024MB。

访问[工作区](http://127.0.0.1:8103/dashboard)或
[已保存首题](http://127.0.0.1:8103/dashboard/run/run_d44ac65dbda220c5020399de4047f1b8)。
检查`/health`返回ok。13:13:43（Asia/Shanghai）已从停止状态启动，实际服务PID
1824、创建时间2026-11-16T05:13:43.2897092Z，源码8b248b3；进程身份以
artifacts/issue-183/delivery-current-process.json为准。前台用Ctrl+C停止；后台
停止前须核对PID和创建时间。
重启使用同一data目录，已有答案通过原深链读取，不重新提交历史题目；unknown不自动重发。

本轮delivery-current-observation.json：health=ok，两Job仍succeeded，原答案
可见且刷新后完整final_response/budget/request_attempts一致，写请求及页面错误
均为0；桌面和移动截图保存在同目录delivery-current-*.png。未新增模型调用。
配置SHA256为e00d8711ade0349e2d006cfcd0f12ceedf7ec2377fb4a76d5d95e47b8027025d。

## 历史入口（2026-11-15，非本轮当前配置）

日期2026-11-15；[阶段验收](../evals/faithful-service-183-20261115.md)。当前服务仅为阶段交付；#183/#168仍开放，不能称完整自主能力已通过。运行需要本机既有.env凭证、uv环境、Docker及已核验Python/Lean镜像、artifacts/issue-183/live02/配置/manifest/持久数据和已构建前端。运行产物按仓库规则不提交；本说明适用于当前机器，不是干净环境安装包。

在仓库根目录启动（端口已监听时先使用现有实例）：

```powershell
uv run --env-file .env python showcase_server.py --mode live --host 127.0.0.1 --port 8100 --faithful-config artifacts/issue-183/live02/service.json --data-dir artifacts/issue-183/live02/data
```

访问[工作区](http://127.0.0.1:8100/dashboard)；[已保存恒等式详情](http://127.0.0.1:8100/dashboard/run/run_20360dd11f279157e9e17a744d983ee9)。`/health`应返回status=ok。当前后台服务身份记录在artifacts/issue-183/delivery-process.json；日志为delivery.stdout.log、delivery.stderr.log。当前两个Job均已完成，缓存已明确停用；浏览器查看不重算。新题仍受原262144 token/1100秒及48/48/8限制，复杂规划可能预算不足。

前台启动用Ctrl+C停止。若使用当前后台实例，核对PID和创建时间后停止：

```powershell
$s = Get-Content artifacts/issue-183/delivery-process.json -Raw -Encoding utf8 | ConvertFrom-Json
$p = Get-Process -Id $s.pid -ErrorAction SilentlyContinue
if ($p -and $p.StartTime.ToUniversalTime().Ticks -eq ([DateTimeOffset]$s.created_at).UtcDateTime.Ticks) { Stop-Process -Id $s.pid }
```

恢复时使用同一启动命令及同一data目录。不要删除showcase.sqlite3、创建替代身份或重新提交历史题目来恢复答案。历史unknown不自动重发；需要复核时保持其原预算和预留。当前交付验证已实际从停止状态启动并只读恢复两个答案；不代表在途崩溃续跑或自然缓存命中通过。
