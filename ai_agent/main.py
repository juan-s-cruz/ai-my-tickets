"""FastAPI application that streams Azure OpenAI chat responses via SSE."""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.agent import stream_chat

app = FastAPI(title="Support Agent (SSE Streaming)")


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
