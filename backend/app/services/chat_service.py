from __future__ import annotations

from collections import OrderedDict
import html
import re

import httpx

from app.core.config import settings
from app.db.session import SessionLocal
from app.schemas.chat import ChatResponse, ChatSource
from app.repositories.knowledge_repo import KnowledgeRepository
from app.services.vector_service import RetrievedChunk, VectorService


class ChatService:
    @staticmethod
    def _normalize_text(value: str) -> str:
        plain = re.sub(r"<[^>]+>", " ", value or "")
        plain = html.unescape(plain)
        return re.sub(r"\s+", " ", plain).strip().lower()

    @staticmethod
    def _extract_terms(question: str) -> list[str]:
        words = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", (question or "").lower())
        unique_terms: list[str] = []
        for word in words:
            if len(word) < 4:
                continue
            candidates = [word]
            if len(word) >= 5:
                candidates.append(word[:5])
            if len(word) >= 4:
                candidates.append(word[:4])
            for candidate in candidates:
                if candidate not in unique_terms:
                    unique_terms.append(candidate)
        return unique_terms

    @staticmethod
    def _keyword_fallback(question: str, top_k: int | None = None, category_id: str | None = None) -> list[RetrievedChunk]:
        terms = ChatService._extract_terms(question)
        if not terms:
            return []

        db = SessionLocal()
        try:
            articles = KnowledgeRepository.list_articles(db, category_id=category_id)
        finally:
            db.close()

        matches: list[tuple[int, RetrievedChunk]] = []
        for article in articles:
            title = ChatService._normalize_text(article.title)
            text = ChatService._normalize_text(article.text_content)
            title_tokens = re.findall(r"[a-zа-яё0-9]+", title)
            text_tokens = re.findall(r"[a-zа-яё0-9]+", text)

            score = 0
            for term in terms:
                if term in title or any(token.startswith(term) for token in title_tokens):
                    score += 3
                if term in text or any(token.startswith(term) for token in text_tokens):
                    score += 1

            if score <= 0:
                continue

            matches.append(
                (
                    score,
                    RetrievedChunk(
                        article_id=article.id,
                        title=article.title,
                        category_id=article.category_id,
                        chunk_index=0,
                        text=ChatService._normalize_text(article.text_content),
                        score=min(score / max(len(terms) * 3, 1), 1.0),
                    ),
                )
            )

        matches.sort(key=lambda item: item[0], reverse=True)
        limit = max(1, top_k or settings.VECTOR_TOP_K)
        return [chunk for _, chunk in matches[:limit]]

    @staticmethod
    def _merge_chunks(primary: list[RetrievedChunk], secondary: list[RetrievedChunk], top_k: int | None = None) -> list[RetrievedChunk]:
        merged: OrderedDict[tuple[str, int], RetrievedChunk] = OrderedDict()
        for chunk in secondary + primary:
            key = (chunk.article_id, chunk.chunk_index)
            existing = merged.get(key)
            if existing is None:
                merged[key] = chunk
                continue
            existing_score = existing.score or 0.0
            chunk_score = chunk.score or 0.0
            if chunk_score > existing_score:
                merged[key] = chunk

        result = sorted(
            merged.values(),
            key=lambda item: item.score if item.score is not None else 0.0,
            reverse=True,
        )
        limit = max(1, top_k or settings.VECTOR_TOP_K)
        return result[:limit]

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
                        "Сначала изучи найденные статьи из базы знаний, затем ответь на вопрос пользователя. "
                        "Отвечай только по переданному контексту. Если данных недостаточно, прямо скажи об этом и не выдумывай факты."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Найденные статьи:\n"
                        f"{context}\n\n"
                        f"Вопрос: {question}"
                    ),
                },
            ],
        }

        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": settings.LLM_HTTP_REFERER,
            "X-Title": settings.LLM_APP_NAME,
        }
        if settings.LLM_API_KEY:
            headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"

        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=60.0)
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
        keyword_chunks = ChatService._keyword_fallback(question, top_k=top_k, category_id=category_id)
        filtered = ChatService._merge_chunks(filtered, keyword_chunks, top_k=top_k)

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
