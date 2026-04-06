from __future__ import annotations

from typing import List

import fitz  # PyMuPDF


def extract_pdf_pages(file_bytes: bytes) -> List[str]:
    """
    Возвращает список текста по страницам.
    Нумерация страниц будет соответствовать index+1 (1-based) при дальнейшем сохранении.
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages: List[str] = []
    for i in range(len(doc)):
        page = doc.load_page(i)
        text = page.get_text("text") or ""
        # Небольшая нормализация переносов
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        pages.append(text)
    return pages


