import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evaluation_metrics import calculate_answer_quality, summarize_results, validate_results


def _result(**overrides):
    row = {
        "strategy": "hybrid",
        "retrieved_chunks": 3,
        "retrieval_ms": 100.0,
        "llm_ms": 900.0,
        "time_to_answer_ms": 1000.0,
        "expected_hit": True,
        "expected_source_hit": True,
        "answer_nonempty": True,
        "answer_too_short": False,
        "answer_context_overlap": 0.8,
        "answer_has_source_ref": True,
        "answer_source_refs_valid": True,
        "answer_grounded": True,
    }
    row.update(overrides)
    return row


def test_summarize_results_groups_metrics_by_strategy():
    summary = summarize_results([_result(), _result(time_to_answer_ms=500.0)])

    hybrid = summary["by_strategy"]["hybrid"]
    assert hybrid["cases"] == 2
    assert hybrid["avg_time_to_answer_ms"] == 750.0
    assert hybrid["retrieval_hit_rate"] == 1.0
    assert hybrid["expected_hit_rate"] == 1.0
    assert hybrid["answer_context_overlap_avg"] == 0.8
    assert hybrid["answer_grounded_rate"] == 1.0


def test_validate_results_reports_threshold_failures():
    failures = validate_results(
        [_result(expected_hit=False, time_to_answer_ms=1200.0)],
        min_expected_hit_rate=1.0,
        min_expected_source_hit_rate=1.0,
        max_avg_time_to_answer_ms=1000.0,
        strategy="hybrid",
    )

    assert len(failures) == 2
    assert "expected_hit_rate" in failures[0]
    assert "avg_time_to_answer_ms" in failures[1]


def test_calculate_answer_quality_marks_grounded_cited_answer():
    quality = calculate_answer_quality(
        answer_text="Документ поддерживает загрузку pdf и docx файлов [source1].",
        context_texts=["Система поддерживает загрузку документов в форматах PDF и DOCX."],
        retrieved_chunks=1,
        grounded_overlap_threshold=0.2,
    )

    assert quality["answer_nonempty"] is True
    assert quality["answer_has_source_ref"] is True
    assert quality["answer_source_refs_valid"] is True
    assert quality["answer_grounded"] is True
    assert quality["answer_context_overlap"] > 0.2


def test_calculate_answer_quality_tokenizes_cyrillic_text():
    quality = calculate_answer_quality(
        answer_text="Документ поддерживает загрузку файлов PDF и DOCX [source1].",
        context_texts=["Система поддерживает загрузку документов в форматах PDF и DOCX."],
        retrieved_chunks=1,
        grounded_overlap_threshold=0.2,
    )

    assert quality["answer_token_count"] >= 5
    assert quality["answer_context_overlap"] > 0.2


def test_calculate_answer_quality_does_not_mark_insufficient_answer_as_too_short():
    quality = calculate_answer_quality(
        answer_text="Информация недостаточна для ответа [source1].",
        context_texts=["В документе описаны только правила загрузки файлов."],
        retrieved_chunks=1,
        grounded_overlap_threshold=0.2,
    )

    assert quality["answer_insufficient"] is True
    assert quality["answer_too_short"] is False
    assert quality["answer_grounded"] is True


def test_validate_results_reports_ungrounded_answers():
    failures = validate_results(
        [
            _result(
                answer_context_overlap=0.05,
                answer_has_source_ref=False,
                answer_source_refs_valid=False,
                answer_grounded=False,
            )
        ],
        min_expected_hit_rate=None,
        min_expected_source_hit_rate=None,
        max_avg_time_to_answer_ms=None,
        strategy="hybrid",
        min_retrieval_hit_rate=1.0,
        min_answer_context_overlap_avg=0.2,
        min_answer_source_ref_rate=1.0,
        min_answer_grounded_rate=1.0,
    )

    assert len(failures) == 3
    assert "answer_context_overlap_avg" in failures[0]
    assert "answer_source_ref_rate" in failures[1]
    assert "answer_grounded_rate" in failures[2]


def test_validate_results_reports_missing_retrieval():
    failures = validate_results(
        [_result(retrieved_chunks=0)],
        min_expected_hit_rate=None,
        min_expected_source_hit_rate=None,
        max_avg_time_to_answer_ms=None,
        strategy="hybrid",
        min_avg_retrieved_chunks=1.0,
        min_retrieval_hit_rate=1.0,
    )

    assert len(failures) == 2
    assert "avg_retrieved_chunks" in failures[0]
    assert "retrieval_hit_rate" in failures[1]
