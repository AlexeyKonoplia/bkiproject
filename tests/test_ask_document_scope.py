from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.routes import ask as ask_route
from app.rag.retrieval import RetrievedChunk


@pytest.mark.asyncio
async def test_fallback_retrieve_last_chunks_forwards_source_document_id(monkeypatch):
    expected_source_document_id = uuid4()
    ask_event = SimpleNamespace(query_text_redacted="question from audit")
    audit_payload = {
        "query": "question from audit",
        "top_k": 4,
        "source_document_id": str(expected_source_document_id),
        "doc_year_from": 2021,
        "doc_year_to": 2024,
        "doc_category": "manuals",
    }

    async def fake_retrieve_relevant_chunks(
        session,
        *,
        question,
        top_k,
        source_document_id,
        doc_year_from,
        doc_year_to,
        doc_category,
    ):
        assert question == "question from audit"
        assert top_k == 4
        assert source_document_id == expected_source_document_id
        assert doc_year_from == 2021
        assert doc_year_to == 2024
        assert doc_category == "manuals"
        return [
            RetrievedChunk(
                chunk_id="44444444-4444-4444-4444-444444444444",
                file_name="manual.pdf",
                page_number=1,
                chunk_text="Scoped chunk",
            )
        ]

    monkeypatch.setattr(ask_route, "retrieve_relevant_chunks", fake_retrieve_relevant_chunks)

    result = await ask_route._fallback_retrieve_last_chunks(
        object(),
        ask_event=ask_event,
        audit_payload=audit_payload,
    )

    assert result[0].file_name == "manual.pdf"
