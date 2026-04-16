# Tax Filing Assistant

LLM-powered tax filing assistant — an agent that orchestrates W-2 parsing, IRS rule lookup, deduction calculation, and Form 1040 generation via tool/function calling. Runs fully locally against LM Studio.

**Stack**: LangGraph · Pydantic v2 · FastAPI · Next.js · SQLite · LM Studio (Qwen2.5-7B / Gemma 3 4B)

## Scope (v1)
- W-2 individual filers only → Form 1040 (+ Schedule A if itemizing).
- Tax year 2025.

## Layout
```
backend/   FastAPI + LangGraph agent + tools + ingest pipeline
frontend/  Next.js (App Router) UI
storage/   SQLite DBs + uploaded PDFs (runtime, gitignored)
tests/     pytest suites
```

## Setup

### Backend
```bash
cd backend
python -m venv ../.venv && source ../.venv/bin/activate
pip install -e ".[dev]"
```

System deps for OCR:
```bash
brew install tesseract          # macOS
# or: apt-get install tesseract-ocr
```

### LM Studio
1. Install LM Studio and pull **Qwen2.5-7B-Instruct** (recommended) or **Gemma 3 4B**.
2. Start the local server on `http://localhost:1234/v1`.
3. Set `MODEL_NAME` in `.env` to the exact model identifier shown in LM Studio.

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Run
```bash
# from repo root
uvicorn backend.app.main:app --reload    # backend on :8000
cd frontend && npm run dev               # frontend on :3000
```

## Tests
```bash
cd backend && pytest
```

## Architecture
See [plan](/.claude/plans/create-a-project-on-hazy-hoare.md) for full system design.
