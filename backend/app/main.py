from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.config import settings
from app.database import create_tables, engine
from app.extraction import claude_extractor
from app.routers import accounts, categories, dashboard, documents, transactions
from app.seed import seed_defaults


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    with Session(engine) as session:
        seed_defaults(session)
    yield


app = FastAPI(title="Spendings", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (accounts.router, categories.router, documents.router, transactions.router, dashboard.router):
    app.include_router(router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "claude_available": claude_extractor.is_available(), "storage": settings.storage_backend}
