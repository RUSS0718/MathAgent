# #221 普通工作台题图实时验收

2026-11-20（北京时间），在源码 `725a137892edb387d037a718d1a1116fad115ead` 的生产构建上验收。Chromium 从 Flask `/dashboard` 点击「题图求解」，两次分别选择同一张[公开示例 PNG](../../showcase/frontend/deeptutor-preview/public/examples/linear-equation.png)。图中只有 $2x+3=11$。运行使用 `--mode live`、`SHOWCASE_VISION_ENABLED=1` 和独立数据目录。工作台构建产物 `dist/index.html` 的 SHA-256 为 `dd34ef15a4930f91bcc93f64ac7d994d17fc36360973799682a0899a4e51377d`。PNG 的 SHA-256 为 `e77b5a680ae7b4e4db7724aa215cbdb4577b33d1c2bee4277663b23c69604939`。

| 输入 | 会话 ID | Job ID | 完成时间（北京时间） | 普通工作台结果 |
| --- | --- | --- | --- | --- |
| 纯图，补充要求留空 | `session_53c200ef9dabfbf16472f308c2b22e9c` | `run_7a85625cfd50afc1cf4e7bad251c101a` | 00:54:07 | `image`，已读取题图，方程题，最终答复 $x=4$ |
| 同图，附「请手算，并把结果代回原方程检验。」 | `session_3d57feadde851ac196ab8e2170c64c1c` | `run_c6efbb0f8fe8dfa09596283614c745a8` | 00:54:45 | `text_image`，已读取题图，方程题，最终答复 $x=4$ |

浏览器与 Flask 访问日志均记录两次独立 `POST /api/agent/jobs`，状态均为 HTTP 202。独立数据库保留两个 Job，分别绑定到两个不同的会话和上传记录。普通会话 API 将原始输入与 Job 关联。两个附件摘要都匹配示例 PNG。两个 Job 均为 `succeeded`、`execution_mode=live`，各有五条 `intern-s2` HTTP 200 回执，依次为识图、规划、求解、续答和综合。纯图的一次工具调用成功。图文的一次工具调用超时，原 Job 续答后交付正确答案。页面的验证提示标为未验证。

首次浏览器驱动在提交成功后读取响应体时遇到导航竞态。使用原会话深链补取证据，两次均在页面终稿和同一 Job 的 answer API 确认 $x=4$。刷新后会话、唯一 Job 和屏幕答案均保持一致。补取未发出求解或上传请求，页面异常为零。修订后的驱动从会话读取身份，在开启题图的 fake Flask 上验证了 HTTP 201/202、附件绑定和 Job 绑定，并按预期在两条路径的 live 模式断言处失败。后端 `test_showcase_multimodal.py` 首轮 8/9，失败项的 `last_event_id` 在两次读取间由 5 增至 6。相同命令复跑 9/9。

本次证据覆盖这一张 PNG 的两种提交方式。此前多模态验收使用了其他源码版本，见[图文读题验收记录](showcase-multimodal-intake-20261119.md)。

## 复现和证据位置

使用已配置的本机 Intern 凭证，从仓库根目录启动。为一轮新验收选择尚未使用的数据目录。浏览器驱动会提交两次实时求解。

```powershell
$env:SHOWCASE_VISION_ENABLED = '1'
uv run --no-project python scripts/start_showcase.py web --mode live --port 8221 --data-dir artifacts/decision-evidence-221-repro/data
```

在另一终端执行。

```powershell
node showcase/frontend/deeptutor-preview/tests/decision-evidence-image-221.mjs artifacts/decision-evidence-221-repro/browser
```

同一运行仍可访问时，在命令末尾按纯图、图文的顺序提供两个会话 ID，可只读核对旧结果。为只读检查指定新的浏览器输出目录。

原运行目录为 `artifacts/decision-evidence-221/`。`live-ledger-summary.json` 保存脱敏的 Job、会话和模型回执状态。`browser/evidence.json` 保存首次浏览器提交计数和竞态结果。`readback/evidence.json` 与同目录的两张截图保存只读结果。`fake-driver/evidence.json` 保存修订后的离线捕获检查。
