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
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
