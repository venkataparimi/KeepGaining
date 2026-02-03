# KeepGaining Trading Platform

A production-grade, fully observable, broker-agnostic, UI-driven algorithmic trading platform.

---

## 🤖 AI Agent Instructions

> **IMPORTANT**: Before making any API calls or database queries, read:
> - [`backend/scripts/UPSTOX_API_REFERENCE.md`](backend/scripts/UPSTOX_API_REFERENCE.md)
> 
> This document contains critical learnings to avoid repeated debugging mistakes.

---

## Architecture

- **Backend**: Python (FastAPI)
- **Frontend**: TypeScript (Next.js)
- **Database**: PostgreSQL (TimescaleDB)
- **Cache**: Redis
- **Orchestration**: Docker Compose

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Python 3.10+
- Node.js 18+

### Running the Stack

```bash
docker-compose up -d --build
```

### Development

#### Backend

```bash
cd backend
poetry install
poetry run uvicorn app.main:app --reload
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```
