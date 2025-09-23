"""LangChain-powered support agent helpers for streaming SSE responses."""

from __future__ import annotations


import asyncio
import json
import os
import logging
from collections.abc import AsyncIterator, Mapping
from typing import Any, Literal

from src.prompt_config import DEFAULT_PROMPT_SET, PROMPT_CONFIG

from langchain.prompts import ChatPromptTemplate
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables.base import Runnable
from langchain_openai import AzureChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode, tools_condition

logger = logging.getLogger(__name__)

RETRY_HINT: bytes = b"retry: 5000\n\n"

# Cache the graph after first use with this global variable
_GRAPH: Runnable | None = None
PROMPTS: Mapping[str, str] = PROMPT_CONFIG.get(DEFAULT_PROMPT_SET, {})
if not PROMPTS:
    raise RuntimeError(f"Prompt configuration '{DEFAULT_PROMPT_SET}' is not defined")

if "system" not in PROMPTS:
    raise RuntimeError(
        f"Prompt configuration '{DEFAULT_PROMPT_SET}' is missing a system prompt"
    )


def simple_agent(system_prompt: str) -> Runnable:
    prompt = PROMPT_CONFIG.get(system_prompt).get("system")
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

    g = StateGraph(MessagesState)
    g.add_node("model", node)
    g.add_edge(START, "model")
    g.add_edge("model", END)
    return g.compile()


@tool("route")
def route(
    destination: Literal["endpoint_1_assistant", "endpoint_2_assistant"],
    reason: str = "",
) -> str:
    """
    Hand off to a specialized agent. Set `destination` to one of:
        "endpoint_1_assistant"
    """
    return destination


def after_tools(state: MessagesState) -> str:
    """
    If the last ToolMessage was `route`, jump to that agent.
    Otherwise, go back to the assistant to continue the loop.
    """
    last = state["messages"][-1]
    if isinstance(last, ToolMessage) and getattr(last, "name", "") == "route":
        dest = str(last.content).strip().lower()
        if dest == "endpoint_1_assistant":
            return "endpoint_1_assist"
    return "endpoint_1_assist"


def build_chain() -> Runnable:
    """Build the LangGraph workflow that powers the support agent.

    Returns:
        Runnable: Compiled LangGraph workflow for invoking the chat model.
    """
    prompt = ChatPromptTemplate.from_messages(
        [("system", PROMPTS["system"]), ("human", "{input}")]
    )

    deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
    if not deployment:
        raise RuntimeError("AZURE_OPENAI_CHAT_DEPLOYMENT is not set")

    routing_tools = [route]
    llm = AzureChatOpenAI(
        azure_deployment=deployment,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        streaming=True,
        temperature=0.0,
    ).bind_tools(routing_tools)
    chain: Runnable = prompt | llm

    graph = StateGraph(MessagesState)

    async def run_chat_model(state: MessagesState) -> MessagesState:
        messages: list[BaseMessage] = state.get("messages", [])
        if not messages:
            raise ValueError("Graph state is missing 'messages'")

        last_message = messages[-1]
        if not isinstance(last_message, HumanMessage):
            raise TypeError(
                "Expected last message to be a HumanMessage but received, %s",
                type(last_message),
            )

        response = await chain.ainvoke({"input": last_message.content})
        if not isinstance(response, BaseMessage):
            raise TypeError("LLM must return a message")
        return {"messages": response}

    tool_node = ToolNode(routing_tools)

    endpoint_1_agent = simple_agent("endpoint_1_config")

    graph.add_node("ticket_assistant", run_chat_model)
    graph.add_node("tools", tool_node)
    graph.add_node("endpoint_1_node", endpoint_1_agent)

    # I put the graph together
    graph.set_entry_point("ticket_assistant")

    graph.add_conditional_edges(
        "ticket_assistant",
        tools_condition,
        {"tools": "tools", "__end__": END},
    )

    graph.add_conditional_edges(
        "tools",
        after_tools,
        {
            # "assistant": "ticket_assistant",
            "endpoint_1_assist": "endpoint_1_node",
            # "endpoint_1_assist": "endpoint_2_node",
        },
    )

    graph.add_edge("endpoint_1_node", END)
    compiled_graph = graph.compile()
    with open("graph_ascii.txt", "w") as f:
        f.write(compiled_graph.get_graph().draw_ascii())
        logging.info("Saved graph diagram.")

    return compiled_graph


def get_graph() -> Runnable:
    """Return a cached instance of the compiled LangGraph workflow."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_chain()
    return _GRAPH


def sse_event(event: str | None, data: Mapping[str, Any] | str) -> bytes:
    """Format a server-sent event payload.

    Args:
        event: Optional SSE event label to include with the frame.
        data: Payload to stream to the client; serialized when not already a string.

    Returns:
        bytes: SSE frame encoded as UTF-8 text.
    """
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    lines: list[str] = []
    if event:
        lines.append(f"event: {event}")
    for line in str(payload).splitlines() or [""]:
        lines.append(f"data: {line}")
    lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")


async def stream_chat(user_msg: str) -> AsyncIterator[bytes]:
    """Stream SSE frames that deliver tokens for the supplied message.

    Args:
        user_msg: Prompt text sent by the client.

    Yields:
        bytes: Encoded SSE frames containing retry hints, tokens, or status markers.
    """
    graph = get_graph()  # compiled LangGraph Runnable

    yield RETRY_HINT

    try:
        result: Mapping[str, Any] = await graph.ainvoke(
            {"messages": [HumanMessage(content=user_msg)]}
        )
        output = ""
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage):
                output = msg.content
                break
        if output:
            yield sse_event("token", {"delta": output})
        await asyncio.sleep(0)
        yield sse_event("end", {"ok": True})
    except Exception as exc:  # pragma: no cover - runtime safeguard
        yield sse_event("error", {"message": str(exc)})
