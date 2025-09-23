"""FastAPI application that streams Azure OpenAI chat responses via SSE."""

import logging
import os
import sys
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
import uvicorn

from src.logging_config import LOGGING_CONFIG
from src.agent import stream_chat

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Support Agent (SSE Streaming)", debug=True)


@app.get("/chat")
async def chat(
    message: str = Query(..., description="User message to send to the support agent")
) -> StreamingResponse:
    """Stream chat responses for the given request in SSE format.

    Args:
        message: Prompt text supplied via query parameter.

    Returns:
        StreamingResponse: FastAPI response that streams the SSE payload.

    Raises:
        HTTPException: Raised when the message content is missing or blank.
    """
    if not message or not message.strip():
        logger.error("No message was received by the endpoint.")
        raise HTTPException(status_code=400, detail="message is required")

    headers: dict[str, str] = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        stream_chat(message),
        media_type="text/event-stream",
        headers=headers,
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        reload=True,
        host="0.0.0.0",
        port=int(os.getenv("AGENT_PORT")),
        log_config=LOGGING_CONFIG,
    )
