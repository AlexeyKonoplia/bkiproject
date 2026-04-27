from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.app_api import UpstreamApiError, post_multipart
from app.db.models import SourceDocument, TextChunk
from app.db.session import get_db
from app.documents.categories import categories_label, normalize_categories, parse_categories
from app.security.jwt import admin_required, user_required

router = APIRouter(prefix="/api/documents", tags=["documents"], dependencies=[Depends(user_required)])


class DocumentSummary(BaseModel):
    id: str
    file_name: str
    doc_year: Optional[int] = None
    doc_category: Optional[str] = None
    categories: list[str] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    chunk_count: int
    page_count: int
    matched_chunks: int = 0
    snippet: Optional[str] = None


class DocumentListResponse(BaseModel):
    total: int
    items: list[DocumentSummary]


class DocumentPage(BaseModel):
    page_number: int
    text: str


class DocumentDetail(BaseModel):
    id: str
    file_name: str
    doc_year: Optional[int] = None
    doc_category: Optional[str] = None
    categories: list[str] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    page_count: int
    chunk_count: int
    content_text: str
    pages: list[DocumentPage]


class DocumentMatch(BaseModel):
    chunk_id: str
    page_number: int
    snippet: str


class DocumentStatusUpdateRequest(BaseModel):
    is_active: bool = Field(...)


class DocumentCategoriesUpdateRequest(BaseModel):
    categories: list[str] = Field(default_factory=list)


class AdminDocumentMutationResponse(BaseModel):
    id: str
    status: str
    is_active: Optional[bool] = None
    doc_category: Optional[str] = None
    categories: list[str] = Field(default_factory=list)


