# #183 当前机器阶段交付

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
