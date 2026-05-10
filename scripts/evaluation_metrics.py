from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional


SOURCE_REF_RE = re.compile(r"\[source(\d+)\]", re.IGNORECASE)

RU_STOPWORDS = {
    "без",
    "был",
    "была",
    "были",
    "быть",
    "вам",
    "вас",
    "все",
    "для",
    "его",
    "если",
    "или",
    "как",
    "над",
    "она",
    "они",
    "при",
    "про",
    "так",
    "что",
    "это",
}

EN_STOPWORDS = {
    "and",
    "are",
    "but",
    "for",
    "from",
    "not",
    "the",
    "this",
    "that",
    "with",
}

STOPWORDS = RU_STOPWORDS | EN_STOPWORDS


def _tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    current: list[str] = []

    for char in text or "":
        if char.isalnum():
            current.append(char.casefold())
            continue

        if len(current) >= 3:
            token = "".join(current)
            if token not in STOPWORDS:
                tokens.add(token)
        current = []

    if len(current) >= 3:
        token = "".join(current)
        if token not in STOPWORDS:
            tokens.add(token)

    return tokens


def calculate_answer_quality(
    *,
    answer_text: Optional[str],
    context_texts: Iterable[str],
    retrieved_chunks: int,
    grounded_overlap_threshold: float = 0.2,
) -> Dict[str, Any]:
    """Deterministic answer quality proxy for RAG evaluation.

    The metric intentionally does not judge whether the answer is complete. It
    checks whether the generated text looks grounded in retrieved context rather
    than being arbitrary fluent text.
    """

    answer = (answer_text or "").strip()
    answer_tokens = _tokenize(answer)
    context_tokens = _tokenize("\n".join(context_texts))
    source_refs = [int(match.group(1)) for match in SOURCE_REF_RE.finditer(answer)]

    overlap = None
    if answer_tokens:
        overlap = len(answer_tokens & context_tokens) / len(answer_tokens)

    invalid_source_refs = [
        source_number
        for source_number in source_refs
        if source_number < 1 or source_number > max(retrieved_chunks, 0)
    ]

    is_insufficient_answer = "insufficient information" in answer.casefold() or "информац" in answer.casefold() and "недостат" in answer.casefold()
    is_nonempty = bool(answer)
    is_too_short = not is_insufficient_answer and 0 < len(answer_tokens) < 5
    has_source_ref = bool(source_refs)
    source_refs_valid = None if not has_source_ref else not invalid_source_refs
    is_grounded = (
        is_insufficient_answer
        or bool(
            answer_tokens
            and context_tokens
            and overlap is not None
            and overlap >= grounded_overlap_threshold
        )
    )

    return {
        "answer_nonempty": is_nonempty,
        "answer_too_short": is_too_short,
        "answer_token_count": len(answer_tokens),
        "answer_context_overlap": overlap,
        "answer_has_source_ref": has_source_ref,
        "answer_source_refs_valid": source_refs_valid,
        "answer_invalid_source_refs": invalid_source_refs,
        "answer_grounded": is_grounded,
        "answer_insufficient": is_insufficient_answer,
    }


def summarize_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_strategy: Dict[str, Dict[str, Any]] = {}
    for row in results:
        strategy = row["strategy"]
        item = by_strategy.setdefault(
            strategy,
            {
                "cases": 0,
                "avg_retrieved_chunks": 0.0,
                "retrieval_hit_rate": None,
                "avg_retrieval_ms": 0.0,
                "avg_llm_ms": None,
                "avg_time_to_answer_ms": 0.0,
                "expected_hit_rate": None,
                "expected_source_hit_rate": None,
                "answer_nonempty_rate": None,
                "answer_too_short_rate": None,
                "answer_context_overlap_avg": None,
                "answer_source_ref_rate": None,
                "answer_valid_source_ref_rate": None,
                "answer_grounded_rate": None,
            },
        )
        item["cases"] += 1
        item["avg_retrieved_chunks"] += row["retrieved_chunks"]
        item["avg_retrieval_ms"] += row["retrieval_ms"]
        item["avg_time_to_answer_ms"] += row["time_to_answer_ms"]

    for strategy, item in by_strategy.items():
        strategy_rows = [row for row in results if row["strategy"] == strategy]
        cases = item["cases"]
        item["avg_retrieved_chunks"] = item["avg_retrieved_chunks"] / cases
        item["retrieval_hit_rate"] = sum(
            1 for row in strategy_rows if row["retrieved_chunks"] > 0
        ) / cases
        item["avg_retrieval_ms"] = item["avg_retrieval_ms"] / cases
        item["avg_time_to_answer_ms"] = item["avg_time_to_answer_ms"] / cases

        llm_rows = [row for row in strategy_rows if row["llm_ms"] is not None]
        if llm_rows:
            item["avg_llm_ms"] = sum(row["llm_ms"] for row in llm_rows) / len(llm_rows)

        expected_rows = [row for row in strategy_rows if row["expected_hit"] is not None]
        if expected_rows:
            item["expected_hit_rate"] = sum(1 for row in expected_rows if row["expected_hit"]) / len(expected_rows)

        source_rows = [row for row in strategy_rows if row["expected_source_hit"] is not None]
        if source_rows:
            item["expected_source_hit_rate"] = sum(1 for row in source_rows if row["expected_source_hit"]) / len(source_rows)

        answer_rows = [row for row in strategy_rows if row.get("answer_nonempty") is not None]
        if answer_rows:
            item["answer_nonempty_rate"] = sum(1 for row in answer_rows if row["answer_nonempty"]) / len(answer_rows)

            grounded_answer_rows = [
                row
                for row in answer_rows
                if row.get("retrieved_chunks", 0) > 0
            ]
            if grounded_answer_rows:
                item["answer_too_short_rate"] = sum(
                    1 for row in grounded_answer_rows if row["answer_too_short"]
                ) / len(grounded_answer_rows)
                item["answer_source_ref_rate"] = sum(
                    1 for row in grounded_answer_rows if row["answer_has_source_ref"]
                ) / len(grounded_answer_rows)
                item["answer_grounded_rate"] = sum(
                    1 for row in grounded_answer_rows if row["answer_grounded"]
                ) / len(grounded_answer_rows)

            source_ref_rows = [
                row
                for row in grounded_answer_rows
                if row.get("answer_source_refs_valid") is not None
            ]
            if source_ref_rows:
                item["answer_valid_source_ref_rate"] = sum(
                    1 for row in source_ref_rows if row["answer_source_refs_valid"]
                ) / len(source_ref_rows)

            overlap_rows = [
                row
                for row in grounded_answer_rows
                if row.get("answer_context_overlap") is not None
            ]
            if overlap_rows:
                item["answer_context_overlap_avg"] = sum(
                    row["answer_context_overlap"] for row in overlap_rows
                ) / len(overlap_rows)

    return {"by_strategy": by_strategy}


