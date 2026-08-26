# Pricing Intelligence AI

AI-driven competitor and pricing intelligence platform. Multi-tenant: each workspace brings its own AI provider API key (OpenAI, Google, or Anthropic) and is billed for its own usage.

Core loop: capture business context → import your product catalog → AI discovers real competitors (and resellers, for MAP monitoring) on the open web → AI matches their products against your catalog with a confidence score → confirmed matches are tracked for live price comparison → automated reports summarize price moves, MAP violations, and alerts → Apex, an agentic assistant, answers open-ended questions and proposes actions over all of the above at any time, not just from a generated report.

## Stack

FastAPI + PostgreSQL (async SQLAlchemy + Alembic) backend, Next.js (App Router) frontend, Docker Compose for local dev.

Deployed on free-tier infrastructure: Vercel (frontend), Render (backend, containerized), Neon (Postgres, scale-to-zero).

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
  catalog/      # Product model + import paths (manual/CSV/URL/photo/website scan)
  discovery/    # AI competitor + reseller discovery, product-level discovery, matching
  reporting/    # scheduled + on-demand AI report generation, PDF export
  assistant/    # Apex — agentic chat assistant (read/write tools, human-approved writes)
  services/     # ai_client.py — provider-flexible dispatcher (OpenAI/Google/Anthropic)

frontend/app/
  onboarding/   # first-run business context capture
  (auth)/       # login, signup
  (app)/        # catalog, discovery, tracked, reports, activity, settings, assistant
```

## Key features

- **Catalog import**: manual entry, CSV, a single product URL, a product photo (AI-described), or a full website scan that finds and lists a site's products.
- **Discovery**: AI web search finds real competitor and reseller candidates from the workspace's own business context, each with a self-assessed confidence score; per-site product-level discovery follows the same pattern.
- **Matching**: AI proposes matches between the workspace's catalog and a competitor's discovered products, reasoning on product type/class first, then spec/tier, with price only a secondary sanity check — confirmed matches feed price comparison and reports.
- **Reports**: scheduled or on-demand AI-written reports covering price comparisons, MAP violations, price anomalies, new competitor products, and stock changes since the previous report; exportable as PDF.
- **Apex**: an agentic chat assistant with full read access to the workspace's catalog, saved competitors, discovered competitor products, and confirmed matches (not limited to what a generated report already covered), plus its own web search for questions the workspace's data can't answer. It can freely compare any two products on request and produce an ad-hoc confidence score, using the same matching heuristic as the platform's own AI matching. Every write action (adding a product, running discovery, auto-matching, generating a report, editing business context) is only ever proposed — nothing executes until a human approves it — and it stays scoped to the workspace's own pricing-intelligence work.
