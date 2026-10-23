# SP-05 连续 Challenge 产品验收

日期：2026-10-23。本票[#61](https://github.com/RUSS0718/MathAgent/issues/61)，父规格[#56](https://github.com/RUSS0718/MathAgent/issues/56)；见[验收合同](../engineering/star-product-sp05-contract.md)。本记录证明工程控制行为，不证明数学正确率或真实Intern效果。

## 同一 Run 证据链

`tests/test_star_product_challenge.py`从认证Job HTTP入口穿过真实STAR controller、InternModelAdapter、共享S3账本和持久Solver状态。仅HTTP传输使用有限fault_injection回复。Job、Run、SSE、报告和Evidence同Run关联。没有live调用；不是replay。离线浏览器使用合成SSE，单独证明展示行为。

| 触发 → 决策 | 实际动作 → 持久状态 → 用户结果 |
| --- | --- |
| 连续三轮异议，第三轮ACCEPT | 三对Reasoner/Verifier逐轮携带双方历史、当前异议与最新状态；SSE仅一次接受；最终生成经新整题审查，Job成功，Evidence保留同Run timeline。 |
| 三轮仍有异议 → Meta ABORT | 最后一次请求为Meta；challenge_stalemate记录轮数原因，meta_decided记录ABORT；Solver partial_aborted、Job失败。 |
| 三轮仍有异议 → Meta CONTINUE | 新Reasoner/Verifier身份带原三轮历史和异议；通过双Gate才接受，CONTINUE本身不接受步骤。 |
| CONTINUE后再CHALLENGE | 只有三轮Challenge和一次Meta；继续后的审查拒绝后不再派发；challenge_escalation_stopped记录Meta次数上限，Job失败。 |
| Meta伪造ACCEPT | schema拒绝，call audit置interrupted，Job失败、验证unknown；无接受事件及后续请求，不自动重试。 |
| Meta TRACE_BACK到不存在步骤 | schema结构合法但目标非法；meta_invalid后partial_aborted，无接受及后续请求。 |

公开事件展示异议摘要、角色来源、提供方输入/输出/总tokens和分类升级原因。公共测试对隐藏argument和original_problem做泄漏断言。浏览器在320、768、1024、1440宽度检查摘要、无横向溢出、无私有prompt/claim/argument和Axe违规。异议字段为模型生成公开摘要；脱敏和长度限制不能证明模型永远不会在该字段复述其他输入。

## 实际检查

| 检查 | 结果 |
| --- | --- |
| `uv run pytest tests/test_star_product_challenge.py tests/test_solver_harness_challenge.py tests/test_solver_harness_meta.py -q` | PASS，22项，14.95秒；公共Challenge场景6项，包含状态phase与单调revision断言。 |
| 修改Python文件 `uv run ruff check`、`git diff --check` | PASS |
| `npm run check` | PASS，依赖合同、类型、13项单元测试及构建。 |
| `npm ci --no-audit --no-fund`、`npm audit --audit-level=high` | PASS，0 vulnerabilities。 |
| `npm run test:browser -- tests/browser/star-decisions.spec.ts --workers=1` | PASS，5项，8.8秒；四视口和原始步骤ID反例，Axe违规0、页面console错误/警告0。Node运行器另有NO_COLOR/FORCE_COLOR配置警告。 |
| `uv run python scripts/check.py --offline` | PASS，404项，323.209秒，9项跳过；repository_check=PASS。 |
| `uv run python scripts/check_showcase_release.py` | PASS，在offline结束后顺序执行；showcase_release=PASS。 |
| 进程内最小mutation探针 | PASS：清空实际出站Challenge历史、将产品3轮限制改为4轮，两个公共验收均按预期失败；mutation_sensitivity=PASS。探针只在独立进程monkeypatch，未改持久源码。 |
| `git diff -- BASELINE.json user_agent.py implementations requirements.txt` | 空差异。 |

日志及临时mutation探针保留在忽略的`artifacts/star-sp05/`；截图保留在忽略的`artifacts/ui-unification/browser/star-decisions-*/`。提交前执行`git merge --no-edit showcase-star-product`确认已包含集成tip `985b337`（Already up to date）。

## 边界与下一切片

本票使用三轮上限触发有界Meta；不声称在耗尽的S3 deadline外仍可新增Meta调用。S3 deadline优先停止后续派发，沿用SP-03控制合同。合法Trace-Back执行与重规划由SP-06验收，记忆/MetaGuidance由SP-07、安全恢复由SP-08、最终文本绑定由SP-10负责。完整reference仍拒绝启动，默认官方入口和预算不变。真实Intern批次、最终上游逐项复核及综合反旁路验收仍属SP-13，不能用本票fault_injection冒充通过。
