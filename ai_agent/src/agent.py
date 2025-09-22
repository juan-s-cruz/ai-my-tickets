"""LangChain-powered support agent helpers for streaming SSE responses."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Mapping
from typing import Any

from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables.base import Runnable
from langchain_openai import AzureChatOpenAI

RETRY_HINT: bytes = b"retry: 5000\n\n"


def build_chain() -> Runnable:
    """Build the LangChain pipeline that powers the support agent.

    Returns:
        Runnable: Runnable chain that streams LLM responses as strings.
    """
    system = (
        "You are a helpful support copilot. Be concise and factual. "
        "When you don't know, say so. Keep answers suitable for a technical reader."
    )
    prompt = ChatPromptTemplate.from_messages(
        [("system", system), ("human", "{input}")]
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
    return chain


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
    chain: Runnable = build_chain()

    yield RETRY_HINT

    try:
        async for chunk in chain.astream({"input": user_msg}):
            yield sse_event("token", {"delta": chunk})
            await asyncio.sleep(0)
        yield sse_event("end", {"ok": True})
    except Exception as exc:  # pragma: no cover - runtime safeguard
        yield sse_event("error", {"message": str(exc)})
