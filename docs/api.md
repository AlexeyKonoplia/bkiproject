# API

## Health
`GET /healthz`

Response:
```json
{ "status": "ok" }
```

## Auth (JWT)
`POST /auth/login`

Request:
```json
{ "username": "admin", "password": "..." }
```

Response:
```json
{ "access_token": "jwt...", "token_type": "bearer" }
```

## Admin bootstrap
`POST /admin/bootstrap`

JWT: `admin`

## Upload knowledge documents
`POST /upload`

JWT: `admin`

Content-Type: `multipart/form-data`

Fields:
- `file`: `PDF` or `DOCX`
- `doc_year`: integer (optional)
- `doc_category`: string (optional)
- `is_active`: boolean (default `true`)

Response:
```json
{
  "status": "indexed",
  "request_id": "uuid...",
  "source_document_id": "uuid...",
  "chunks_count": 123,
  "pages_count": 10
}
```

## Ask (RAG)
`POST /ask`

JWT: `user` (или `admin`)

Request:
```json
{
  "question": "string",
  "top_k": 5,
  "doc_year_from": 2024,
  "doc_year_to": 2025,
  "doc_category": "optional",
  "request_id": "optional"
}
```

Response:
```json
{
  "ask_event_id": "uuid...",
  "request_id": "uuid...",
  "answer_text": "string",
  "sources": [
    { "chunk_id": "uuid...", "file_name": "reglament.pdf", "page_number": 3 }
  ],
  "retrieved_chunks": 5
}
```

## Feedback
`POST /feedback`

JWT: `user` (или `admin`)

Request:
```json
{ "ask_event_id": "uuid...", "vote": 1, "comment": "optional" }
```

