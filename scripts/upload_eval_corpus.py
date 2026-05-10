from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_DIR = ROOT / "eval_corpus"


def load_manifest(corpus_dir: Path) -> list[dict[str, Any]]:
    manifest_path = corpus_dir / "manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def login(client: httpx.Client, *, username: str, password: str) -> str:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def upload_document(
    client: httpx.Client,
    *,
    token: str,
    corpus_dir: Path,
    item: dict[str, Any],
) -> dict[str, Any]:
    relative_path = Path(*str(item["path"]).replace("\\", "/").split("/"))
    path = corpus_dir / relative_path
    with path.open("rb") as f:
        response = client.post(
            "/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "doc_year": str(item["doc_year"]),
                "doc_category": item["doc_category"],
                "description": item["description"],
                "is_active": str(bool(item.get("is_active", True))).lower(),
            },
            files={
                "file": (
                    item["file_name"],
                    f,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            timeout=180,
        )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", default=str(DEFAULT_CORPUS_DIR))
    parser.add_argument("--api-url", default="http://app:8000")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir)
    manifest = load_manifest(corpus_dir)

    with httpx.Client(base_url=args.api_url) as client:
        token = login(client, username=args.username, password=args.password)
        for item in manifest:
            result = upload_document(
                client,
                token=token,
                corpus_dir=corpus_dir,
                item=item,
            )
            print(f"{item['file_name']}: {result.get('status')} ({result.get('source_document_id')})")


if __name__ == "__main__":
    main()
