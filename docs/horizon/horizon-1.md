# Horizon 1: Agent Server assessment

FRAG currently embeds LangGraph in its FastAPI process. The graphs orchestrate Preview, Context Run, and Inference Run for Harness and RAG Lab. They use no checkpointer; independent one-time approvals and bounded pending Inference state remain in the host process. No LangSmith tracing is enabled.

LangGraph is a Python library, not a separate desktop application. The optional LangGraph Agent Server is a distinct deployment path. `langgraph dev` runs a local development server through the LangGraph CLI; `langgraph up` uses Docker. FRAG does not install or start either server today.

Consider Agent Server only if a tested requirement needs remotely managed runs, durable execution, or separately deployed graph APIs. Before any migration, demonstrate parity for source revision checks, exact outbound previews, two independent approvals, token expiry and replay rejection, model output and citation validation, plugin isolation, and a no-trace privacy boundary. Server persistence, authentication, and deployment would need their own reviewed design.

References: [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview), [local development and testing](https://docs.langchain.com/langsmith/local-dev-testing), [LangGraph CLI](https://docs.langchain.com/langsmith/cli).
