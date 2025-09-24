"""Factory helpers for LangChain tools used by the support agent."""

from __future__ import annotations

from typing import Literal

from langchain_core.tools import BaseTool, tool

__all__ = ["get_route_tools", "get_tool", "route"]


@tool("route")
def route(
    destination: Literal["endpoint_1_assistant", "endpoint_2_assistant"],
    reason: str = "",
) -> str:
    """Hand off to a specialized agent by returning the destination name."""
    return destination


def get_route_tools() -> list:
    """Return the collection of LangChain tools used by the main agent."""
    return [route]


def get_sub_agent_tools() -> list:
    """Return the collection of LangChain tools used by the support agent."""
    # TODO: Add tools for sub agents
    return []


def get_tool(tool_name: str) -> BaseTool:
    """Return a single LangChain tool by name."""
    for tool_obj in get_sub_agent_tools():
        if tool_obj.name == tool_name:
            return tool_obj
    raise ValueError(f"Tool '{tool_name}' is not registered")
