"""Helper factories for modular sub-agents."""

from __future__ import annotations

import os

from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.runnables.base import Runnable
from langchain_openai import AzureChatOpenAI
from langgraph.graph import MessagesState, StateGraph, END, START
from langgraph.prebuilt import ToolNode, tools_condition

from src.config import AGENTS_CONFIG
from src.tool_factory import get_tool

__all__ = ["sub_agent"]


def sub_agent(agent_config: dict) -> Runnable:
    """Return a compiled LangGraph agent configured for a system prompt and tool."""
    sub_agent_conf = AGENTS_CONFIG.get(agent_config, {})
    prompt = sub_agent_conf.get("system")
    tool_names = sub_agent_conf.get("tools")
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

    tool_node: ToolNode | None = None
    tools = []
    for tool in tool_names:
        try:
            tool = get_tool(tool)
            tools.append(tool)
        except ValueError as exc:  # pragma: no cover - validation safeguard
            raise RuntimeError(
                f"Unable to resolve tool '{tool}' for sub agent"
            ) from exc
    if len(tools) > 0:
        tool_node = ToolNode(tools)
        llm = llm.bind_tools(tools)

    async def node(state: MessagesState) -> MessagesState:
        msgs = [SystemMessage(content=prompt), *state["messages"]]
        ai = await llm.ainvoke(msgs)
        return {"messages": ai}

    graph = StateGraph(MessagesState)
    graph.add_node("model", node)
    graph.add_edge(START, "model")

    if tool_node:
        graph.add_node("tools", tool_node)
        graph.add_conditional_edges(
            "model",
            tools_condition,
            {"tools": "tools", "__end__": END},
        )
        graph.add_edge("tools", "model")
    else:
        graph.add_edge("model", END)

    return graph.compile()
