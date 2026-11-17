from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.auth import require_user
from app.config import settings
from app.database import create_tables, engine
from app.extraction import claude_extractor
from app.routers import accounts, assistant, categories, dashboard, documents, goals, income, insights, loans, plan, properties, scheduled, setup, transactions, wealth
from app.seed import seed_defaults


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    with Session(engine) as session:
        seed_defaults(session)
    yield


# The interactive API docs would reveal the whole API surface to anyone: hide them behind auth.
docs = {} if not settings.auth_enabled else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title="Spendings", version="0.1.0", lifespan=lifespan, **docs)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (accounts.router, categories.router, documents.router, transactions.router, dashboard.router, insights.router, loans.router, properties.router, wealth.router, income.router, plan.router, assistant.router, goals.router, setup.router, scheduled.router):
    app.include_router(router, prefix="/api", dependencies=[Depends(require_user)])


@app.get("/api/config")
def public_config():
    """What the browser needs before signing in. Firebase web settings are public identifiers."""
    return {
        "auth_enabled": settings.auth_enabled,
        "firebase": {"apiKey": settings.firebase_api_key, "authDomain": settings.firebase_auth_domain, "projectId": settings.firebase_project_id}
        if settings.auth_enabled else None,
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "claude_available": claude_extractor.is_available(), "storage": settings.storage_backend}


# Serve the built frontend when it exists (deploy-local.sh / Docker image).
# API routes are declared above, so they take precedence; anything else is the SPA.
if settings.frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=settings.frontend_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        requested = settings.frontend_dist / path
        if path and requested.is_file():
            return FileResponse(requested)
        return FileResponse(settings.frontend_dist / "index.html")
