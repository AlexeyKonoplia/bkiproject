from __future__ import annotations

from typing import List

import fitz  # PyMuPDF

from app.ingest.chunking import sanitize_text


def extract_pdf_pages(file_bytes: bytes) -> List[str]:
    """
    Возвращает список текста по страницам PDF.
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages: List[str] = []
    for i in range(len(doc)):
        page = doc.load_page(i)
        text = page.get_text("text") or ""
        pages.append(sanitize_text(text).strip())
    return pages
