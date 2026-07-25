from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth.router import router as auth_router
from app.catalog.router import router as catalog_router
from app.config import settings
from app.services.storage import UPLOAD_DIR
from app.workspace.router import router as workspace_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Pricing Intelligence AI API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# StaticFiles requires the directory to exist at mount time.
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(workspace_router, prefix="/api/v1/workspace", tags=["workspace"])
app.include_router(catalog_router, prefix="/api/v1/products", tags=["catalog"])


@app.get("/health")
async def health():
    return {"status": "ok"}
