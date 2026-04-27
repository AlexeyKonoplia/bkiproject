from app.rag.retrieval import extract_literal_terms, keyword_search, literal_search


class _FakeResult:
    def all(self):
        return []


class _FakeSession:
    def __init__(self):
        self.statement = None
        self.params = None

    async def execute(self, statement, params):
        self.statement = statement
        self.params = params
        return _FakeResult()


async def test_keyword_search_filters_out_zero_rank_rows():
    session = _FakeSession()

    result = await keyword_search(
        session,
        query_text="срок рассмотрения обращения",
        top_k=5,
    )

    assert result == []
    rendered_sql = str(session.statement)
    assert "tc.search_vector @@ q.ts_query" in rendered_sql
    assert "ts_rank_cd(tc.search_vector, q.ts_query)" in rendered_sql


def test_extract_literal_terms_keeps_technology_names():
    terms = extract_literal_terms("Что написано про SQLite и PostgreSQL в API?")

    assert "sqlite" in terms
    assert "postgresql" in terms
    assert "api" in terms


async def test_literal_search_uses_substring_matching_for_technology_terms():
    session = _FakeSession()

    result = await literal_search(
        session,
        query_text="Что написано про SQLite?",
        top_k=5,
    )

    assert result == []
    rendered_sql = str(session.statement)
    assert "lower(tc.chunk_text) LIKE '%' || CAST(term.term AS TEXT) || '%'" in rendered_sql
    assert session.params["literal_terms"] == ["sqlite"]


def test_extract_literal_terms_keeps_relevant_russian_terms():
    terms = extract_literal_terms(
        "Как следует оформлять заголовки в тексте, какой отступ, какое выравнивание?"
    )

    assert "заголовки" in terms
    assert "отступ" in terms
    assert "выравнивание" in terms
    assert "как" not in terms
    assert "какой" not in terms
    assert "следует" not in terms
