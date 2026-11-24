# ModelPort 与首个真实 Provider

固定仓库源码：`9d5e7afde27ec8623ab18c010f8c4d2adad394b6`。文档核对：2026-11-24。本次无模型调用、依赖安装或账号可用性验证。

## 源码与接口

- [ModelPort](https://github.com/RUSS0718/RiCL/blob/9d5e7afde27ec8623ab18c010f8c4d2adad394b6/showcase/solver_harness/explore.py) 仅要求 `complete(request)`；[InternModelPort](https://github.com/RUSS0718/RiCL/blob/9d5e7afde27ec8623ab18c010f8c4d2adad394b6/showcase/solver_harness/intern_port.py) 同时做角色格式处理与运行记录，不是任意端点的通用传输。
- [响应归一化](https://github.com/RUSS0718/RiCL/blob/9d5e7afde27ec8623ab18c010f8c4d2adad394b6/llm_response.py) 提供请求/返回模型、调用尝试、token 和请求标识的已有结构；`cost=None` 不代表调用免费。
- [直接依赖](https://github.com/RUSS0718/RiCL/blob/9d5e7afde27ec8623ab18c010f8c4d2adad394b6/pyproject.toml) 中既无 LiteLLM 也无 OpenAI SDK。锁文件里的传递依赖不构成研究运行环境的安装合同。
- [DeepSeek 请求/响应](https://api-docs.deepseek.com/api/create-chat-completion/) 与 [thinking 指南](https://api-docs.deepseek.com/guides/thinking_mode/) 说明请求模型、服务端返回标识和 usage 可分别记录；thinking 模式不使用 temperature，工具续轮有上下文要求。由适配层处理，不把差异泄露给搜索或调控算法。

## 候选方案与建议

1. 直接复用旧 Intern port：既有接口可供参考，但导入产品运行和角色格式约束，不是去耦的默认选择。
2. 保留窄调用约定，给首个实际选中的 Provider 实现必要参数/回包映射，复用现有计量语义；成熟客户端可用时不重写 HTTP 和流解析。建议从这里开始。
3. [LiteLLM SDK/Router](https://docs.litellm.ai/docs/routing) 为多供应商提供统一调用；其 Router 可以重试、切换部署。首版只有一个 Provider，没有理由先引入路由。需要第二个 Provider 时再比较专用 SDK 与统一库的直接依赖、锁文件差异、安装和行为；不假定已测出安装体积或时延。

## 最小实测与账本

显式指定端点与模型，设置本次调用上限，先做一次获准的真实 smoke；成功拿到可核验返回及用量才称此组合可调用。失败则停止并记录，不自动换模型或尝试另一个提供商。DeepSeek Flash 可作为首选候选，不是静态盘点得出的环境事实。

每次实际尝试保存请求模型、返回模型/版本（未披露的后端版本为 unknown）、可用的请求标识、thinking/工具配置摘要、终态、实际 token、缺失字段及计量来源。估算费用与服务端账单区分，注明币种和费率版本或记 unknown；重试与工具/干预不另开实验预算。不要保存密钥、完整提示或模型私有推理。此方案仍待 Runtime 合同确认。