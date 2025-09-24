"""Main agent definition, serves and entry point and router"""

import os
from collections.abc import Mapping

from src.config import DEFAULT_PROMPT_SET, AGENTS_CONFIG
from langchain.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import BaseMessage
from langchain_core.runnables.base import Runnable
from langgraph.graph import StateGraph, MessagesState


from src.tool_factory import get_route_tools

_PROMPTS: Mapping[str, str] | None = None


def _get_prompts() -> Mapping[str, str]:
    """Load and validate the prompt set when first needed."""
    global _PROMPTS
    if _PROMPTS is None:
        prompts = AGENTS_CONFIG.get(DEFAULT_PROMPT_SET, {})
        if not prompts:
            raise RuntimeError(
                f"Prompt configuration '{DEFAULT_PROMPT_SET}' is not defined"
            )
        if "system" not in prompts:
            raise RuntimeError(
                f"Prompt configuration '{DEFAULT_PROMPT_SET}' is missing a system prompt"
            )
        _PROMPTS = prompts
    return _PROMPTS


prompts = _get_prompts()
prompt = ChatPromptTemplate.from_messages(
    [("system", prompts["system"]), ("human", "{input}")]
)

deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
if not deployment:
    raise RuntimeError("AZURE_OPENAI_CHAT_DEPLOYMENT is not set")

routing_tools = get_route_tools()
llm = AzureChatOpenAI(
    azure_deployment=deployment,
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    streaming=True,
    temperature=0.0,
).bind_tools(routing_tools)
chain: Runnable = prompt | llm


async def run_chat_model(state: MessagesState) -> MessagesState:
    messages: list[BaseMessage] = state.get("messages", [])
    if not messages:
        raise ValueError("Graph state is missing 'messages'")

    last_message = messages[-1]

    response = await chain.ainvoke({"input": last_message.content})
    if not isinstance(response, BaseMessage):
        raise TypeError("LLM must return a message")
    return {"messages": response}
