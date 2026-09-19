"""POST /api/chat."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .schemas import ChatRequest
from .service import handle_chat

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(body: ChatRequest) -> dict[str, Any]:
    return await handle_chat(body.message)