def validate_results(
    results: List[Dict[str, Any]],
    *,
    min_expected_hit_rate: Optional[float],
    min_expected_source_hit_rate: Optional[float],
    max_avg_time_to_answer_ms: Optional[float],
    strategy: str,
    min_avg_retrieved_chunks: Optional[float] = None,
    min_retrieval_hit_rate: Optional[float] = None,
    min_answer_nonempty_rate: Optional[float] = None,
    max_answer_too_short_rate: Optional[float] = None,
    min_answer_context_overlap_avg: Optional[float] = None,
    min_answer_source_ref_rate: Optional[float] = None,
    min_answer_valid_source_ref_rate: Optional[float] = None,
    min_answer_grounded_rate: Optional[float] = None,
) -> List[str]:
    strategy_summary = summarize_results(results)["by_strategy"].get(strategy)
    if not strategy_summary:
        return [f"No results for strategy '{strategy}'"]

    failures: List[str] = []
    if min_expected_hit_rate is not None:
        hit_rate = strategy_summary["expected_hit_rate"]
        if hit_rate is None:
            failures.append("No expected_answer_substrings checks were available")
        elif hit_rate < min_expected_hit_rate:
            failures.append(
                f"expected_hit_rate={hit_rate:.3f} below threshold {min_expected_hit_rate:.3f}"
            )

    if min_expected_source_hit_rate is not None:
        source_hit_rate = strategy_summary["expected_source_hit_rate"]
        if source_hit_rate is None:
            failures.append("No expected_source_files checks were available")
        elif source_hit_rate < min_expected_source_hit_rate:
            failures.append(
                f"expected_source_hit_rate={source_hit_rate:.3f} below threshold {min_expected_source_hit_rate:.3f}"
            )

    if max_avg_time_to_answer_ms is not None:
        avg_ms = strategy_summary["avg_time_to_answer_ms"]
        if avg_ms > max_avg_time_to_answer_ms:
            failures.append(
                f"avg_time_to_answer_ms={avg_ms:.1f} above threshold {max_avg_time_to_answer_ms:.1f}"
            )

    if min_avg_retrieved_chunks is not None:
        avg_retrieved = strategy_summary["avg_retrieved_chunks"]
        if avg_retrieved < min_avg_retrieved_chunks:
            failures.append(
                f"avg_retrieved_chunks={avg_retrieved:.3f} below threshold {min_avg_retrieved_chunks:.3f}"
            )

    if min_retrieval_hit_rate is not None:
        retrieval_hit_rate = strategy_summary["retrieval_hit_rate"]
        if retrieval_hit_rate < min_retrieval_hit_rate:
            failures.append(
                f"retrieval_hit_rate={retrieval_hit_rate:.3f} below threshold {min_retrieval_hit_rate:.3f}"
            )

    answer_thresholds = [
        ("answer_nonempty_rate", min_answer_nonempty_rate, "below", "min"),
        ("answer_context_overlap_avg", min_answer_context_overlap_avg, "below", "min"),
        ("answer_source_ref_rate", min_answer_source_ref_rate, "below", "min"),
        ("answer_valid_source_ref_rate", min_answer_valid_source_ref_rate, "below", "min"),
        ("answer_grounded_rate", min_answer_grounded_rate, "below", "min"),
        ("answer_too_short_rate", max_answer_too_short_rate, "above", "max"),
    ]
    for metric_name, threshold, direction, threshold_kind in answer_thresholds:
        if threshold is None:
            continue

        actual = strategy_summary.get(metric_name)
        if actual is None:
            failures.append(f"No generated answer checks were available for {metric_name}")
            continue

        failed = actual < threshold if threshold_kind == "min" else actual > threshold
        if failed:
            failures.append(
                f"{metric_name}={actual:.3f} {direction} threshold {threshold:.3f}"
            )

    return failures
