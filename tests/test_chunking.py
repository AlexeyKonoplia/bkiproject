from app.ingest.chunking import chunk_pages


def test_chunk_pages_page_numbers_and_indices():
    pages = ["Hello world. " * 50, "Second page text. " * 50]
    chunks = chunk_pages(pages, chunk_size=200, chunk_overlap=20)

    assert chunks, "Expected at least one chunk"
    assert all(c.page_number in (1, 2) for c in chunks)

    # chunk_index is sequential within each page (monotonic by construction)
    page1 = [c for c in chunks if c.page_number == 1]
    page2 = [c for c in chunks if c.page_number == 2]
    assert page1 == sorted(page1, key=lambda x: x.chunk_index)
    assert page2 == sorted(page2, key=lambda x: x.chunk_index)

