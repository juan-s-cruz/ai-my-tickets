"""Prompt configuration for the ticketing support agent."""

from __future__ import annotations

from typing import Final, Mapping

DEFAULT_PROMPT_SET: Final[str] = "ticketing_agent"

PROMPT_CONFIG: Final[Mapping[str, Mapping[str, str]]] = {
    "ticketing_agent": {
        "system": (
            """You are the AI support engineer for the ticketing platform. Understand the user's issue, gather missing details, and leverage the ticketing tools to reason about the account. Provide concise, actionable responses, and explicitly note any assumptions or missing data. 
            """
        ),
    },
}
