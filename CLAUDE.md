# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Enterprise RAG Agent — a local/private RAG system with a FastAPI backend and Vue 3 frontend. Supports multi-format document parsing, 7 chunking strategies, hybrid retrieval (vector + BM25 + rerank), multi-turn conversations, role-based permissions, and async document processing via Celery.

## Common Commands

### Backend (Python)

```bash
cd backend

# Run dev server (hot reload)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run tests
python -m pytest tests/ -v

# Run Celery worker (document processing)
celery -A app.core.celery_app worker --loglevel=info --queues=celery,doc_process,maintenance

# Run a specific test script
python backend/test_query_stream.py
python backend/test_permissions.py
```

### Frontend (Vue 3 + Vite)

```bash
cd frontend

# Dev server
npm run dev -- --host

# Production build
npm run build

# Preview production build
npm run preview
```

### Docker

```bash
# Start full stack (backend + PostgreSQL + Redis)
docker compose up -d

# Start individual services
docker compose up -d db redis
docker compose up -d backend

# Milvus must be started separately via its own compose file
# wget https://github.com/milvus-io/milvus/releases/download/v2.4.0/milvus-standalone-docker-compose.yml
# docker compose -f milvus-docker-compose.yml up -d
```

### Testing

```bash
cd backend

# Run all tests
python -m pytest tests/ -v

# Run without integration tests (no external services needed)
python -m pytest tests/ -m "not integration" -v

# Run with coverage
python -m pytest tests/ --cov=app --cov-report=html
```

## Architecture

### Backend (`backend/app/`)

Layered architecture with dependency injection:

- **`api/routes/`** — FastAPI routers. Each module handles one domain. Routes use dependency injection from `api/deps.py` for current user, services, and stores.
- **`services/`** — Business orchestration layer. `rag_service.py` runs the full RAG pipeline. `document_service.py` handles document ingestion.
- **`core/`** — Low-level engines:
  - `chunking.py` — 7 chunking strategies (auto, fixed_size, recursive, semantic, structured, parent_child, llm_smart).
  - `parser.py` — Document parsing with `unstructured` as primary, pure-Python libraries as fallback. Optional Baichuan API fallback via `baichuan_parser.py`.
  - `embedding.py` — Ollama embedding (bge-m3, 1024-dim).
  - `milvus_store.py` — Milvus vector store. Uses IVF_FLAT + COSINE.
  - `metadata_store.py` — SQLAlchemy async ORM. Default SQLite (dev), PostgreSQL via docker-compose (production). Switch via `METADATA_DB_URL`.
  - `retrieval.py` — Hybrid retriever: vector search + BM25 over jieba-segmented text, fused with RRF.
  - `reranker.py` — BGE reranker (FlagEmbedding).
  - `llm.py` — LLM service supporting Ollama (default) and vLLM.
  - `security.py` — JWT auth. `SECRET_KEY` must be set in `.env` (length >= 32), startup warns if using default.
  - `celery_app.py` — Celery configuration with Redis broker.
  - `tasks.py` — Async Celery tasks: `process_document`, `rebuild_bm25_index`.
- **`container.py`** — Dependency injection container. Replaces global module-level singletons. Services register as singletons; tests can override implementations via `container.override(Type, mock_instance)`.
- **`api/deps.py`** — FastAPI dependency injection re-exports. All route dependencies come through here.
- **`models/schemas.py`** — Pydantic request/response models.
- **`config.py`** — Pydantic Settings with `.env` file at repo root. Priority: `.env` > environment variables > defaults.
- **`logger.py`** — Structured JSON logging with trace IDs.

### Dependency Injection

All core and service modules have been migrated from global singletons to `app.container`:

```python
# Old pattern (still works, delegates to container):
from app.core.milvus_store import get_milvus_store
store = get_milvus_store()

# New pattern (FastAPI Depends):
from app.container import get_milvus_store
from fastapi import Depends

@router.get("/docs")
async def list_docs(store: MilvusStore = Depends(get_milvus_store)):
    ...

# Test override:
from app.container import container
container.override(MilvusStore, mock_store)
```

### Async Document Processing

Two upload endpoints:

- `POST /api/upload` — Synchronous, blocks until complete. Suitable for small files (< 10MB).
- `POST /api/upload/async` — Asynchronous via Celery. Returns `task_id` immediately. Poll `GET /api/tasks/{task_id}` for progress.

