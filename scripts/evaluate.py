import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.db.session import SessionLocal
from app.ingest.embedder import embed_texts
from app.rag.llm import build_chat_llm
from app.rag.orchestrator import INSUFFICIENT_INFO_ANSWER, retrieve_relevant_chunks
from app.rag.prompts import build_user_prompt, system_prompt_russian
from app.rag.retrieval import RetrievedChunk, keyword_search, similarity_search
from evaluation_metrics import calculate_answer_quality, summarize_results, validate_results


def load_qa_set(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def build_context_for_llm(chunks: List[RetrievedChunk]) -> List[tuple[str, str]]:
    context_with_sources: List[tuple[str, str]] = []
    for i, c in enumerate(chunks, start=1):
        label = f"[source{i}] file={c.file_name}, page={c.page_number}"
        context_with_sources.append((label, c.chunk_text))
    return context_with_sources


async def generate_answer_from_chunks(
    *,
    question: str,
    chunks: List[RetrievedChunk],
    answer_mode: str,
) -> str:
    context_with_sources = build_context_for_llm(chunks)
    user_prompt = build_user_prompt(question, context_with_sources, answer_mode=answer_mode)
    sys_prompt = system_prompt_russian()

    llm = build_chat_llm()
    messages = [SystemMessage(sys_prompt), HumanMessage(user_prompt)]
    resp = llm.invoke(messages)
    return getattr(resp, "content", str(resp))


async def evaluate_one(
    session,
    row: Dict[str, Any],
    *,
    strategy: str,
    call_llm: bool,
    grounded_overlap_threshold: float,
    ignore_qa_filters: bool,
) -> Dict[str, Any]:
    question = row["question"]
    top_k = int(row.get("top_k", 5))
    doc_year_from = None if ignore_qa_filters else row.get("doc_year_from")
    doc_year_to = None if ignore_qa_filters else row.get("doc_year_to")
    doc_category = None if ignore_qa_filters else row.get("doc_category")
    answer_mode = row.get("answer_mode", "detailed")

    start = time.perf_counter()

    if strategy == "keyword":
        t0 = time.perf_counter()
        chunks = await keyword_search(
            session,
            query_text=question,
            top_k=top_k,
            doc_year_from=doc_year_from,
            doc_year_to=doc_year_to,
            doc_category=doc_category,
        )
        retrieval_ms = (time.perf_counter() - t0) * 1000
    elif strategy == "rag":
        t0 = time.perf_counter()
        q_vec = embed_texts(
            [question],
            embedding_model=settings.EMBEDDING_MODEL,
            ollama_base_url=settings.OLLAMA_BASE_URL,
        )[0]
        chunks = await similarity_search(
            session,
            query_vector=q_vec,
            top_k=top_k,
            doc_year_from=doc_year_from,
            doc_year_to=doc_year_to,
            doc_category=doc_category,
        )
        retrieval_ms = (time.perf_counter() - t0) * 1000
    elif strategy == "hybrid":
        t0 = time.perf_counter()
        chunks = await retrieve_relevant_chunks(
            session,
            question=question,
            top_k=top_k,
            doc_year_from=doc_year_from,
            doc_year_to=doc_year_to,
            doc_category=doc_category,
        )
        retrieval_ms = (time.perf_counter() - t0) * 1000
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    answer_text: Optional[str] = None
    llm_ms = None
    if call_llm and not chunks:
        answer_text = INSUFFICIENT_INFO_ANSWER
        llm_ms = 0.0
    elif call_llm:
        t1 = time.perf_counter()
        answer_text = await generate_answer_from_chunks(
            question=question,
            chunks=chunks,
            answer_mode=answer_mode,
        )
        llm_ms = (time.perf_counter() - t1) * 1000

    total_ms = (time.perf_counter() - start) * 1000

    expected_substrings = row.get("expected_answer_substrings") or []
    hit = None
    if expected_substrings and answer_text is not None:
        answer_lower = answer_text.lower()
        hit = any(str(sub).lower() in answer_lower for sub in expected_substrings)

    expected_source_files = row.get("expected_source_files") or []
    source_hit = None
    if expected_source_files:
        retrieved_files = {chunk.file_name for chunk in chunks}
        source_hit = any(file_name in retrieved_files for file_name in expected_source_files)

    result = {
        "id": row.get("id"),
        "strategy": strategy,
        "question": question,
        "top_k": top_k,
        "retrieved_chunks": len(chunks),
        "retrieval_ms": retrieval_ms,
        "llm_ms": llm_ms,
        "time_to_answer_ms": total_ms,
        "expected_hit": hit,
        "expected_source_hit": source_hit,
        "answer_text": answer_text if call_llm else None,
        "doc_year_from": doc_year_from,
        "doc_year_to": doc_year_to,
        "doc_category": doc_category,
        "answer_mode": answer_mode,
    }
    if call_llm:
        result.update(
            calculate_answer_quality(
                answer_text=answer_text,
                context_texts=[chunk.chunk_text for chunk in chunks],
                retrieved_chunks=len(chunks),
                grounded_overlap_threshold=grounded_overlap_threshold,
            )
        )

    return result


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa", type=str, default=str(ROOT / "tests" / "qa_set.jsonl"))
    parser.add_argument("--call-llm", action="store_true", help="Generate LLM answers")
    parser.add_argument("--out-dir", type=str, default=str(ROOT / "analysis"))
    parser.add_argument("--strategy", choices=["keyword", "rag", "hybrid", "all"], default="all")
    parser.add_argument(
        "--ignore-qa-filters",
        action="store_true",
        help="Ignore doc_year/doc_category filters from QA rows and search all active documents",
    )
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--validate-strategy", choices=["keyword", "rag", "hybrid"], default="hybrid")
    parser.add_argument("--min-expected-hit-rate", type=float, default=None)
    parser.add_argument("--min-expected-source-hit-rate", type=float, default=None)
    parser.add_argument("--min-avg-retrieved-chunks", type=float, default=None)
    parser.add_argument("--min-retrieval-hit-rate", type=float, default=None)
    parser.add_argument("--max-avg-time-to-answer-ms", type=float, default=None)
    parser.add_argument("--grounded-overlap-threshold", type=float, default=0.2)
    parser.add_argument("--min-answer-nonempty-rate", type=float, default=None)
    parser.add_argument("--max-answer-too-short-rate", type=float, default=None)
    parser.add_argument("--min-answer-context-overlap-avg", type=float, default=None)
    parser.add_argument("--min-answer-source-ref-rate", type=float, default=None)
    parser.add_argument("--min-answer-valid-source-ref-rate", type=float, default=None)
    parser.add_argument("--min-answer-grounded-rate", type=float, default=None)
    args = parser.parse_args()

    qa_path = Path(args.qa)
    rows = load_qa_set(qa_path)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"results_{ts}.json"

    results: List[Dict[str, Any]] = []
    strategies = ["keyword", "rag", "hybrid"] if args.strategy == "all" else [args.strategy]

    async with SessionLocal() as session:
        for row in rows:
            for strategy in strategies:
                results.append(
                    await evaluate_one(
                        session,
                        row,
                        strategy=strategy,
                        call_llm=args.call_llm,
                        grounded_overlap_threshold=args.grounded_overlap_threshold,
                        ignore_qa_filters=args.ignore_qa_filters,
                    )
                )

    payload = {
        "settings": {
            "llm_model": settings.LLM_MODEL,
            "embedding_model": settings.EMBEDDING_MODEL,
            "llm_num_ctx": settings.LLM_NUM_CTX,
            "llm_num_predict": settings.LLM_NUM_PREDICT,
            "enable_self_correction": settings.ENABLE_SELF_CORRECTION,
        },
        "summary": summarize_results(results),
        "results": results,
    }
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote results to {out_file}")

    if args.validate:
        failures = validate_results(
            results,
            min_expected_hit_rate=args.min_expected_hit_rate,
            min_expected_source_hit_rate=args.min_expected_source_hit_rate,
            max_avg_time_to_answer_ms=args.max_avg_time_to_answer_ms,
            strategy=args.validate_strategy,
            min_avg_retrieved_chunks=args.min_avg_retrieved_chunks,
            min_retrieval_hit_rate=args.min_retrieval_hit_rate,
            min_answer_nonempty_rate=args.min_answer_nonempty_rate,
            max_answer_too_short_rate=args.max_answer_too_short_rate,
            min_answer_context_overlap_avg=args.min_answer_context_overlap_avg,
            min_answer_source_ref_rate=args.min_answer_source_ref_rate,
            min_answer_valid_source_ref_rate=args.min_answer_valid_source_ref_rate,
            min_answer_grounded_rate=args.min_answer_grounded_rate,
        )
        if failures:
            print("Validation failed:")
            for failure in failures:
                print(f"- {failure}")
            raise SystemExit(1)
        print("Validation passed")


if __name__ == "__main__":
    asyncio.run(main())
