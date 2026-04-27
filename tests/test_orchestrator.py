from app.rag.orchestrator import merge_retrieved_chunks
from app.rag.retrieval import RetrievedChunk


def _chunk(chunk_id: str, page_number: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        source_document_id="doc-1",
        file_name="policy.pdf",
        page_number=page_number,
        chunk_text=f"chunk {chunk_id}",
    )


def test_merge_retrieved_chunks_prioritizes_keyword_hits_without_losing_semantic_recall():
    semantic = [_chunk("s1", 1), _chunk("s2", 2), _chunk("s3", 3)]
    keyword = [_chunk("k1", 10), _chunk("k2", 11)]
    literal = [_chunk("l1", 100)]

    merged = merge_retrieved_chunks(
        literal_chunks=literal,
        semantic_chunks=semantic,
        keyword_chunks=keyword,
        top_k=4,
    )

    assert [chunk.chunk_id for chunk in merged] == ["l1", "k1", "s1", "k2"]


def test_merge_retrieved_chunks_deduplicates_between_search_strategies():
    semantic = [_chunk("shared", 1), _chunk("s2", 2)]
    keyword = [_chunk("shared", 1), _chunk("k2", 20)]
    literal = [_chunk("shared", 1), _chunk("l2", 30)]

    merged = merge_retrieved_chunks(
        literal_chunks=literal,
        semantic_chunks=semantic,
        keyword_chunks=keyword,
        top_k=4,
    )

    assert [chunk.chunk_id for chunk in merged] == ["shared", "l2", "k2", "s2"]
