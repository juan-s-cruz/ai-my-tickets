"""Factory helpers for LangChain tools used by the support agent."""

from __future__ import annotations

import json
import logging
from typing import Literal, Optional, Dict, Any
from src.config import MAX_ATTEMPTS, DEFAULT_TIMEOUT_S, BASE_URL
import httpx
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception_type,
    retry_if_result,
)
from langchain_core.tools import BaseTool, tool, StructuredTool

__all__ = ["get_route_tools", "get_tool", "route"]

logger = logging.getLogger(__name__)


# Models
class FetchInput(BaseModel):
    """Inputs accepted by the GET tool."""

    ticket_id: str = Field(
        ..., description="Resource identifier appended to the endpoint path."
    )
    # optional query params
    params: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Query parameters for the GET."
    )
    # optional headers
    headers: Optional[Dict[str, str]] = Field(
        default_factory=dict, description="Additional HTTP headers."
    )


class CreateTicketInput(BaseModel):
    title: str = Field(
        ..., min_length=3, max_length=200, description="Short human-readable subject"
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=20_000,
        description="Detailed issue text (markdown allowed)",
    )


# Helper functions
def _should_retry_on_response(resp: httpx.Response) -> bool:
    """Return True if this response should be retried."""
    return resp.status_code == 429 or 500 <= resp.status_code < 600


def _retry_decorator():
    return retry(
        # Retry on network errors…
        retry=(
            retry_if_exception_type(httpx.RequestError)
            # …or on HTTP responses that indicate transient failure.
            | retry_if_result(
                lambda r: isinstance(r, httpx.Response) and _should_retry_on_response(r)
            )
        ),
        wait=wait_exponential(multiplier=1.2, min=0, max=10.0),
        stop=stop_after_attempt(MAX_ATTEMPTS),
        reraise=True,
    )


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:2000]}


@_retry_decorator()
async def _create_ticket(title: str, description: str) -> Dict[str, Any]:
    payload = CreateTicketInput(title=title, description=description)
    body = {"title": payload.title.strip(), "description": payload.description}
    headers = {}
    headers.setdefault("Accept", "application/json")
    logger.info(headers)

    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT_S, follow_redirects=True
    ) as client:
        r = await client.post(f"{BASE_URL}", json=body, headers=headers)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            # If server returns 409 for duplicate idempotency, treat as success and return body
            if r.status_code == 409:
                return _safe_json(r)
            # Non-retryable 4xx will bubble up; tenacity will not retry them
            raise
        return _safe_json(r)  # expected to be the created ticket as a dict


# Tool definitions
@tool("route")
def route(
    destination: Literal["get_endpoint_assistant", "create_endpoint_assistant"],
    reason: str = "",
) -> str:
    """Hand off to a specialized agent by returning the destination name."""
    return destination


@tool("get_tickets", args_schema=FetchInput)
@_retry_decorator()
async def get_tickets(
    ticket_id: str, params: Dict[str, Any] = None, headers: Dict[str, str] = None
) -> Dict[str, Any]:
    """
    Perform a GET to the ticket system to get current tickets in the system.
    Ths tool will retr on 5xx/429/network errors and return parsed JSON plus status/meta.

    Args:
        ticket_id: argument is used to identify the tickets, leave empty
    """
    params = params or {}
    headers = headers or {}
    # you can set a default Accept header safely
    headers.setdefault("Accept", "application/json")

    url = f"{str(BASE_URL).rstrip('/')}/{ticket_id}"
    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT_S, follow_redirects=True
    ) as client:
        resp = await client.get(url, params=params, headers=headers)

    # allows the retry_if_result condition above to trigger retries on 5xx/429.
    if _should_retry_on_response(resp):
        return resp

    # Raise for non-OK statuses that we don't retry (e.g., 4xx not 429).
    resp.raise_for_status()

    # Parse JSON safely; if the API returns non-JSON, this will raise.
    try:
        data = resp.json()
    except json.JSONDecodeError as e:
        # Provide a helpful error payload to the agent
        raise ValueError(
            f"Endpoint returned non-JSON payload (status {resp.status_code})."
        ) from e

    # Return a clean, tool-friendly dict
    return {
        "ok": True,
        "status": resp.status_code,
        "url": str(resp.request.url),
        "data": data,
    }


create_ticket_tool = StructuredTool.from_function(
    name="create_ticket",
    description=(
        "Create a new support ticket. "
        "Use this tool when the user wants to open/submit/log an issue."
    ),
    args_schema=CreateTicketInput,
    coroutine=_create_ticket,  # for async version
    return_direct=False,
)

# Get tool functions


def get_route_tools() -> list:
    """Return the collection of LangChain tools used by the main agent."""
    return [route]


def get_sub_agent_tools() -> list:
    """Return the collection of LangChain tools used by the support agent."""
    # TODO: Add tools for sub agents
    return [get_tickets, create_ticket_tool]


def get_tool(tool_name: str) -> BaseTool:
    """Return a single LangChain tool by name."""
    for tool_obj in get_sub_agent_tools():
        if tool_obj.name == tool_name:
            return tool_obj
    raise ValueError(f"Tool '{tool_name}' is not registered")
