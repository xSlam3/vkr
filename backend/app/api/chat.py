from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/", response_model=ChatResponse)
def ask_chat(
    payload: ChatRequest,
    _: User = Depends(get_current_user),
):
    return ChatService.ask(
        question=payload.question,
        top_k=payload.top_k,
        category_id=payload.category_id,
    )
