from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import Base, engine
from app.routes.events import router as events_router
from app.routes.projects import router as projects_router

app = FastAPI(title="ReleaseGuard", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from sqlalchemy import text

Base.metadata.create_all(bind=engine)

if engine.dialect.name == "postgresql":
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE error_events ADD COLUMN IF NOT EXISTS event_id VARCHAR(36);"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_error_events_event_id ON error_events (event_id);"))

app.include_router(projects_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "service": "ReleaseGuard"}
