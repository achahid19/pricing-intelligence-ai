FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Shell form (not exec-form CMD) so $PORT actually gets expanded at
# container start — Render assigns this dynamically and the container must
# bind to it, unlike the fixed 8000 used for local Docker Compose. No
# --reload here: that's a dev-only convenience (see docker-compose.yml's
# command: override, which restores it for local dev without needing a
# second Dockerfile for production).
#
# Migrations run here, chained before uvicorn, rather than via Render's
# Pre-Deploy Command — that feature is paid-plan-only, unavailable on the
# free tier this app deploys to. alembic upgrade head is a no-op once
# already current, so running it on every container start (including every
# free-tier wake-from-sleep) is safe, not just on the first deploy. If it
# fails, uvicorn deliberately never starts — running with an out-of-sync
# schema silently would be worse than the service staying down.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
