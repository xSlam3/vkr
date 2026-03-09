from sqlalchemy.orm import Session

from app.models.chat import ChatMessage, ChatSession


class ChatRepository:
    @staticmethod
    def list_sessions_for_user(db: Session, user_id: str) -> list[ChatSession]:
        return (
            db.query(ChatSession)
            .filter(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
            .all()
        )

    @staticmethod
    def get_session_for_user(db: Session, session_id: str, user_id: str) -> ChatSession | None:
        return (
            db.query(ChatSession)
            .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
            .first()
        )

    @staticmethod
    def create_session(db: Session, user_id: str, title: str) -> ChatSession:
        session = ChatSession(user_id=user_id, title=title)
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def list_messages(db: Session, session_id: str) -> list[ChatMessage]:
        return (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.sort_order.asc(), ChatMessage.created_at.asc())
            .all()
        )

    @staticmethod
    def next_sort_order(db: Session, session_id: str) -> int:
        last = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.sort_order.desc())
            .first()
        )
        return (last.sort_order + 1) if last else 1

    @staticmethod
    def create_message(db: Session, session_id: str, role, content: str, sort_order: int) -> ChatMessage:
        message = ChatMessage(session_id=session_id, role=role, content=content, sort_order=sort_order)
        db.add(message)
        db.commit()
        db.refresh(message)
        return message

    @staticmethod
    def touch_session(db: Session, session: ChatSession) -> ChatSession:
        db.add(session)
        db.commit()
        db.refresh(session)
        return session