The Celery task (`app.core.tasks.process_document`) runs: parse → chunk → embed → Milvus insert → metadata save → BM25 update. Max 3 retries with 60s delay. Task progress reported via Celery `update_state(PROGRESS, meta=...)`.

### Frontend (`frontend/src/`)

- Vue 3 with Element Plus, Vue Router, Axios.
- `api/api.js` — Axios instance with JWT interceptors.
- `views/` — Page-level components: `QueryView.vue`, `UploadView.vue`, `DocumentView.vue`, `PermissionView.vue`, `LoginView.vue`.
- `components/` — `ChunkPreviewPanel.vue`.
- `router.js` — Route guards check JWT and admin role.

### Key Data Flows

**Document Ingestion (Sync):**
Upload → `document_service.py` → `parser.py` → `chunking.py` → `embedding.py` → `milvus_store.py` + `metadata_store.py` + BM25 update.

**Document Ingestion (Async):**
Upload → save temp file → Celery `process_document` task → same pipeline as sync but in background worker.

**RAG Query:**
`POST /api/query` or `/api/query/stream` → `rag_service.py` → query rewriting → `retrieval.py` (vector + BM25 + RRF) → `reranker.py` → LLM with context + history → return answer with source citations [^1], [^2].

**Multi-turn Conversations:**
`conversation_id` passed in query request → `metadata_store.py` loads last 10 messages (5 rounds) → injected as `history_messages` into LLM prompt → new messages saved back to DB.

**Permission Model:**
- `admin` — access all documents and user management.
- `staff` — access public + own department documents.
- `user` — access public documents only.
Permissions enforced in `query.py` via doc_id filters and in `permission.py` for document access control.

## External Dependencies

- **Milvus 2.4+** — Vector database (runs externally).
- **Ollama** — Local LLM/embedding server. Models: `bge-m3` (embeddings), `qwen2.5:7b-instruct` (LLM).
- **PostgreSQL 16** — Metadata DB in production (via docker-compose). SQLite for local dev.
- **Redis 7** — Celery broker and result backend.

## Configuration

All config lives in `.env` at repo root. Key settings:

- `SECRET_KEY` — JWT signing key. Must be >= 32 chars in production. Startup warns if using default.
- `OLLAMA_HOST`, `OLLAMA_EMBED_MODEL`, `OLLAMA_LLM_MODEL` — Ollama endpoint and models.
- `MILVUS_HOST`, `MILVUS_PORT`, `MILVUS_COLLECTION_NAME` — Milvus connection.
- `METADATA_DB_URL` — `sqlite+aiosqlite:///./metadata.db` (dev) or `postgresql+asyncpg://...` (production).
- `REDIS_URL` — `redis://localhost:6379/0` (Celery broker).
- `LLM_PROVIDER` — `"ollama"` or `"vllm"`.
- `CHUNK_SIZE`, `CHUNK_OVERLAP`, `DEFAULT_CHUNK_STRATEGY` — Default chunking.
- `TOP_K_VECTOR`, `TOP_K_BM25`, `TOP_K_RERANK` — Retrieval top-k.

## Testing

Tests in `backend/tests/`:
- `conftest.py` — Global fixtures. Sets test DB (`test_metadata.db`), mock external services (Milvus/Ollama) via DI container overrides.
- `test_auth.py` — Register, login, JWT validation, role-based access.
- `test_health.py` — Health check endpoint.
- `test_permissions.py` — Admin-only route protection.

External services are mocked at the container level (`container.override(MilvusStore, mock)`) so tests run without Milvus/Ollama/Redis.

## Important Notes

- The backend uses `app.main:app` as the ASGI entry point. When running `uvicorn`, `cd backend` first so imports resolve as `app.*`.
- Frontend dev server proxies `/api` to backend via Vite config.
- Chunk preview (`POST /api/chunk-preview`) does not persist to database.
- The `parent_child` chunking strategy stores both parent and child chunks in Milvus. Child chunks retrieve, parent chunks provide context.
- Health check (`/api/health`) gracefully handles missing external services — returns `degraded` status instead of crashing.
- `AGENTS.md` contains detailed documentation on chunking strategies and conversation system.
