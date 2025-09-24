"""Factory helpers for LangChain tools used by the support agent."""

from __future__ import annotations

import json
import logging
from typing import Literal, Optional, Dict, Any, List
from src.config import MAX_ATTEMPTS, DEFAULT_TIMEOUT_S, BASE_URL
import httpx

from tenacity import (
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception_type,
    retry_if_result,
)
from langchain_core.tools import BaseTool, tool, StructuredTool

from src.models import RESOLUTION, FetchInput, CreateTicketInput, TicketsFilterInput

__all__ = [
    "get_route_tools",
    "get_tool",
    "router",
    "get_sub_agent_tools",
    "get_route_tools",
]

logger = logging.getLogger(__name__)


# ======================= Helper functions =====================================
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


@_retry_decorator()
async def _get_json(
    client: httpx.AsyncClient, url: str, params: Dict[str, Any], timeout: float
) -> Dict[str, Any]:
    resp = await client.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _build_params(inp: TicketsFilterInput) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if inp.search:
        params["search"] = inp.search
    if inp.id:
        if len(inp.id) == 1:
            params["id"] = str(inp.id[0])
        else:
            params["id__in"] = ",".join(str(x) for x in inp.id)
    if inp.resolution_status:
        if len(inp.resolution_status) == 1:
            params["resolution_status"] = inp.resolution_status[0]
        else:
            params["resolution_status__in"] = ",".join(inp.resolution_status)
    if inp.page is not None:
        params["page"] = inp.page
    if inp.page_size is not None:
        params["page_size"] = inp.page_size
    return params


@_retry_decorator()
async def _list_tickets_impl(
    *,
    search: str = None,
    id: List[int] = None,
    resolution_status: List[RESOLUTION] = None,
    page: int = 1,
    page_size: int = None,
    fetch_all: bool = False,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    inp = TicketsFilterInput(
        search=search,
        id=id,
        resolution_status=resolution_status,
        page=page,
        page_size=page_size,
        fetch_all=fetch_all,
        timeout=timeout,
    )
    params = _build_params(inp)
    async with httpx.AsyncClient(
        base_url=BASE_URL, headers={"Accept": "application/json"}
    ) as client:
        data = await _get_json(client, BASE_URL, params, inp.timeout)

        # DRF pagination shape: {"count": int, "next": url|null, "previous": url|null, "results": [...]}
        if (
            inp.fetch_all
            and isinstance(data, dict)
            and "results" in data
            and data.get("next")
        ):
            all_results = list(data["results"])
            next_url = data["next"]
            # Follow next links; keep same timeout + retry policy
            while next_url:
                page = await _get_json(client, next_url, params={}, timeout=inp.timeout)
                all_results.extend(page.get("results", []))
                next_url = page.get("next")
            # Return in DRF-like shape for consistency
            return {
                "count": len(all_results),
                "next": None,
                "previous": None,
                "results": all_results,
            }
        return data


@_retry_decorator()
async def _patch(
    client: httpx.AsyncClient,
    url: str,
    json_payload: Dict[str, Any],
) -> httpx.Response:
    return await client.patch(url, json=json_payload)


# ========================== Tool definitions ==================================
@tool("route")
def router(
    destination: Literal[
        "get_endpoint_assistant",
        "create_endpoint_assistant",
        "update_endpoint_assistant",
    ],
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


create_ticket = StructuredTool.from_function(
    name="create_ticket",
    description=(
        "Create a new support ticket. "
        "Use this tool when the user wants to open/submit/log an issue."
    ),
    args_schema=CreateTicketInput,
    coroutine=_create_ticket,  # for async version
    return_direct=False,
)

get_filtered_tickets: StructuredTool = StructuredTool.from_function(
    name="get_filtered_tickets",
    description=(
        "List tickets using DRF filters. Supports 'search', 'id' (single or list), "
        "'resolution_status' (single or list), pagination (page/page_size), and fetch_all."
    ),
    args_schema=TicketsFilterInput,
    coroutine=_list_tickets_impl,
)


@tool("update_ticket", return_direct=False)
async def update_ticket(
    ticket_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    resolution_status: Optional[str] = None,
    base_url: str = BASE_URL,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """
    PATCH-update an existing ticket.

    Updatable fields: title, description, resolution_status.

    Args:
        ticket_id: Ticket identifier.
        title: Optional new title.
        description: Optional new description.
        resolution_status: Optional new resolution status.
        base_url: Ticket system base URL (no trailing slash).
        timeout_s: HTTP timeout in seconds.

    Returns:
        Parsed JSON (dict) on success. Raises for non-2xx.
    """
    if not (title or description or resolution_status):
        raise ValueError(
            "Provide at least one of `title`, `description`, or `resolution_status` for PATCH."
        )

    payload: Dict[str, Any] = {}
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    if resolution_status is not None:
        payload["resolution_status"] = resolution_status

    url = f"{base_url.rstrip('/')}/{ticket_id}/"

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await _patch(client, url, payload)

    if 500 <= resp.status_code < 600:
        resp.raise_for_status()

    if 400 <= resp.status_code < 500:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise httpx.HTTPStatusError(
            f"PATCH {url} failed with {resp.status_code}: {detail}",
            request=resp.request,
            response=resp,
        )

    return resp.json()


# ======================= Get tool functions ===================================


def get_route_tools() -> list:
    """Return the collection of LangChain tools used by the main agent."""
    return [router]


def get_sub_agent_tools() -> list:
    """Return the collection of LangChain tools used by the support agent."""
    # TODO: Add tools for sub agents
    return [get_tickets, create_ticket, get_filtered_tickets, update_ticket]


def get_tool(tool_name: str) -> BaseTool:
    """Return a single LangChain tool by name."""
    for tool_obj in get_sub_agent_tools():
        if tool_obj.name == tool_name:
            return tool_obj
    raise ValueError(f"Tool '{tool_name}' is not registered")
