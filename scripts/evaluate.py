import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Make `app` importable when running from repo root
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.db.session import SessionLocal
from app.ingest.embedder import embed_texts
from app.rag.prompts import build_user_prompt, system_prompt_russian
from app.rag.retrieval import RetrievedChunk, keyword_search, similarity_search
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage


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
) -> str:
    context_with_sources = build_context_for_llm(chunks)
    user_prompt = build_user_prompt(question, context_with_sources)
    sys_prompt = system_prompt_russian()

    llm = ChatOllama(
        model=settings.LLM_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0.0,
    )
    messages = [SystemMessage(sys_prompt), HumanMessage(user_prompt)]
    resp = llm.invoke(messages)
    return getattr(resp, "content", str(resp))


async def evaluate_one(
    session,
    row: Dict[str, Any],
    *,
    strategy: str,
    call_llm: bool,
) -> Dict[str, Any]:
    question = row["question"]
    top_k = int(row.get("top_k", 5))
    doc_year_from = row.get("doc_year_from")
    doc_year_to = row.get("doc_year_to")
    doc_category = row.get("doc_category")

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
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    answer_text: Optional[str] = None
    llm_ms = None
    if call_llm:
        t1 = time.perf_counter()
        answer_text = await generate_answer_from_chunks(question=question, chunks=chunks)
        llm_ms = (time.perf_counter() - t1) * 1000

    total_ms = (time.perf_counter() - start) * 1000

    expected_substrings = row.get("expected_answer_substrings") or []
    hit = None
    if expected_substrings and answer_text is not None:
        hit = any(sub in answer_text for sub in expected_substrings)

    return {
        "id": row.get("id"),
        "strategy": strategy,
        "question": question,
        "top_k": top_k,
        "retrieved_chunks": len(chunks),
        "retrieval_ms": retrieval_ms,
        "llm_ms": llm_ms,
        "time_to_answer_ms": total_ms,
        "expected_hit": hit,
        "answer_text": answer_text if call_llm else None,
        "doc_year_from": doc_year_from,
        "doc_year_to": doc_year_to,
        "doc_category": doc_category,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa", type=str, default=str(ROOT / "tests" / "qa_set.jsonl"))
    parser.add_argument("--call-llm", action="store_true", help="Выполнить генерацию ответов LLM (дороже)")
    parser.add_argument("--out-dir", type=str, default=str(ROOT / "analysis"))
    args = parser.parse_args()

    qa_path = Path(args.qa)
    rows = load_qa_set(qa_path)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"results_{ts}.json"

    results: List[Dict[str, Any]] = []

    async with SessionLocal() as session:
        for row in rows:
            results.append(
                await evaluate_one(session, row, strategy="keyword", call_llm=args.call_llm)
            )
            results.append(
                await evaluate_one(session, row, strategy="rag", call_llm=args.call_llm)
            )

    out_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote results to {out_file}")


if __name__ == "__main__":
    asyncio.run(main())