def _normalize_query(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _build_snippet(text: str, query: Optional[str], *, radius: int = 180) -> str:
    compact = " ".join(text.split())
    if not compact:
        return ""
    if not query:
        return compact[:radius].strip()

    lowered = compact.lower()
    lowered_query = query.lower()
    idx = lowered.find(lowered_query)
    if idx == -1:
        return compact[:radius].strip()

    start = max(0, idx - radius // 2)
    end = min(len(compact), idx + len(query) + radius // 2)
    snippet = compact[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(compact):
        snippet = snippet + "..."
    return snippet


async def _get_doc_stats(session: AsyncSession, doc_ids: list[UUID]) -> tuple[dict[str, int], dict[str, int]]:
    if not doc_ids:
        return {}, {}

    rows = (
        await session.execute(
            select(
                TextChunk.source_document_id,
                func.count(TextChunk.id),
                func.max(TextChunk.page_number) + 1,
            )
            .where(TextChunk.source_document_id.in_(doc_ids))
            .group_by(TextChunk.source_document_id)
        )
    ).all()

    chunk_count_by_doc: dict[str, int] = {}
    page_count_by_doc: dict[str, int] = {}
    for doc_id, chunk_count, page_count in rows:
        key = str(doc_id)
        chunk_count_by_doc[key] = int(chunk_count or 0)
        page_count_by_doc[key] = int(page_count or 0)
    return chunk_count_by_doc, page_count_by_doc


async def _get_content_matches(
    session: AsyncSession,
    doc_ids: list[UUID],
    content_query: Optional[str],
) -> tuple[dict[str, int], dict[str, str]]:
    if not doc_ids or not content_query:
        return {}, {}

    pattern = f"%{content_query}%"
    rows = (
        await session.execute(
            select(TextChunk.source_document_id, TextChunk.chunk_text)
            .where(
                TextChunk.source_document_id.in_(doc_ids),
                TextChunk.chunk_text.ilike(pattern),
            )
            .order_by(TextChunk.source_document_id, TextChunk.page_number, TextChunk.chunk_index)
        )
    ).all()

    matched_chunks: dict[str, int] = {}
    snippets: dict[str, str] = {}
    for doc_id, chunk_text in rows:
        key = str(doc_id)
        matched_chunks[key] = matched_chunks.get(key, 0) + 1
        snippets.setdefault(key, _build_snippet(chunk_text, content_query))
    return matched_chunks, snippets


def _apply_document_filters(
    stmt: Select,
    *,
    query: Optional[str],
    only_active: bool,
    content_query: Optional[str],
) -> Select:
    if only_active:
        stmt = stmt.where(SourceDocument.is_active.is_(True))
    if query:
        pattern = f"%{query}%"
        stmt = stmt.where(
            or_(
                SourceDocument.file_name.ilike(pattern),
                SourceDocument.doc_category.ilike(pattern),
            )
        )
    if content_query:
        content_pattern = f"%{content_query}%"
        content_doc_ids = (
            select(TextChunk.source_document_id)
            .where(TextChunk.chunk_text.ilike(content_pattern))
            .distinct()
        )
        stmt = stmt.where(SourceDocument.id.in_(content_doc_ids))
    return stmt


def _summary_from_document(
    doc: SourceDocument,
    *,
    chunk_count_by_doc: dict[str, int],
    page_count_by_doc: dict[str, int],
    matched_chunks_by_doc: dict[str, int],
    snippets_by_doc: dict[str, str],
) -> DocumentSummary:
    parsed_categories = parse_categories(doc.doc_category)
    return DocumentSummary(
        id=str(doc.id),
        file_name=doc.file_name,
        doc_year=doc.doc_year,
        doc_category=categories_label(doc.doc_category),
        categories=parsed_categories,
        is_active=doc.is_active,
        created_at=doc.created_at,
        chunk_count=chunk_count_by_doc.get(str(doc.id), 0),
        page_count=page_count_by_doc.get(str(doc.id), 0),
        matched_chunks=matched_chunks_by_doc.get(str(doc.id), 0),
        snippet=snippets_by_doc.get(str(doc.id)),
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    query: Optional[str] = Query(None, description="Search by file name or category"),
    content_query: Optional[str] = Query(None, description="Search by document content"),
    only_active: bool = True,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    normalized_query = _normalize_query(query)
    normalized_content_query = _normalize_query(content_query)

    base_stmt = _apply_document_filters(
        select(SourceDocument),
        query=normalized_query,
        only_active=only_active,
        content_query=normalized_content_query,
    )

    total = int((await session.execute(select(func.count()).select_from(base_stmt.subquery()))).scalar_one())
    documents = (
        await session.execute(
            base_stmt.order_by(SourceDocument.created_at.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()

    doc_ids = [doc.id for doc in documents]
    chunk_count_by_doc, page_count_by_doc = await _get_doc_stats(session, doc_ids)
    matched_chunks_by_doc, snippets_by_doc = await _get_content_matches(
        session,
        doc_ids,
        normalized_content_query,
    )

    return DocumentListResponse(
        total=total,
        items=[
            _summary_from_document(
                doc,
                chunk_count_by_doc=chunk_count_by_doc,
                page_count_by_doc=page_count_by_doc,
                matched_chunks_by_doc=matched_chunks_by_doc,
                snippets_by_doc=snippets_by_doc,
            )
            for doc in documents
        ],
    )


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    document = (await session.execute(select(SourceDocument).where(SourceDocument.id == document_id))).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunks = (
        await session.execute(
            select(TextChunk)
            .where(TextChunk.source_document_id == document_id)
            .order_by(TextChunk.page_number, TextChunk.chunk_index)
        )
    ).scalars().all()

    parsed_categories = parse_categories(document.doc_category)
    if not chunks:
        return DocumentDetail(
            id=str(document.id),
            file_name=document.file_name,
            doc_year=document.doc_year,
            doc_category=categories_label(document.doc_category),
            categories=parsed_categories,
            is_active=document.is_active,
            created_at=document.created_at,
            page_count=0,
            chunk_count=0,
            content_text="",
            pages=[],
        )

    pages_map: dict[int, list[str]] = {}
    for chunk in chunks:
        pages_map.setdefault(chunk.page_number, []).append(chunk.chunk_text.strip())

    ordered_pages = [
        DocumentPage(page_number=page_number, text="\n\n".join(texts).strip())
        for page_number, texts in sorted(pages_map.items())
    ]
    content_text = "\n\n".join(f"Страница {page.page_number + 1}\n{page.text}" for page in ordered_pages).strip()

    return DocumentDetail(
        id=str(document.id),
        file_name=document.file_name,
        doc_year=document.doc_year,
        doc_category=categories_label(document.doc_category),
        categories=parsed_categories,
        is_active=document.is_active,
        created_at=document.created_at,
        page_count=len(ordered_pages),
        chunk_count=len(chunks),
        content_text=content_text,
        pages=ordered_pages,
    )


@router.get("/{document_id}/search", response_model=list[DocumentMatch])
async def search_document_content(
    document_id: UUID,
    query: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> list[DocumentMatch]:
    document_exists = (await session.execute(select(SourceDocument.id).where(SourceDocument.id == document_id))).scalar_one_or_none()
    if document_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    normalized_query = query.strip()
    pattern = f"%{normalized_query}%"
    rows = (
        await session.execute(
            select(TextChunk.id, TextChunk.page_number, TextChunk.chunk_text)
            .where(
                TextChunk.source_document_id == document_id,
                TextChunk.chunk_text.ilike(pattern),
            )
            .order_by(TextChunk.page_number, TextChunk.chunk_index)
            .limit(limit)
        )
    ).all()

    return [
        DocumentMatch(
            chunk_id=str(chunk_id),
            page_number=page_number,
            snippet=_build_snippet(chunk_text, normalized_query),
        )
        for chunk_id, page_number, chunk_text in rows
    ]


@router.post("/upload", response_model=dict)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    doc_year: Optional[int] = Form(None),
    doc_category: Optional[str] = Form(None),
    is_active: bool = Form(True),
    actor=Depends(admin_required),
) -> dict:
    del actor
    authorization = request.headers.get("authorization")
    file_bytes = await file.read()

    try:
        return await post_multipart(
            "/upload",
            data={
                "doc_year": "" if doc_year is None else str(doc_year),
                "doc_category": normalize_categories(doc_category) or "",
                "is_active": str(is_active).lower(),
            },
            files={
                "file": (
                    file.filename or "document.bin",
                    file_bytes,
                    file.content_type or "application/octet-stream",
                )
            },
            authorization=authorization,
        )
    except UpstreamApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload) from exc


@router.patch("/{document_id}/status", response_model=AdminDocumentMutationResponse)
async def update_document_status(
    document_id: UUID,
    req: DocumentStatusUpdateRequest,
    session: AsyncSession = Depends(get_db),
    actor=Depends(admin_required),
) -> AdminDocumentMutationResponse:
    del actor
    result = await session.execute(
        update(SourceDocument)
        .where(SourceDocument.id == document_id)
        .values(is_active=req.is_active)
        .returning(SourceDocument.id, SourceDocument.is_active, SourceDocument.doc_category)
    )
    updated_row = result.one_or_none()
    if updated_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    await session.commit()
    return AdminDocumentMutationResponse(
        id=str(updated_row.id),
        status="updated",
        is_active=updated_row.is_active,
        doc_category=categories_label(updated_row.doc_category),
        categories=parse_categories(updated_row.doc_category),
    )


@router.patch("/{document_id}/categories", response_model=AdminDocumentMutationResponse)
async def update_document_categories(
    document_id: UUID,
    req: DocumentCategoriesUpdateRequest,
    session: AsyncSession = Depends(get_db),
    actor=Depends(admin_required),
) -> AdminDocumentMutationResponse:
    del actor
    normalized_doc_category = normalize_categories(req.categories)

    result = await session.execute(
        update(SourceDocument)
        .where(SourceDocument.id == document_id)
        .values(doc_category=normalized_doc_category)
        .returning(SourceDocument.id, SourceDocument.doc_category)
    )
    updated_row = result.one_or_none()
    if updated_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    await session.execute(
        update(TextChunk)
        .where(TextChunk.source_document_id == document_id)
        .values(doc_category=normalized_doc_category)
    )
    await session.commit()

    return AdminDocumentMutationResponse(
        id=str(updated_row.id),
        status="updated",
        doc_category=categories_label(updated_row.doc_category),
        categories=parse_categories(updated_row.doc_category),
    )


@router.delete("/{document_id}", response_model=AdminDocumentMutationResponse)
async def delete_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_db),
    actor=Depends(admin_required),
) -> AdminDocumentMutationResponse:
    del actor
    document_exists = (await session.execute(select(SourceDocument.id).where(SourceDocument.id == document_id))).scalar_one_or_none()
    if document_exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    await session.execute(delete(TextChunk).where(TextChunk.source_document_id == document_id))
    await session.execute(delete(SourceDocument).where(SourceDocument.id == document_id))
    await session.commit()

    return AdminDocumentMutationResponse(
        id=str(document_id),
        status="deleted",
    )
