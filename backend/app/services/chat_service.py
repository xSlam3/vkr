from __future__ import annotations

from collections import OrderedDict

import httpx

from app.core.config import settings
from app.schemas.chat import ChatResponse, ChatSource
from app.services.vector_service import RetrievedChunk, VectorService


class ChatService:
    @staticmethod
    def _filter_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        min_score = settings.VECTOR_MIN_SCORE
        filtered: list[RetrievedChunk] = []
        for chunk in chunks:
            if chunk.score is None or chunk.score >= min_score:
                filtered.append(chunk)
        return filtered

    @staticmethod
    def _build_context(chunks: list[RetrievedChunk]) -> str:
        lines: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            title = chunk.title or "Без названия"
            lines.append(f"[Источник {idx}] {title}")
            lines.append(chunk.text)
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def _build_sources(chunks: list[RetrievedChunk]) -> list[ChatSource]:
        sources: OrderedDict[str, ChatSource] = OrderedDict()
        for chunk in chunks:
            if not chunk.article_id:
                continue
            existing = sources.get(chunk.article_id)
            if existing is None:
                sources[chunk.article_id] = ChatSource(
                    article_id=chunk.article_id,
                    title=chunk.title,
                    score=chunk.score,
                )
                continue
            if existing.score is None and chunk.score is not None:
                existing.score = chunk.score
            elif existing.score is not None and chunk.score is not None:
                existing.score = max(existing.score, chunk.score)
        return list(sources.values())

    @staticmethod
    def _fallback_answer(chunks: list[RetrievedChunk]) -> str:
        best = chunks[0].text.strip()
        return best if len(best) <= 1000 else best[:1000] + "..."

    @staticmethod
    def _call_llm(question: str, context: str) -> str | None:
        if not settings.CHAT_USE_LLM:
            return None
        if not settings.LLM_API_URL or not settings.LLM_MODEL:
            return None

        url = settings.LLM_API_URL.rstrip("/") + "/chat/completions"
        payload = {
            "model": settings.LLM_MODEL,
            "temperature": settings.LLM_TEMPERATURE,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты помощник для сотрудников ювелирного магазина. "
                        "Отвечай только по контексту и не выдумывай данные."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Контекст:\n"
                        f"{context}\n\n"
                        f"Вопрос: {question}"
                    ),
                },
            ],
        }

        headers = {"Content-Type": "application/json"}
        if settings.LLM_API_KEY:
            headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"

        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            return None

    @staticmethod
    def ask(question: str, top_k: int | None = None, category_id: str | None = None) -> ChatResponse:
        chunks = VectorService.search(
            query=question,
            top_k=top_k or settings.VECTOR_TOP_K,
            category_id=category_id,
        )
        filtered = ChatService._filter_chunks(chunks)

        if not filtered:
            return ChatResponse(
                answer="Не нашел релевантной информации в базе знаний.",
                sources=[],
                used_context=False,
            )

        context = ChatService._build_context(filtered)
        llm_answer = ChatService._call_llm(question, context)
        answer = llm_answer or ChatService._fallback_answer(filtered)

        return ChatResponse(
            answer=answer,
            sources=ChatService._build_sources(filtered),
            used_context=True,
        )
