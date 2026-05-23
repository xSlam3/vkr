from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
import html
import logging
import re
import time

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.knowledge_repo import KnowledgeRepository
from app.schemas.chat import ChatResponse, ChatSource
from app.services.vector_service import RetrievedChunk, VectorService


@dataclass
class RetrievedArticle:
    article_id: str
    title: str | None
    category_id: str | None
    text: str
    score: float | None


class ChatService:
    _logger = logging.getLogger("uvicorn.error")
    _llm_client: httpx.Client | None = None
    _BULLET_CHARS = {"•", "●", "▪", "◦", "○"}
    _STOP_TERMS = {
        "что",
        "это",
        "как",
        "мне",
        "или",
        "для",
        "вообще",
        "просто",
        "простыми",
        "словами",
        "если",
        "есть",
        "нет",
        "можно",
        "нужно",
        "почему",
        "откуда",
    }

    _QUESTION_SYNONYMS = {
        "585": ["проба", "золото", "металл"],
        "750": ["проба", "золото", "металл"],
        "925": ["проба", "серебро", "металл"],
        "натуральный": ["природный"],
        "натуральная": ["природный"],
        "натуральное": ["природный"],
        "подделка": ["имитация", "искусственный"],
        "подделки": ["имитация", "искусственный"],
        "поддельный": ["имитация", "искусственный"],
        "хороший": ["качество", "оценка"],
        "хорошая": ["качество", "оценка"],
        "дорогой": ["стоимость", "цена", "ценность"],
        "дороже": ["стоимость", "цена", "ценность"],
        "цена": ["стоимость"],
        "цены": ["стоимость"],
        "стоит": ["стоимость", "цена"],
        "стоить": ["стоимость", "цена"],
        "складывается": ["формируется", "стоимость", "цена"],
        "берется": ["формируется", "стоимость", "цена"],
        "объяснить": ["объяснять"],
        "объясняется": ["объяснять"],
        "большой": ["масса", "размер"],
        "большая": ["масса", "размер"],
        "бриллиант": ["цветность", "чистота", "огранка"],
        "фианит": ["имитация", "бриллиант"],
    }

    _STOP_TERMS.update(
        {
            "\u0447\u0442\u043e",
            "\u044d\u0442\u043e",
            "\u043a\u0430\u043a",
            "\u043c\u043d\u0435",
            "\u0438\u043b\u0438",
            "\u0434\u043b\u044f",
            "\u0432\u043e\u043e\u0431\u0449\u0435",
            "\u043f\u0440\u043e\u0441\u0442\u043e",
            "\u043f\u0440\u043e\u0441\u0442\u044b\u043c\u0438",
            "\u0441\u043b\u043e\u0432\u0430\u043c\u0438",
            "\u0435\u0441\u043b\u0438",
            "\u0435\u0441\u0442\u044c",
            "\u043d\u0435\u0442",
            "\u043c\u043e\u0436\u043d\u043e",
            "\u043d\u0443\u0436\u043d\u043e",
            "\u043f\u043e\u0447\u0435\u043c\u0443",
            "\u043e\u0442\u043a\u0443\u0434\u0430",
        }
    )

    _QUESTION_SYNONYMS.update(
        {
            "585": ["\u043f\u0440\u043e\u0431\u0430", "\u0437\u043e\u043b\u043e\u0442\u043e", "\u043c\u0435\u0442\u0430\u043b\u043b"],
            "750": ["\u043f\u0440\u043e\u0431\u0430", "\u0437\u043e\u043b\u043e\u0442\u043e", "\u043c\u0435\u0442\u0430\u043b\u043b"],
            "925": ["\u043f\u0440\u043e\u0431\u0430", "\u0441\u0435\u0440\u0435\u0431\u0440\u043e", "\u043c\u0435\u0442\u0430\u043b\u043b"],
            "\u043d\u0430\u0442\u0443\u0440\u0430\u043b\u044c\u043d\u044b\u0439": ["\u043f\u0440\u0438\u0440\u043e\u0434\u043d\u044b\u0439"],
            "\u043d\u0430\u0442\u0443\u0440\u0430\u043b\u044c\u043d\u0430\u044f": ["\u043f\u0440\u0438\u0440\u043e\u0434\u043d\u044b\u0439"],
            "\u043d\u0430\u0442\u0443\u0440\u0430\u043b\u044c\u043d\u043e\u0435": ["\u043f\u0440\u0438\u0440\u043e\u0434\u043d\u044b\u0439"],
            "\u043f\u043e\u0434\u0434\u0435\u043b\u043a\u0430": ["\u0438\u043c\u0438\u0442\u0430\u0446\u0438\u044f", "\u0438\u0441\u043a\u0443\u0441\u0441\u0442\u0432\u0435\u043d\u043d\u044b\u0439"],
            "\u043f\u043e\u0434\u0434\u0435\u043b\u043a\u0438": ["\u0438\u043c\u0438\u0442\u0430\u0446\u0438\u044f", "\u0438\u0441\u043a\u0443\u0441\u0441\u0442\u0432\u0435\u043d\u043d\u044b\u0439"],
            "\u043f\u043e\u0434\u0434\u0435\u043b\u044c\u043d\u044b\u0439": ["\u0438\u043c\u0438\u0442\u0430\u0446\u0438\u044f", "\u0438\u0441\u043a\u0443\u0441\u0441\u0442\u0432\u0435\u043d\u043d\u044b\u0439"],
            "\u0445\u043e\u0440\u043e\u0448\u0438\u0439": ["\u043a\u0430\u0447\u0435\u0441\u0442\u0432\u043e", "\u043e\u0446\u0435\u043d\u043a\u0430"],
            "\u0445\u043e\u0440\u043e\u0448\u0430\u044f": ["\u043a\u0430\u0447\u0435\u0441\u0442\u0432\u043e", "\u043e\u0446\u0435\u043d\u043a\u0430"],
            "\u0434\u043e\u0440\u043e\u0433\u043e\u0439": ["\u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c", "\u0446\u0435\u043d\u0430", "\u0446\u0435\u043d\u043d\u043e\u0441\u0442\u044c"],
            "\u0434\u043e\u0440\u043e\u0436\u0435": ["\u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c", "\u0446\u0435\u043d\u0430", "\u0446\u0435\u043d\u043d\u043e\u0441\u0442\u044c"],
            "\u0446\u0435\u043d\u0430": ["\u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c"],
            "\u0446\u0435\u043d\u044b": ["\u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c"],
            "\u0441\u0442\u043e\u0438\u0442": ["\u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c", "\u0446\u0435\u043d\u0430"],
            "\u0441\u0442\u043e\u0438\u0442\u044c": ["\u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c", "\u0446\u0435\u043d\u0430"],
            "\u0441\u043a\u043b\u0430\u0434\u044b\u0432\u0430\u0435\u0442\u0441\u044f": ["\u0444\u043e\u0440\u043c\u0438\u0440\u0443\u0435\u0442\u0441\u044f", "\u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c", "\u0446\u0435\u043d\u0430"],
            "\u0431\u0435\u0440\u0435\u0442\u0441\u044f": ["\u0444\u043e\u0440\u043c\u0438\u0440\u0443\u0435\u0442\u0441\u044f", "\u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c", "\u0446\u0435\u043d\u0430"],
            "\u043e\u0431\u044a\u044f\u0441\u043d\u0438\u0442\u044c": ["\u043e\u0431\u044a\u044f\u0441\u043d\u044f\u0442\u044c"],
            "\u043e\u0431\u044a\u044f\u0441\u043d\u044f\u0435\u0442\u0441\u044f": ["\u043e\u0431\u044a\u044f\u0441\u043d\u044f\u0442\u044c"],
            "\u0431\u043e\u043b\u044c\u0448\u043e\u0439": ["\u043c\u0430\u0441\u0441\u0430", "\u0440\u0430\u0437\u043c\u0435\u0440"],
            "\u0431\u043e\u043b\u044c\u0448\u0430\u044f": ["\u043c\u0430\u0441\u0441\u0430", "\u0440\u0430\u0437\u043c\u0435\u0440"],
            "\u0431\u0440\u0438\u043b\u043b\u0438\u0430\u043d\u0442": ["\u0446\u0432\u0435\u0442\u043d\u043e\u0441\u0442\u044c", "\u0447\u0438\u0441\u0442\u043e\u0442\u0430", "\u043e\u0433\u0440\u0430\u043d\u043a\u0430"],
            "\u0444\u0438\u0430\u043d\u0438\u0442": ["\u0438\u043c\u0438\u0442\u0430\u0446\u0438\u044f", "\u0431\u0440\u0438\u043b\u043b\u0438\u0430\u043d\u0442"],
        }
    )

    @staticmethod
    def _to_plain_text(value: str) -> str:
        text = value or ""
        replacements = [
            (r"(?i)<br\s*/?>", "\n"),
            (r"(?i)<li[^>]*>", "- "),
            (r"(?i)</li>", "\n"),
            (r"(?i)</(p|div|h1|h2|h3|h4|blockquote|pre|figure|figcaption|ul|ol|table|thead|tbody|tfoot|tr|caption)>", "\n"),
            (r"(?i)</(td|th)>", " | "),
        ]
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text)

        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)

        lines: list[str] = []
        buffer = ""
        pending_bullet = False

        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            line = re.sub(r"(?:\s*\|\s*){2,}", " | ", line).strip(" |")

            if not line:
                if buffer:
                    lines.append(buffer)
                    buffer = ""
                pending_bullet = False
                continue

            if line in ChatService._BULLET_CHARS:
                pending_bullet = True
                continue

            if pending_bullet:
                line = f"- {line.lstrip('- ').strip()}"
                pending_bullet = False

            if buffer and ChatService._should_join_plain_lines(buffer, line):
                buffer = f"{buffer} {line}"
                continue

            if buffer:
                lines.append(buffer)
            buffer = line

        if buffer:
            lines.append(buffer)

        return "\n".join(lines).strip()

    @staticmethod
    def _should_join_plain_lines(previous: str, current: str) -> bool:
        if not previous or not current:
            return False

        if previous.startswith("- "):
            return False

        if previous[-1] in ".!?;:":
            return False

        current_first = current[0]
        return current_first.islower() or current_first.isdigit() or current_first in {",", ")", "]"}

    @staticmethod
    def _is_substantive_fragment(fragment: str) -> bool:
        words = fragment.split()
        if len(words) < 3 and not any(char.isdigit() for char in fragment):
            return False
        if len(fragment) < 18 and not any(char.isdigit() for char in fragment):
            return False
        return True

    @staticmethod
    def _fragment_quality_bonus(fragment: str) -> float:
        bonus = min(len(fragment), 180) / 600
        if fragment.endswith((".", "!", "?")):
            bonus += 0.12
        if fragment.startswith("- "):
            bonus -= 0.05
        return bonus

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", ChatService._to_plain_text(value)).strip().lower()

    @staticmethod
    def _extract_terms(question: str) -> list[str]:
        words = re.findall(r"[A-Za-z\u0400-\u04FF0-9]+", (question or "").lower())
        unique_terms: list[str] = []
        expanded_words: list[str] = []

        for word in words:
            if word in ChatService._STOP_TERMS:
                continue

            expanded_words.append(word)
            expanded_words.extend(ChatService._QUESTION_SYNONYMS.get(word, []))

        for word in expanded_words:
            if len(word) < 4 and not (word.isdigit() and len(word) >= 3):
                continue

            candidates = [word]
            if len(word) >= 5 and not word.isdigit():
                candidates.append(word[:5])
            if len(word) >= 4 and not word.isdigit():
                candidates.append(word[:4])
            for candidate in candidates:
                if candidate not in unique_terms:
                    unique_terms.append(candidate)
        return unique_terms

    @staticmethod
    def _question_flags(question: str) -> dict[str, bool]:
        normalized = (question or "").lower()
        return {
            "probe": any(token in normalized for token in ("585", "750", "925", "\u043f\u0440\u043e\u0431")),
            "price": any(
                token in normalized
                for token in (
                    "\u0446\u0435\u043d",
                    "\u0441\u0442\u043e\u0438\u043c",
                    "\u0434\u043e\u0440\u043e\u0433",
                    "\u0441\u0442\u043e\u0438\u0442",
                    "\u0441\u043a\u043b\u0430\u0434\u044b\u0432",
                    "\u0431\u0435\u0440\u0435\u0442\u0441",
                    "\u0444\u043e\u0440\u043c\u0438\u0440\u0443",
                )
            ),
            "stone": any(
                token in normalized
                for token in (
                    "\u043a\u0430\u043c\u0435\u043d",
                    "\u0431\u0440\u0438\u043b\u043b\u0438\u0430\u043d\u0442",
                    "\u0432\u0441\u0442\u0430\u0432\u043a",
                )
            ),
            "size": any(
                token in normalized
                for token in (
                    "\u0431\u043e\u043b\u044c\u0448",
                    "\u0440\u0430\u0437\u043c\u0435\u0440",
                    "\u043c\u0430\u0441\u0441",
                )
            ),
            "rating": any(
                token in normalized
                for token in (
                    "\u0445\u043e\u0440\u043e\u0448",
                    "\u043e\u0446\u0435\u043d",
                    "\u043a\u0430\u0447\u0435\u0441\u0442",
                    "\u0447\u0438\u0441\u0442\u043e\u0442",
                    "\u043e\u0433\u0440\u0430\u043d\u043a",
                    "\u0446\u0432\u0435\u0442\u043d\u043e\u0441\u0442",
                )
            ),
            "synthetic": any(
                token in normalized
                for token in (
                    "\u0441\u0438\u043d\u0442\u0435\u0442",
                    "\u0444\u0438\u0430\u043d\u0438\u0442",
                )
            ),
            "imitation": any(
                token in normalized
                for token in (
                    "\u0438\u043c\u0438\u0442\u0430\u0446",
                    "\u043f\u043e\u0434\u0434\u0435\u043b",
                    "\u0438\u0441\u043a\u0443\u0441\u0441\u0442\u0432\u0435\u043d",
                )
            ),
            "natural": any(
                token in normalized
                for token in (
                    "\u043d\u0430\u0442\u0443\u0440\u0430\u043b",
                    "\u043f\u0440\u0438\u0440\u043e\u0434\u043d",
                )
            ),
            "showcase": any(
                token in normalized
                for token in (
                    "\u0432\u0438\u0442\u0440\u0438\u043d",
                    "\u0432\u044b\u043a\u043b\u0430\u0434",
                    "\u0432\u044b\u043b\u043e\u0436",
                    "\u0437\u043e\u043d",
                    "\u0446\u0435\u043d\u0442\u0440",
                    "\u0443\u0440\u043e\u0432\u043d\u0435 \u0433\u043b\u0430\u0437",
                    "\u0433\u043e\u0440\u044f\u0447",
                )
            ),
        }

    @staticmethod
    def _score_by_keywords(question: str, title: str, text: str) -> float:
        terms = ChatService._extract_terms(question)
        if not terms:
            return 0.0

        normalized_title = title.lower()
        normalized_text = text.lower()
        title_tokens = re.findall(r"[a-z\u0400-\u04FF0-9]+", normalized_title)
        text_tokens = re.findall(r"[a-z\u0400-\u04FF0-9]+", normalized_text)
        flags = ChatService._question_flags(question)

        score = 0
        for term in terms:
            if term in normalized_title or any(token.startswith(term) for token in title_tokens):
                score += 3
            if term in normalized_text or any(token.startswith(term) for token in text_tokens):
                score += 1

        if flags["probe"] and (
            "\u043f\u0440\u043e\u0431" in normalized_title
            or "\u043f\u0440\u043e\u0431" in normalized_text
            or "585" in normalized_text
            or "750" in normalized_text
            or "925" in normalized_text
        ):
            score += 6

        if flags["probe"] and (
            normalized_title.strip() == "\u043f\u0440\u043e\u0431\u044b"
            or normalized_title.startswith("\u043f\u0440\u043e\u0431")
        ):
            score += 6

        if flags["price"] and (
            "\u0446\u0435\u043d" in normalized_title
            or "\u0441\u0442\u043e\u0438\u043c" in normalized_title
            or "\u0444\u043e\u0440\u043c\u0438\u0440" in normalized_title
            or "\u0446\u0435\u043d" in normalized_text
            or "\u0441\u0442\u043e\u0438\u043c" in normalized_text
        ):
            score += 4

        if flags["synthetic"] and flags["imitation"] and (
            ("\u0441\u0438\u043d\u0442\u0435\u0442" in normalized_title or "\u0441\u0438\u043d\u0442\u0435\u0442" in normalized_text)
            and ("\u0438\u043c\u0438\u0442\u0430\u0446" in normalized_title or "\u0438\u043c\u0438\u0442\u0430\u0446" in normalized_text)
        ):
            score += 6

        if flags["rating"] and (
            "\u043e\u0446\u0435\u043d" in normalized_title
            or "\u043a\u0430\u0447\u0435\u0441\u0442" in normalized_title
            or "\u0447\u0438\u0441\u0442\u043e\u0442" in normalized_text
            or "\u0446\u0432\u0435\u0442\u043d\u043e\u0441\u0442" in normalized_text
            or "\u043e\u0433\u0440\u0430\u043d\u043a" in normalized_text
        ):
            score += 5

        if flags["stone"] and flags["size"] and (
            "\u0440\u0430\u0437\u043c\u0435\u0440" in normalized_text
            or "\u043c\u0430\u0441\u0441" in normalized_text
            or "\u043a\u0430\u0440\u0430\u0442" in normalized_text
        ):
            score += 4

        if flags["stone"] and flags["size"] and flags["price"] and (
            "\u043e\u0446\u0435\u043d" in normalized_title
            or "\u0441\u0442\u043e\u0438\u043c" in normalized_title
            or "\u0446\u0435\u043d" in normalized_title
        ):
            score += 4

        if flags["stone"] and flags["size"] and (
            "\u043e\u0446\u0435\u043d\u0438\u0432\u0430\u0442\u044c \u043a\u0430\u043c\u0435\u043d\u044c \u0442\u043e\u043b\u044c\u043a\u043e \u043f\u043e \u0440\u0430\u0437\u043c\u0435\u0440\u0443 \u043d\u0435\u043b\u044c\u0437\u044f" in normalized_text
            or "\u0440\u0430\u0437\u043c\u0435\u0440\u0443 \u043d\u0435\u043b\u044c\u0437\u044f" in normalized_text
        ):
            score += 8

        if flags["natural"] and (
            "\u043f\u0440\u0438\u0440\u043e\u0434" in normalized_title
            or "\u043f\u0440\u0438\u0440\u043e\u0434" in normalized_text
            or "\u043c\u0430\u0440\u043a\u0438\u0440\u043e\u0432" in normalized_text
            or "\u0441\u0435\u0440\u0442\u0438\u0444\u0438\u043a" in normalized_text
        ):
            score += 4

        if flags["showcase"] and (
            "\u0432\u044b\u043a\u043b\u0430\u0434" in normalized_title
            or "\u0432\u0438\u0442\u0440\u0438\u043d" in normalized_title
            or "\u0437\u043e\u043d\u0438\u0440" in normalized_title
            or "\u0432\u044b\u043a\u043b\u0430\u0434" in normalized_text
            or "\u0432\u0438\u0442\u0440\u0438\u043d" in normalized_text
            or "\u0433\u043e\u0440\u044f\u0447" in normalized_text
        ):
            score += 8

        if flags["showcase"] and (
            "\u0434\u043e\u0440\u043e\u0433" in normalized_text
            or "\u0446\u0435\u043d\u043e\u0432\u043e\u0439 \u0441\u0435\u0433\u043c\u0435\u043d\u0442" in normalized_text
            or "\u0431\u043b\u0438\u0436\u0435 \u043a \u0446\u0435\u043d\u0442\u0440\u0443" in normalized_text
            or "\u0443\u0440\u043e\u0432\u043d\u0435 \u0433\u043b\u0430\u0437" in normalized_text
        ):
            score += 6

        return min(score / max(len(terms) * 3, 1), 1.0)

    @staticmethod
    def _keyword_fallback(
        db: Session,
        question: str,
        top_k: int | None = None,
        category_id: str | None = None,
    ) -> list[RetrievedChunk]:
        articles = KnowledgeRepository.list_articles(db, category_id=category_id)

        matches: list[tuple[float, RetrievedChunk]] = []
        for article in articles:
            plain_text = ChatService._to_plain_text(article.text_content)
            score = ChatService._score_by_keywords(question, article.title or "", plain_text)
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
                        text=plain_text,
                        score=score,
                    ),
                )
            )

        matches.sort(key=lambda item: item[0], reverse=True)
        limit = max(8, max(1, top_k or settings.VECTOR_TOP_K) * 4)
        return [chunk for _, chunk in matches[:limit]]

    @staticmethod
    def _merge_chunks(
        primary: list[RetrievedChunk],
        secondary: list[RetrievedChunk],
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
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
        limit = max(8, max(1, top_k or settings.VECTOR_TOP_K) * 4)
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
    def _select_articles(
        db: Session,
        question: str,
        chunks: list[RetrievedChunk],
        top_k: int | None = None,
        category_id: str | None = None,
    ) -> list[RetrievedArticle]:
        vector_scores: dict[str, float] = {}
        chunk_texts: dict[str, list[str]] = {}
        article_titles: dict[str, str | None] = {}
        article_categories: dict[str, str | None] = {}

        for chunk in chunks:
            if not chunk.article_id:
                continue
            chunk_score = chunk.score or 0.0
            vector_scores[chunk.article_id] = max(vector_scores.get(chunk.article_id, 0.0), chunk_score)
            chunk_texts.setdefault(chunk.article_id, []).append(chunk.text)
            article_titles.setdefault(chunk.article_id, chunk.title)
            article_categories.setdefault(chunk.article_id, chunk.category_id)

        articles = KnowledgeRepository.list_articles(db, category_id=category_id)

        selected: list[tuple[float, RetrievedArticle]] = []
        seen_article_ids: set[str] = set()

        for article in articles:
            plain_text = ChatService._to_plain_text(article.text_content)
            keyword_score = ChatService._score_by_keywords(question, article.title or "", plain_text)
            vector_score = vector_scores.get(article.id, 0.0)
            if vector_score <= 0 and keyword_score <= 0:
                continue

            final_score = max(vector_score, keyword_score)
            combined_score = keyword_score * 4 + vector_score * 1.5
            if keyword_score > 0 and vector_score > 0:
                combined_score += min(keyword_score, vector_score)
            selected.append(
                (
                    combined_score,
                    RetrievedArticle(
                        article_id=article.id,
                        title=article.title,
                        category_id=article.category_id,
                        text=plain_text,
                        score=final_score,
                    ),
                )
            )
            seen_article_ids.add(article.id)

        if not selected:
            for article_id, texts in chunk_texts.items():
                unique_texts = list(OrderedDict.fromkeys(text.strip() for text in texts if text.strip()))
                if not unique_texts:
                    continue

                selected.append(
                    (
                        vector_scores.get(article_id, 0.0) * 10,
                        RetrievedArticle(
                            article_id=article_id,
                            title=article_titles.get(article_id),
                            category_id=article_categories.get(article_id),
                            text="\n\n".join(unique_texts),
                            score=vector_scores.get(article_id),
                        ),
                    )
                )

        selected.sort(
            key=lambda item: (
                item[0],
                item[1].score if item[1].score is not None else 0.0,
            ),
            reverse=True,
        )
        limit = max(1, top_k or settings.VECTOR_TOP_K)
        return [article for _, article in selected[:limit]]

    @staticmethod
    def _collect_fragments(article: RetrievedArticle) -> list[str]:
        fragments: list[str] = []
        lines = [re.sub(r"\s+", " ", line).strip() for line in article.text.splitlines() if line.strip()]

        for idx, line in enumerate(lines):
            clean_line = re.sub(r"\s+", " ", line).strip()
            if not clean_line:
                continue
            if "|" in clean_line:
                fragments.append(clean_line)
                continue

            if clean_line.startswith("- "):
                fragments.append(clean_line)
                if idx > 0:
                    previous = lines[idx - 1]
                    if previous and previous[-1] not in ".!?;:" and not previous.startswith("- "):
                        fragments.append(f"{previous} {clean_line}")
                continue

            if idx + 1 < len(lines):
                next_line = lines[idx + 1]
                if clean_line[-1] not in ".!?;:" and next_line and not next_line.startswith("- "):
                    fragments.append(f"{clean_line} {next_line}")

            sentence_parts = re.split(r"(?<=[.!?])\s+", clean_line)
            for part in sentence_parts:
                fragment = re.sub(r"\s+", " ", part).strip()
                if fragment:
                    fragments.append(fragment)

        return list(OrderedDict.fromkeys(fragments))

    @staticmethod
    def _select_relevant_fragments(question: str, article: RetrievedArticle, limit: int = 3) -> list[str]:
        ranked: list[tuple[float, int, str]] = []
        for idx, fragment in enumerate(ChatService._collect_fragments(article)):
            if not ChatService._is_substantive_fragment(fragment):
                continue
            score = ChatService._score_by_keywords(question, article.title or "", fragment)
            if score <= 0:
                continue
            ranked.append((score + ChatService._fragment_quality_bonus(fragment), -idx, fragment))

        ranked.sort(reverse=True)
        best = [fragment for _, _, fragment in ranked[:limit]]
        return list(OrderedDict.fromkeys(best))

    @staticmethod
    def _build_context(articles: list[RetrievedArticle]) -> str:
        lines: list[str] = []
        for idx, article in enumerate(articles, start=1):
            title = article.title or "Без названия"
            lines.append(f"[Статья {idx}] {title}")
            lines.append(article.text)
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def _trim_context_articles(articles: list[RetrievedArticle], limit: int) -> list[RetrievedArticle]:
        if not articles:
            return []

        limited = articles[:limit]
        best_score = limited[0].score or 0.0
        threshold = max(0.35, best_score * 0.55)

        trimmed = [limited[0]]
        for article in limited[1:]:
            article_score = article.score or 0.0
            if article_score >= threshold:
                trimmed.append(article)

        return trimmed

    @staticmethod
    def _build_sources(articles: list[RetrievedArticle]) -> list[ChatSource]:
        sources: OrderedDict[str, ChatSource] = OrderedDict()
        for article in articles:
            if not article.article_id:
                continue

            existing = sources.get(article.article_id)
            if existing is None:
                sources[article.article_id] = ChatSource(
                    article_id=article.article_id,
                    title=article.title,
                    score=article.score,
                )
                continue

            if existing.score is None and article.score is not None:
                existing.score = article.score
            elif existing.score is not None and article.score is not None:
                existing.score = max(existing.score, article.score)

        return list(sources.values())

    @staticmethod
    def _fallback_answer(question: str, article: RetrievedArticle) -> str:
        fragments = ChatService._select_relevant_fragments(question, article)
        if fragments:
            selected: list[str] = []
            for fragment in fragments:
                selected.append(fragment)
                if len(" ".join(selected)) >= 180 or fragment.endswith((".", "!", "?")) or len(selected) == 2:
                    break

            answer = " ".join(selected)
            if article.title:
                return f'По статье "{article.title}":\n{answer}'
            return answer

        best = article.text.strip()
        return best if len(best) <= 400 else best[:400] + "..."

    @staticmethod
    def _format_llm_error(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = {}

        error = payload.get("error") if isinstance(payload, dict) else {}
        if not isinstance(error, dict):
            error = {}

        message = error.get("message") or response.text.strip() or "Unknown LLM error"
        metadata = error.get("metadata") if isinstance(error.get("metadata"), dict) else {}
        raw = metadata.get("raw")
        if raw:
            message = f"{message}: {raw}"

        status_label = "OpenRouter error"
        if response.status_code == 429:
            status_label = "OpenRouter rate limit"
        elif response.status_code >= 500:
            status_label = "OpenRouter unavailable"

        return f"{status_label}: {message}"

    @staticmethod
    def _build_llm_headers() -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": settings.LLM_HTTP_REFERER,
            "X-Title": settings.LLM_APP_NAME,
        }
        if settings.LLM_API_KEY:
            headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"
        return headers

    @classmethod
    def _get_llm_client(cls) -> httpx.Client:
        if cls._llm_client is None:
            cls._llm_client = httpx.Client(
                timeout=httpx.Timeout(
                    settings.LLM_TIMEOUT_SECONDS,
                    connect=min(settings.LLM_TIMEOUT_SECONDS, 10.0),
                ),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
        return cls._llm_client

    @classmethod
    def close_llm_client(cls) -> None:
        if cls._llm_client is None:
            return

        cls._llm_client.close()
        cls._llm_client = None

    @staticmethod
    def _perform_llm_request(url: str, payload: dict[str, object], headers: dict[str, str]) -> httpx.Response:
        return ChatService._get_llm_client().post(url, json=payload, headers=headers)

    @staticmethod
    def _sanitize_llm_answer(answer: str) -> str:
        cleaned = (answer or "").strip()
        if not cleaned:
            return ""

        cleaned = re.sub(r"[\u3400-\u4DBF\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]+", "", cleaned)
        cleaned = re.sub(r"[。，、；：]", "", cleaned)
        cleaned = re.sub(r"\[\d+\]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        not_found_phrase = "\u0412 \u0431\u0430\u0437\u0435 \u0437\u043d\u0430\u043d\u0438\u0439 \u043d\u0435\u0442 \u0442\u043e\u0447\u043d\u043e\u0433\u043e \u043e\u0442\u0432\u0435\u0442\u0430 \u043d\u0430 \u044d\u0442\u043e\u0442 \u0432\u043e\u043f\u0440\u043e\u0441."
        if not_found_phrase in cleaned and cleaned != not_found_phrase:
            cleaned = cleaned.replace(not_found_phrase, "").strip()
        cleaned = cleaned.rstrip(" ,;:")
        return cleaned.strip()

    @staticmethod
    def _call_llm(question: str, context: str) -> tuple[str | None, str | None]:
        if not settings.CHAT_USE_LLM:
            return None, None
        if not settings.LLM_API_URL:
            return None, "LLM API URL is not configured."
        model = (settings.LLM_MODEL or "").strip()
        if not model:
            return None, "LLM model is not configured."

        headers = ChatService._build_llm_headers()
        url = settings.LLM_API_URL.rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "temperature": settings.LLM_TEMPERATURE,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты помощник по базе знаний ювелирного магазина. "
                        "Тебе передают одну наиболее релевантную статью из базы знаний. "
                        "Отвечай только по этой статье и не используй внешние знания. "
                        "Сначала найди в статье прямой ответ на вопрос пользователя, затем сформулируй короткий и точный ответ по существу. "
                        "Не пересказывай статью целиком, не добавляй факты от себя и не используй информацию, которой нет в статье. "
                        "Если в статье нет точного ответа, ответь: "
                        "'В базе знаний нет точного ответа на этот вопрос.'"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Найденная статья базы знаний:\n"
                        f"{context}\n\n"
                        f"Вопрос пользователя: {question}"
                    ),
                },
            ],
        }

        payload["messages"][0]["content"] = (
            "\u0422\u044b \u043f\u043e\u043c\u043e\u0449\u043d\u0438\u043a \u043f\u043e \u0431\u0430\u0437\u0435 \u0437\u043d\u0430\u043d\u0438\u0439 \u044e\u0432\u0435\u043b\u0438\u0440\u043d\u043e\u0433\u043e \u043c\u0430\u0433\u0430\u0437\u0438\u043d\u0430. "
            "\u0422\u0435\u0431\u0435 \u043f\u0435\u0440\u0435\u0434\u0430\u044e\u0442 \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u043d\u0430\u0438\u0431\u043e\u043b\u0435\u0435 \u0440\u0435\u043b\u0435\u0432\u0430\u043d\u0442\u043d\u044b\u0445 \u0441\u0442\u0430\u0442\u0435\u0439 \u0438\u0437 \u0431\u0430\u0437\u044b \u0437\u043d\u0430\u043d\u0438\u0439. "
            "\u041e\u0442\u0432\u0435\u0447\u0430\u0439 \u0442\u043e\u043b\u044c\u043a\u043e \u043f\u043e \u044d\u0442\u0438\u043c \u0441\u0442\u0430\u0442\u044c\u044f\u043c \u0438 \u043d\u0435 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u0432\u043d\u0435\u0448\u043d\u0438\u0435 \u0437\u043d\u0430\u043d\u0438\u044f. "
            "\u041f\u0438\u0448\u0438 \u0442\u043e\u043b\u044c\u043a\u043e \u043d\u0430 \u0440\u0443\u0441\u0441\u043a\u043e\u043c \u044f\u0437\u044b\u043a\u0435. "
            "\u041d\u0435 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 markdown, \u0438\u0435\u0440\u043e\u0433\u043b\u0438\u0444\u044b, \u0430\u043d\u0433\u043b\u0438\u0439\u0441\u043a\u0438\u0435 \u0432\u0441\u0442\u0430\u0432\u043a\u0438 \u0438 \u0444\u0430\u043a\u0442\u044b, \u043a\u043e\u0442\u043e\u0440\u044b\u0445 \u043d\u0435\u0442 \u0432 \u043f\u0435\u0440\u0435\u0434\u0430\u043d\u043d\u044b\u0445 \u0441\u0442\u0430\u0442\u044c\u044f\u0445. "
            "\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u043d\u0430\u0439\u0434\u0438 \u043f\u0440\u044f\u043c\u043e\u0439 \u043e\u0442\u0432\u0435\u0442 \u0432 \u0441\u0442\u0430\u0442\u044c\u044f\u0445, \u0437\u0430\u0442\u0435\u043c \u0434\u0430\u0439 \u043a\u0440\u0430\u0442\u043a\u0438\u0439 \u0442\u043e\u0447\u043d\u044b\u0439 \u043e\u0442\u0432\u0435\u0442 \u043e\u0434\u043d\u0438\u043c-\u0434\u0432\u0443\u043c\u044f \u0444\u0440\u0430\u0437\u0430\u043c\u0438. "
            "\u0415\u0441\u043b\u0438 \u0442\u043e\u0447\u043d\u043e\u0433\u043e \u043e\u0442\u0432\u0435\u0442\u0430 \u043d\u0435\u0442, \u043e\u0442\u0432\u0435\u0442\u044c: "
            "'\u0412 \u0431\u0430\u0437\u0435 \u0437\u043d\u0430\u043d\u0438\u0439 \u043d\u0435\u0442 \u0442\u043e\u0447\u043d\u043e\u0433\u043e \u043e\u0442\u0432\u0435\u0442\u0430 \u043d\u0430 \u044d\u0442\u043e\u0442 \u0432\u043e\u043f\u0440\u043e\u0441.'"
        )
        payload["messages"][1]["content"] = (
            "\u041d\u0430\u0439\u0434\u0435\u043d\u043d\u044b\u0435 \u0441\u0442\u0430\u0442\u044c\u0438 \u0431\u0430\u0437\u044b \u0437\u043d\u0430\u043d\u0438\u0439:\n"
            f"{context}\n\n"
            f"\u0412\u043e\u043f\u0440\u043e\u0441 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f: {question}"
        )

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(ChatService._perform_llm_request, url, payload, headers)
                response = future.result(timeout=settings.LLM_TIMEOUT_SECONDS)
            if response.status_code >= 400:
                return None, ChatService._format_llm_error(response)
            data = response.json()
            answer = ChatService._sanitize_llm_answer(data["choices"][0]["message"]["content"])
            if not answer:
                return None, "OpenRouter returned an empty answer."
            return answer, None
        except FuturesTimeoutError:
            return None, f"OpenRouter timed out after {settings.LLM_TIMEOUT_SECONDS:.1f}s."
        except Exception as exc:
            return None, f"OpenRouter request failed: {exc}"

    @staticmethod
    def ask(db: Session, question: str, top_k: int | None = None, category_id: str | None = None) -> ChatResponse:
        request_started_at = time.perf_counter()
        vector_started_at = time.perf_counter()
        chunks = VectorService.search(
            query=question,
            top_k=top_k or settings.VECTOR_TOP_K,
            category_id=category_id,
        )
        vector_elapsed = time.perf_counter() - vector_started_at
        ranking_started_at = time.perf_counter()
        filtered = ChatService._filter_chunks(chunks)
        keyword_chunks = ChatService._keyword_fallback(db, question, top_k=top_k, category_id=category_id)
        filtered = ChatService._merge_chunks(filtered, keyword_chunks, top_k=top_k)
        selected_articles = ChatService._select_articles(
            db,
            question,
            filtered,
            top_k=top_k,
            category_id=category_id,
        )
        ranking_elapsed = time.perf_counter() - ranking_started_at

        if not selected_articles:
            total_elapsed = time.perf_counter() - request_started_at
            ChatService._logger.info(
                "Chat timing total=%.3fs vector=%.3fs ranking=%.3fs llm=%.3fs selected_articles=0",
                total_elapsed,
                vector_elapsed,
                ranking_elapsed,
                0.0,
            )
            return ChatResponse(
                answer="Не нашел релевантной информации в базе знаний.",
                sources=[],
                used_context=False,
            )

        best_article = selected_articles[0]
        context_limit = min(max(1, top_k or settings.VECTOR_TOP_K), 3)
        context_articles = ChatService._trim_context_articles(selected_articles, context_limit)
        context = ChatService._build_context(context_articles)
        llm_started_at = time.perf_counter()
        llm_answer, llm_error = ChatService._call_llm(question, context)
        llm_elapsed = time.perf_counter() - llm_started_at
        if settings.CHAT_USE_LLM and llm_answer:
            answer = llm_answer or (
                "Не удалось получить ответ от OpenRouter.\n"
                f"{llm_error or 'Неизвестная ошибка LLM.'}"
            )
        else:
            if settings.CHAT_USE_LLM:
                ChatService._logger.warning("LLM fallback used: %s", llm_error or "unknown LLM error")
            answer = ChatService._fallback_answer(question, best_article)

        total_elapsed = time.perf_counter() - request_started_at
        ChatService._logger.info(
            "Chat timing total=%.3fs vector=%.3fs ranking=%.3fs llm=%.3fs selected_articles=%d chunks=%d",
            total_elapsed,
            vector_elapsed,
            ranking_elapsed,
            llm_elapsed,
            len(context_articles),
            len(chunks),
        )

        return ChatResponse(
            answer=answer,
            sources=ChatService._build_sources(context_articles),
            used_context=True,
        )
