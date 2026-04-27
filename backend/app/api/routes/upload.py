from datetime import datetime, timezone
import hashlib
import os
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select

from app.config import settings
from app.db.models import AuditLog, SourceDocument, TextChunk
from app.db.session import get_db
from app.documents.categories import normalize_categories
from app.ingest.chunking import chunk_pages, sanitize_text
from app.ingest.embedder import embed_texts
from app.ingest.parser_docx import extract_docx_pages
from app.ingest.parser_pdf import extract_pdf_pages
from app.security.redaction import redact_text
from app.security.rbac import admin_required

router = APIRouter(tags=["upload"])


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _read_all(upload: UploadFile) -> bytes:
    # UploadFile.read() уже асинхронен; используем отдельную обертку ради читаемости.
    return await upload.read()


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    doc_year: Optional[int] = Form(None),
    doc_category: Optional[str] = Form(None),
    is_active: bool = Form(True),
    session=Depends(get_db),
    actor=Depends(admin_required),
):
    data = await _read_all(file)
    if not data:
        return {"error": "Empty file"}

    normalized_doc_category = normalize_categories(doc_category)

    filename = sanitize_text(file.filename or "uploaded")
    redacted_filename = redact_text(filename)
    ext = os.path.splitext(filename.lower())[1]
    if ext not in {".pdf", ".docx"}:
        return {"error": "Unsupported file type", "supported": [".pdf", ".docx"]}

    file_hash = _sha256_hex(data)
    request_id = str(uuid4())

    existing = await session.execute(select(SourceDocument).where(SourceDocument.file_hash == file_hash))
    existing_doc = existing.scalar_one_or_none()
    if existing_doc is not None:
        session.add(
            AuditLog(
                actor_user_id=actor.user_id,
                created_at=datetime.now(timezone.utc),
                action="upload",
                request_id=request_id,
                redacted_payload={
                    "file_name": redacted_filename,
                    "file_hash": file_hash,
                    "doc_year": doc_year,
                    "doc_category": normalized_doc_category,
                },
                status="already_indexed",
            )
        )
        await session.commit()
        return {
            "status": "already_indexed",
            "request_id": request_id,
            "source_document_id": str(existing_doc.id),
            "file_name": existing_doc.file_name,
        }

    if ext == ".pdf":
        pages = extract_pdf_pages(data)
    else:
        pages = extract_docx_pages(data)

    page_chunks = chunk_pages(
        pages,
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )

    if not page_chunks:
        return {"error": "No text found to index"}

    source_doc = SourceDocument(
        file_name=filename,
        file_hash=file_hash,
        doc_year=doc_year,
        doc_category=normalized_doc_category,
        is_active=is_active,
        uploaded_by=actor.user_id,
    )
    session.add(source_doc)
    await session.flush()  # get source_doc.id

    texts = [pc.chunk_text for pc in page_chunks]

    # Batched embeddings to reduce memory spikes / shorten long calls.
    vectors: list[list[float]] = []
    batch_size = int(os.getenv("EMBED_BATCH_SIZE", "64"))
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i : i + batch_size]
        vectors.extend(
            embed_texts(
                batch_texts,
                embedding_model=settings.EMBEDDING_MODEL,
                ollama_base_url=settings.OLLAMA_BASE_URL,
            )
        )

    if len(vectors) != len(page_chunks):
        return {"error": "Embedding count mismatch"}

    # Create chunks
    chunk_objs: list[TextChunk] = []
    for pc, vec in zip(page_chunks, vectors):
        if len(vec) != settings.EMBEDDING_DIM:
            return {
                "error": "Embedding dimension mismatch",
                "expected": settings.EMBEDDING_DIM,
                "got": len(vec),
            }
        chunk_objs.append(
            TextChunk(
                source_document_id=source_doc.id,
                page_number=pc.page_number,
                chunk_index=pc.chunk_index,
                chunk_text=pc.chunk_text,
                section_title=None,
                doc_year=doc_year,
                doc_category=normalized_doc_category,
                embedding=vec,
            )
        )

    session.add_all(chunk_objs)
    await session.flush()

    session.add(
        AuditLog(
            actor_user_id=actor.user_id,
            created_at=datetime.now(timezone.utc),
            action="upload",
            request_id=request_id,
            redacted_payload={
                "file_name": redacted_filename,
                "file_hash": file_hash,
                "doc_year": doc_year,
                "doc_category": normalized_doc_category,
                "chunks_count": len(chunk_objs),
                "pages_count": len(pages),
            },
            status="indexed",
        )
    )
    await session.commit()
    return {
        "status": "indexed",
        "request_id": request_id,
        "source_document_id": str(source_doc.id),
        "chunks_count": len(chunk_objs),
        "pages_count": len(pages),
    }

