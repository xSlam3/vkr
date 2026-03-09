from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.chat import ChatMessageRole, ChatSession
from app.models.user import User
from app.repositories.chat_repo import ChatRepository


class ChatHistoryService:
    @staticmethod
    def _build_title(question: str) -> str:
        compact = " ".join((question or "").split()).strip()
        if len(compact) <= 60:
            return compact or "Новый чат"
        return compact[:57].rstrip() + "..."

    @staticmethod
    def list_sessions(db: Session, current_user: User) -> list[ChatSession]:
        return ChatRepository.list_sessions_for_user(db, current_user.id)

    @staticmethod
    def get_session(db: Session, current_user: User, session_id: str) -> ChatSession:
        session = ChatRepository.get_session_for_user(db, session_id, current_user.id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Чат не найден.")
        return session

    @staticmethod
    def get_messages(db: Session, current_user: User, session_id: str):
        session = ChatHistoryService.get_session(db, current_user, session_id)
        return ChatRepository.list_messages(db, session.id)

    @staticmethod
    def save_exchange(
        db: Session,
        current_user: User,
        *,
        question: str,
        answer: str,
        session_id: str | None = None,
    ) -> ChatSession:
        if session_id:
            session = ChatHistoryService.get_session(db, current_user, session_id)
        else:
            session = ChatRepository.create_session(db, current_user.id, ChatHistoryService._build_title(question))

        sort_order = ChatRepository.next_sort_order(db, session.id)
        ChatRepository.create_message(db, session.id, ChatMessageRole.user, question, sort_order)
        ChatRepository.create_message(db, session.id, ChatMessageRole.assistant, answer, sort_order + 1)
        ChatRepository.touch_session(db, session)
        return session
