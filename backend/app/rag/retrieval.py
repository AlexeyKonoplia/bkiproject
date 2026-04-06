from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SourceDocument, TextChunk


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    file_name: str
    page_number: int
    chunk_text: str


async def similarity_search(
    session: AsyncSession,
    *,
    query_vector: list[float],
    top_k: int,
    doc_year_from: Optional[int] = None,
    doc_year_to: Optional[int] = None,
    doc_category: Optional[str] = None,
) -> List[RetrievedChunk]:
    """
    Similarity Search по pgvector (cosine distance).
    """
    # NOTE: `embedding` — pgvector column type; cosine_distance генерирует выражение для ORDER BY.
    stmt = (
        select(TextChunk, SourceDocument.file_name)
        .join(SourceDocument, TextChunk.source_document_id == SourceDocument.id)
        .where(SourceDocument.is_active.is_(True))
    )

    if doc_year_from is not None:
        stmt = stmt.where(SourceDocument.doc_year >= doc_year_from)
    if doc_year_to is not None:
        stmt = stmt.where(SourceDocument.doc_year <= doc_year_to)
    if doc_category is not None:
        stmt = stmt.where(SourceDocument.doc_category == doc_category)

    stmt = stmt.order_by(TextChunk.embedding.cosine_distance(query_vector)).limit(top_k)

    res = await session.execute(stmt)
    rows = res.all()

    out: List[RetrievedChunk] = []
    for chunk, file_name in rows:
        out.append(
            RetrievedChunk(
                chunk_id=str(chunk.id),
                file_name=file_name,
                page_number=chunk.page_number,
                chunk_text=chunk.chunk_text,
            )
        )
    return out


async def keyword_search(
    session: AsyncSession,
    *,
    query_text: str,
    top_k: int,
    doc_year_from: Optional[int] = None,
    doc_year_to: Optional[int] = None,
    doc_category: Optional[str] = None,
) -> List[RetrievedChunk]:
    """
    Базовый (AS-IS) метод: PostgreSQL full-text search по `search_vector`.
    """
    # `search_vector` — GENERATED ALWAYS AS (to_tsvector('russian', chunk_text))
    sql = text(
        """
        SELECT
          tc.id::text AS chunk_id,
          sd.file_name AS file_name,
          tc.page_number AS page_number,
          tc.chunk_text AS chunk_text
        FROM text_chunks tc
        JOIN source_documents sd ON tc.source_document_id = sd.id
        WHERE sd.is_active = TRUE
          AND (:doc_year_from::int IS NULL OR sd.doc_year >= :doc_year_from)
          AND (:doc_year_to::int IS NULL OR sd.doc_year <= :doc_year_to)
          AND (:doc_category::text IS NULL OR sd.doc_category = :doc_category)
        ORDER BY ts_rank_cd(tc.search_vector, websearch_to_tsquery('russian', :query_text)) DESC
        LIMIT :top_k
        """
    )

    res = await session.execute(
        sql,
        {
            "query_text": query_text,
            "top_k": top_k,
            "doc_year_from": doc_year_from,
            "doc_year_to": doc_year_to,
            "doc_category": doc_category,
        },
    )
    rows = res.all()

    return [
        RetrievedChunk(
            chunk_id=row.chunk_id,
            file_name=row.file_name,
            page_number=row.page_number,
            chunk_text=row.chunk_text,
        )
        for row in rows
    ]


