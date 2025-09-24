"""Helper factories for modular sub-agents."""

from __future__ import annotations

import os

from langchain_core.messages import SystemMessage
from langchain_core.runnables.base import Runnable
from langchain_openai import AzureChatOpenAI
from langgraph.graph import MessagesState, StateGraph, END, START

from src.config import PROMPT_CONFIG

__all__ = ["sub_agent"]


def sub_agent(system_prompt: str) -> Runnable:
    """Return a compiled LangGraph agent configured for a specific system prompt."""
    prompt_config = PROMPT_CONFIG.get(system_prompt, {})
    prompt = prompt_config.get("system")
    if not prompt:
        raise RuntimeError("Unable to resolve system prompt for simple agent")

    deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_MINI")
    if not deployment:
        raise RuntimeError("AZURE_OPENAI_CHAT_DEPLOYMENT_MINI is not set")

    llm = AzureChatOpenAI(
        azure_deployment=deployment,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        streaming=True,
        temperature=0.0,
    )

    async def node(state: MessagesState) -> MessagesState:
        msgs = [SystemMessage(content=prompt), *state["messages"]]
        ai = await llm.ainvoke(msgs)
        return {"messages": ai}

    graph = StateGraph(MessagesState)
    graph.add_node("model", node)
    graph.add_edge(START, "model")
    graph.add_edge("model", END)
    return graph.compile()
