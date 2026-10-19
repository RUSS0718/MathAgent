# Frontend source record

This directory includes a MathAgent-owned Vue/TypeScript workspace derived from the MIT-licensed CausalAgent `chat-frontend` source at commit `eff6fd1bb603895f09f1a5bac35e7c5bd476cc7d`.

The copied MIT license is preserved in `LICENSE.CausalAgent`. The v0.2 visual redesign also ports generic workspace interaction patterns from the MIT-licensed LangChain Agent Chat UI project at reference commit `7a503412aeeb4534a24b04bd97b618ee3871821e`; its license is preserved in `LICENSE.AgentChatUI`. MathAgent owns the product integration and maintains the session, message, Job, report, settings, Zod parsing, and route seams here. Causal graph, RAG, search, administrator, and login/register surfaces were removed. Neither upstream repository is a v0.2 runtime dependency.
