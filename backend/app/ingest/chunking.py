from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass(frozen=True)
class PageChunk:
    page_number: int  # 1-based
    chunk_index: int  # sequential within page
    chunk_text: str


def chunk_pages(
    pages: Iterable[str],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> List[PageChunk]:
    """
    Разбивает страницы отдельно, чтобы цитирование могло возвращать `page_number`.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )

    out: List[PageChunk] = []
    for idx, page_text in enumerate(pages):
        page_number = idx + 1  # 1-based
        normalized = (page_text or "").strip()
        if not normalized:
            continue

        chunks = splitter.split_text(normalized)
        for c_idx, chunk_text in enumerate(chunks):
            normalized_chunk = (chunk_text or "").strip()
            if not normalized_chunk:
                continue
            out.append(PageChunk(page_number=page_number, chunk_index=c_idx, chunk_text=normalized_chunk))
    return out


