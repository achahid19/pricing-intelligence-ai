# Pricing Intelligence AI

AI-driven market and competitor intelligence platform. Multi-tenant: each workspace brings its own AI provider API key (OpenAI, Google, or Anthropic).

Price tracking/comparison/alerts (from the earlier `ai_crafters_pfa` prototype) is an optional later capability here, not the starting point — this platform's core loop is business-context capture → catalog import → AI-driven competitor discovery, matching, and reporting.

## Stack

FastAPI + PostgreSQL (async SQLAlchemy + Alembic) backend, Next.js (App Router) frontend, Docker Compose for local dev.

## Running locally

```bash
cp .env.example .env        # fill in JWT_SECRET_KEY / FERNET_ENCRYPTION_KEY
cp backend/.env.example backend/.env
docker compose up -d --build
```

- Backend: http://localhost:8000 (`/health`)
- Frontend: http://localhost:3000

## Structure

```
backend/app/
  auth/         # signup, login, JWT, get_current_workspace dependency
  workspace/    # Workspace model, business-context capture, AI provider key storage
  catalog/      # Product model + import paths (manual/csv/url/image/website)
  discovery/    # AI competitor discovery + matching (manual or AI-assisted)
  reporting/    # AI-generated competitor reports
  services/     # ai_client.py — provider-flexible dispatcher (OpenAI/Google/Anthropic)
  tracking/     # deferred — price tracking/comparison/alerts, ported from ai_crafters_pfa later
```

See `docs/` (if present) or the project plan for the full build sequence.
