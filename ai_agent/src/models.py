"""Pydantic based models required for the tool inputs"""

from typing import Literal, Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator


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


RESOLUTION = Literal["OPEN", "RESOLVED", "CLOSED"]


class TicketsFilterInput(BaseModel):
    """Filter Tickets using DRF filters."""

    search: Optional[str] = Field(
        default=None, description="Full-text search over searchable fields."
    )
    id: Optional[List[int]] = Field(
        default=None, description="Exact id(s). If many, will use __in."
    )
    resolution_status: Optional[List[RESOLUTION]] = Field(
        default=None, description="One or more statuses; will use __in when multiple."
    )
    page: Optional[int] = Field(default=1, ge=1)
    page_size: Optional[int] = Field(
        default=None, ge=1, le=200, description="If your DRF pagination supports it."
    )
    fetch_all: bool = Field(
        default=False, description="Follow DRF pagination to fetch all pages."
    )
    timeout: float = Field(default=10.0, gt=0, description="HTTP timeout in seconds.")

    @field_validator("resolution_status")
    def dedup_status(cls, v):
        return sorted(set(v)) if v else v
