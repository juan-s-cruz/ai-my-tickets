"""Factory helpers for LangChain tools used by the support agent."""

from __future__ import annotations

from typing import Literal

from langchain_core.tools import tool

__all__ = ["get_route_tools", "route"]


@tool("route")
def route(
    destination: Literal["endpoint_1_assistant", "endpoint_2_assistant"],
    reason: str = "",
) -> str:
    """Hand off to a specialized agent by returning the destination name."""
    return destination


def get_route_tools() -> list:
    """Return the collection of LangChain tools used by the support agent."""
    return [route]
