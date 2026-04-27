from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.routes import ask as ask_route
from app.api.routes.tester_ui import HTML_PAGE
from app.rag.retrieval import RetrievedChunk
from app.security.jwt import Actor


@pytest.mark.asyncio
async def test_resolve_last_ask_chunks_uses_stored_sources(monkeypatch):
    ask_event_id = uuid4()
    expected_actor_user_id = uuid4()
    ask_event = SimpleNamespace(
        id=ask_event_id,
        request_id="req-1",
        query_text_redacted="masked question",
    )
    audit_log = SimpleNamespace(
        redacted_payload={
            "query": "masked question",
            "retrieved_sources": [
                {
                    "chunk_id": "11111111-1111-1111-1111-111111111111",
                    "file_name": "rules.pdf",
                    "page_number": 2,
                }
            ],
        }
    )
    expected_chunks = [
        RetrievedChunk(
            chunk_id="11111111-1111-1111-1111-111111111111",
            file_name="rules.pdf",
            page_number=2,
            chunk_text="Chunk text from stored ids",
        )
    ]

    async def fake_get_latest(session, *, actor_user_id):
        assert actor_user_id == expected_actor_user_id
        return ask_event

    async def fake_get_audit(session, *, request_id):
        assert request_id == "req-1"
        return audit_log

    async def fake_load_chunks(session, *, retrieved_sources):
        assert retrieved_sources == audit_log.redacted_payload["retrieved_sources"]
        return expected_chunks

    async def fake_fallback(session, *, ask_event, audit_payload):
        raise AssertionError("Fallback retrieval should not be used when stored sources exist")

    monkeypatch.setattr(ask_route, "_get_latest_ask_event", fake_get_latest)
    monkeypatch.setattr(ask_route, "_get_ask_audit_log", fake_get_audit)
    monkeypatch.setattr(ask_route, "_load_chunks_from_sources", fake_load_chunks)
    monkeypatch.setattr(ask_route, "_fallback_retrieve_last_chunks", fake_fallback)

    result = await ask_route.resolve_last_ask_chunks(object(), actor_user_id=expected_actor_user_id)

    assert result["ask_event_id"] == str(ask_event_id)
    assert result["request_id"] == "req-1"
    assert result["question_text"] == "masked question"
    assert result["retrieved_chunks"] == 1
    assert result["chunks"][0]["chunk_text"] == "Chunk text from stored ids"


@pytest.mark.asyncio
async def test_resolve_last_ask_chunks_falls_back_to_retrieval(monkeypatch):
    actor_user_id = uuid4()
    ask_event = SimpleNamespace(
        id=uuid4(),
        request_id="req-2",
        query_text_redacted="fallback question",
    )
    audit_log = SimpleNamespace(
        redacted_payload={
            "query": "fallback question",
            "top_k": 3,
            "doc_year_from": 2024,
            "doc_year_to": 2025,
            "doc_category": "rules",
        }
    )
    fallback_chunks = [
        RetrievedChunk(
            chunk_id="22222222-2222-2222-2222-222222222222",
            file_name="policy.pdf",
            page_number=7,
            chunk_text="Recovered by fallback retrieval",
        )
    ]

    async def fake_get_latest(session, *, actor_user_id):
        return ask_event

    async def fake_get_audit(session, *, request_id):
        return audit_log

    async def fake_load_chunks(session, *, retrieved_sources):
        assert retrieved_sources == []
        return []

    async def fake_fallback(session, *, ask_event, audit_payload):
        assert ask_event.request_id == "req-2"
        assert audit_payload["top_k"] == 3
        assert audit_payload["doc_year_from"] == 2024
        assert audit_payload["doc_year_to"] == 2025
        assert audit_payload["doc_category"] == "rules"
        return fallback_chunks

    monkeypatch.setattr(ask_route, "_get_latest_ask_event", fake_get_latest)
    monkeypatch.setattr(ask_route, "_get_ask_audit_log", fake_get_audit)
    monkeypatch.setattr(ask_route, "_load_chunks_from_sources", fake_load_chunks)
    monkeypatch.setattr(ask_route, "_fallback_retrieve_last_chunks", fake_fallback)

    result = await ask_route.resolve_last_ask_chunks(object(), actor_user_id=actor_user_id)

    assert result["retrieved_chunks"] == 1
    assert result["chunks"][0]["file_name"] == "policy.pdf"
    assert result["chunks"][0]["chunk_text"] == "Recovered by fallback retrieval"


@pytest.mark.asyncio
async def test_get_last_ask_chunks_endpoint_returns_response_model(monkeypatch):
    actor = Actor(user_id=uuid4(), username="tester", roles=["user"])
    expected_payload = {
        "ask_event_id": str(uuid4()),
        "request_id": "req-3",
        "question_text": "latest question",
        "chunks": [
            {
                "chunk_id": "33333333-3333-3333-3333-333333333333",
                "file_name": "guide.pdf",
                "page_number": 4,
                "chunk_text": "Latest chunk text",
            }
        ],
        "retrieved_chunks": 1,
    }

    async def fake_resolve(session, *, actor_user_id):
        assert actor_user_id == actor.user_id
        return expected_payload

    monkeypatch.setattr(ask_route, "resolve_last_ask_chunks", fake_resolve)

    response = await ask_route.get_last_ask_chunks(session=object(), actor=actor)

    assert response.request_id == "req-3"
    assert response.question_text == "latest question"
    assert response.retrieved_chunks == 1
    assert response.chunks[0].chunk_text == "Latest chunk text"


def test_tester_ui_contains_last_chunks_controls():
    assert 'id="last-chunks-btn"' in HTML_PAGE
    assert 'id="last-chunks-result"' in HTML_PAGE
    assert 'apiRequest("/ask/last-chunks"' in HTML_PAGE
