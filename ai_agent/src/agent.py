"""LangChain-powered support agent helpers for streaming SSE responses."""

from __future__ import annotations


import asyncio
import json
import os
import logging
from collections.abc import AsyncIterator, Mapping
from typing import Any

from src.prompt_config import DEFAULT_PROMPT_SET, PROMPT_CONFIG

from langchain.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables.base import Runnable
from langchain_openai import AzureChatOpenAI
from langgraph.graph import StateGraph, MessagesState, END

logger = logging.getLogger(__name__)

RETRY_HINT: bytes = b"retry: 5000\n\n"

# Cache the graph after first use with this global variable
_GRAPH: Runnable | None = None


def build_chain() -> Runnable:
    """Build the LangGraph workflow that powers the support agent.

    Returns:
        Runnable: Compiled LangGraph workflow for invoking the chat model.
    """
    prompt_config: Mapping[str, str] | None = PROMPT_CONFIG.get(DEFAULT_PROMPT_SET)
    if not prompt_config:
        raise RuntimeError(
            f"Prompt configuration '{DEFAULT_PROMPT_SET}' is not defined"
        )

    system_prompt = prompt_config.get("system")
    if not system_prompt:
        raise RuntimeError(
            f"Prompt configuration '{DEFAULT_PROMPT_SET}' is missing a system prompt"
        )

    prompt = ChatPromptTemplate.from_messages(
        [("system", system_prompt), ("human", "{input}")]
    )

    deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
    if not deployment:
        raise RuntimeError("AZURE_OPENAI_CHAT_DEPLOYMENT is not set")

    llm = AzureChatOpenAI(
        azure_deployment=deployment,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        streaming=True,
        temperature=0.0,
    )
    chain: Runnable = prompt | llm | StrOutputParser()

    graph = StateGraph(MessagesState)

    async def run_chat_model(state: MessagesState) -> MessagesState:
        messages: list[BaseMessage] = state.get("messages", [])
        if not messages:
            raise ValueError("Graph state is missing 'messages'")

        last_message = messages[-1]
        if not isinstance(last_message, HumanMessage):
            raise TypeError("Expected last message to be a HumanMessage")

        response = await chain.ainvoke({"input": last_message.content})
        return {"messages": [AIMessage(content=response)]}

    graph.add_node("chat_model", run_chat_model)
    graph.set_entry_point("chat_model")
    graph.add_edge("chat_model", END)

    return graph.compile()


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
    graph: Runnable = get_graph()

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
