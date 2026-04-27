from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SourceDocument, TextChunk
from app.documents.categories import category_membership_condition, normalize_categories


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    source_document_id: str
    file_name: str
    page_number: int
    chunk_text: str


_LITERAL_TERM_RE = re.compile(r"[\w:+#./-]{2,}", re.UNICODE)
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_RUSSIAN_LITERAL_STOPWORDS = {
    "без",
    "более",
    "быть",
    "весь",
    "всех",
    "всего",
    "где",
    "для",
    "должен",
    "должна",
    "должно",
    "должны",
    "его",
    "если",
    "или",
    "как",
    "какая",
    "какие",
    "какой",
    "какое",
    "когда",
    "куда",
    "между",
    "менее",
    "может",
    "можно",
    "над",
    "надо",
    "него",
    "нужно",
    "под",
    "после",
    "при",
    "про",
    "следует",
    "также",
    "текст",
    "текста",
    "тексте",
    "только",
    "этого",
    "этой",
    "этот",
    "это",
}


def _is_cyrillic_term(term: str) -> bool:
    return bool(_CYRILLIC_RE.search(term))


def extract_literal_terms(query_text: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for raw_term in _LITERAL_TERM_RE.findall(query_text or ""):
        term = raw_term.strip().lower()
        if len(term) < 2:
            continue
        if _is_cyrillic_term(term):
            if len(term) < 4:
                continue
            if term in _RUSSIAN_LITERAL_STOPWORDS:
                continue
        if term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


async def similarity_search(
    session: AsyncSession,
    *,
    query_vector: list[float],
    top_k: int,
    source_document_id: Optional[UUID] = None,
    doc_year_from: Optional[int] = None,
    doc_year_to: Optional[int] = None,
    doc_category: Optional[str] = None,
) -> List[RetrievedChunk]:
    stmt = (
        select(TextChunk, SourceDocument.file_name)
        .join(SourceDocument, TextChunk.source_document_id == SourceDocument.id)
        .where(SourceDocument.is_active.is_(True))
    )

    if source_document_id is not None:
        stmt = stmt.where(SourceDocument.id == source_document_id)
    if doc_year_from is not None:
        stmt = stmt.where(SourceDocument.doc_year >= doc_year_from)
    if doc_year_to is not None:
        stmt = stmt.where(SourceDocument.doc_year <= doc_year_to)
    if doc_category is not None:
        category_condition = category_membership_condition(SourceDocument.doc_category, doc_category)
        if category_condition is not None:
            stmt = stmt.where(category_condition)

    stmt = stmt.order_by(TextChunk.embedding.cosine_distance(query_vector)).limit(top_k)

    rows = (await session.execute(stmt)).all()
    return [
        RetrievedChunk(
            chunk_id=str(chunk.id),
            source_document_id=str(chunk.source_document_id),
            file_name=file_name,
            page_number=chunk.page_number,
            chunk_text=chunk.chunk_text,
        )
        for chunk, file_name in rows
    ]


async def keyword_search(
    session: AsyncSession,
    *,
    query_text: str,
    top_k: int,
    source_document_id: Optional[UUID] = None,
    doc_year_from: Optional[int] = None,
    doc_year_to: Optional[int] = None,
    doc_category: Optional[str] = None,
) -> List[RetrievedChunk]:
    normalized_doc_category = normalize_categories(doc_category)
    legacy_doc_category = doc_category.strip().lower() if doc_category else None

    sql = text(
        """
        WITH query AS (
          SELECT websearch_to_tsquery('russian', :query_text) AS ts_query
        )
        SELECT
          tc.id::text AS chunk_id,
          tc.source_document_id::text AS source_document_id,
          sd.file_name AS file_name,
          tc.page_number AS page_number,
          tc.chunk_text AS chunk_text
        FROM text_chunks tc
        JOIN source_documents sd ON tc.source_document_id = sd.id
        CROSS JOIN query q
        WHERE sd.is_active = TRUE
          AND (CAST(:source_document_id AS UUID) IS NULL OR sd.id = CAST(:source_document_id AS UUID))
          AND (CAST(:doc_year_from AS INTEGER) IS NULL OR sd.doc_year >= CAST(:doc_year_from AS INTEGER))
          AND (CAST(:doc_year_to AS INTEGER) IS NULL OR sd.doc_year <= CAST(:doc_year_to AS INTEGER))
          AND tc.search_vector @@ q.ts_query
          AND (
            CAST(:doc_category_token AS TEXT) IS NULL
            OR sd.doc_category ILIKE '%' || CAST(:doc_category_token AS TEXT) || '%'
            OR sd.doc_category = CAST(:doc_category_legacy AS TEXT)
          )
        ORDER BY
          ts_rank_cd(tc.search_vector, q.ts_query) DESC,
          tc.page_number ASC,
          tc.chunk_index ASC
        LIMIT :top_k
        """
    )

    rows = (
        await session.execute(
            sql,
            {
                "query_text": query_text,
                "top_k": top_k,
                "source_document_id": str(source_document_id) if source_document_id else None,
                "doc_year_from": doc_year_from,
                "doc_year_to": doc_year_to,
                "doc_category_token": normalized_doc_category,
                "doc_category_legacy": legacy_doc_category,
            },
        )
    ).all()

    return [
        RetrievedChunk(
            chunk_id=row.chunk_id,
            source_document_id=str(row.source_document_id),
            file_name=row.file_name,
            page_number=row.page_number,
            chunk_text=row.chunk_text,
        )
        for row in rows
    ]


async def literal_search(
    session: AsyncSession,
    *,
    query_text: str,
    top_k: int,
    source_document_id: Optional[UUID] = None,
    doc_year_from: Optional[int] = None,
    doc_year_to: Optional[int] = None,
    doc_category: Optional[str] = None,
) -> List[RetrievedChunk]:
    literal_terms = extract_literal_terms(query_text)
    if not literal_terms:
        return []

    normalized_doc_category = normalize_categories(doc_category)
    legacy_doc_category = doc_category.strip().lower() if doc_category else None

    sql = text(
        """
        SELECT
          tc.id::text AS chunk_id,
          tc.source_document_id::text AS source_document_id,
          sd.file_name AS file_name,
          tc.page_number AS page_number,
          tc.chunk_index AS chunk_index,
          tc.chunk_text AS chunk_text,
          GREATEST(
            COALESCE(array_length(regexp_split_to_array(lower(tc.chunk_text), :term_regex), 1), 1) - 1,
            0
          ) AS term_hits,
          MIN(
            CASE
              WHEN lower(tc.chunk_text) LIKE '%' || CAST(term.term AS TEXT) || '%'
              THEN POSITION(CAST(term.term AS TEXT) IN lower(tc.chunk_text))
              ELSE 2147483647
            END
          ) AS first_hit_pos
        FROM text_chunks tc
        JOIN source_documents sd ON tc.source_document_id = sd.id
        JOIN unnest(CAST(:literal_terms AS TEXT[])) AS term(term)
          ON lower(tc.chunk_text) LIKE '%' || CAST(term.term AS TEXT) || '%'
        WHERE sd.is_active = TRUE
          AND (CAST(:source_document_id AS UUID) IS NULL OR sd.id = CAST(:source_document_id AS UUID))
          AND (CAST(:doc_year_from AS INTEGER) IS NULL OR sd.doc_year >= CAST(:doc_year_from AS INTEGER))
          AND (CAST(:doc_year_to AS INTEGER) IS NULL OR sd.doc_year <= CAST(:doc_year_to AS INTEGER))
          AND (
            CAST(:doc_category_token AS TEXT) IS NULL
            OR sd.doc_category ILIKE '%' || CAST(:doc_category_token AS TEXT) || '%'
            OR sd.doc_category = CAST(:doc_category_legacy AS TEXT)
          )
        GROUP BY tc.id, tc.source_document_id, sd.file_name, tc.page_number, tc.chunk_index, tc.chunk_text
        ORDER BY term_hits DESC, first_hit_pos ASC, tc.page_number ASC, tc.chunk_index ASC
        LIMIT :top_k
        """
    )

    term_regex = "|".join(re.escape(term) for term in literal_terms)
    rows = (
        await session.execute(
            sql,
            {
                "literal_terms": literal_terms,
                "term_regex": term_regex or r"$^",
                "top_k": top_k,
                "source_document_id": str(source_document_id) if source_document_id else None,
                "doc_year_from": doc_year_from,
                "doc_year_to": doc_year_to,
                "doc_category_token": normalized_doc_category,
                "doc_category_legacy": legacy_doc_category,
            },
        )
    ).all()

    return [
        RetrievedChunk(
            chunk_id=row.chunk_id,
            source_document_id=str(row.source_document_id),
            file_name=row.file_name,
            page_number=row.page_number,
            chunk_text=row.chunk_text,
        )
        for row in rows
    ]
