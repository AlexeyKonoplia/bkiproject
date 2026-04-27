from __future__ import annotations

from io import BytesIO
from typing import List

from docx import Document

from app.ingest.chunking import sanitize_text


def extract_docx_pages(file_bytes: bytes) -> List[str]:
    """
    DOCX не имеет явной разметки страниц; для MVP считаем, что документ = 1 страница.
    """
    doc = Document(BytesIO(file_bytes))
    parts: List[str] = []
    for p in doc.paragraphs:
        cleaned = sanitize_text(p.text).strip()
        if cleaned:
            parts.append(cleaned)
    text = sanitize_text("\n".join(parts)).strip()
    return [text]
