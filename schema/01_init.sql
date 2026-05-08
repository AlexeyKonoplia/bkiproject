-- PostgreSQL init schema for on-premise RAG
-- Target vector dimension: 768 (default for `nomic-embed-text`)

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username text NOT NULL UNIQUE,
  password_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_roles (
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, role_id)
);

-- Source documents metadata
CREATE TABLE IF NOT EXISTS source_documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  file_name text NOT NULL,
  file_hash text UNIQUE,
  description text,
  doc_year integer,
  doc_category text,
  is_active boolean NOT NULL DEFAULT true,
  uploaded_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Text chunks with embeddings (pgvector)
CREATE TABLE IF NOT EXISTS text_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_document_id uuid NOT NULL REFERENCES source_documents(id) ON DELETE CASCADE,
  page_number integer NOT NULL,
  chunk_index integer NOT NULL,
  chunk_text text NOT NULL,
  section_title text,

  doc_year integer,
  doc_category text,

  embedding vector(768) NOT NULL,

  -- For keyword baseline retrieval (AS-IS mode)
  search_vector tsvector GENERATED ALWAYS AS (to_tsvector('russian', chunk_text)) STORED,

  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_document_id, page_number, chunk_index)
);

-- RAG request/response tracking
CREATE TABLE IF NOT EXISTS ask_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),

  request_id text NOT NULL,
  query_text_redacted text NOT NULL,
  model text,
  status text NOT NULL DEFAULT 'ok'
);

CREATE TABLE IF NOT EXISTS feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ask_event_id uuid NOT NULL REFERENCES ask_events(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  vote smallint NOT NULL,
  comment text,
  CHECK (vote IN (-1, 1))
);

-- Append-only audit log (application-level inserts; no UPDATE usage)
CREATE TABLE IF NOT EXISTS audit_log (
  id bigserial PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  action text NOT NULL,
  request_id text,
  redacted_payload jsonb NOT NULL,
  status text
);

-- Indexes for retrieval
CREATE INDEX IF NOT EXISTS text_chunks_doc_year_idx ON text_chunks(doc_year);
CREATE INDEX IF NOT EXISTS text_chunks_doc_category_idx ON text_chunks(doc_category);
CREATE INDEX IF NOT EXISTS text_chunks_search_vector_gin_idx ON text_chunks USING GIN (search_vector);

-- Cosine similarity index for pgvector
-- NOTE: pgvector chooses the appropriate operator class; we use cosine distance downstream.
CREATE INDEX IF NOT EXISTS text_chunks_embedding_hnsw_idx
ON text_chunks USING hnsw (embedding vector_cosine_ops);

-- Source documents filters
CREATE INDEX IF NOT EXISTS source_documents_active_year_idx
ON source_documents(is_active, doc_year);

COMMIT;

