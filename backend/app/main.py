from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.db import Base, engine
from app.routes.auth import router as auth_router
from app.routes.events import router as events_router
from app.routes.flags import router as flags_router
from app.routes.incidents import router as incidents_router
from app.routes.projects import router as projects_router
from app.routes.releases import router as releases_router
from app.routes.tenants import router as tenants_router

app = FastAPI(title="ReleaseGuard", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

if engine.dialect.name == "postgresql":
    with engine.begin() as conn:
        # Phase 5 migrations
        conn.execute(text("ALTER TABLE error_events ADD COLUMN IF NOT EXISTS event_id VARCHAR(36);"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_error_events_event_id ON error_events (event_id);"))

        # Phase 6 migrations
        conn.execute(text("ALTER TABLE issues ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'unresolved' NOT NULL;"))
        conn.execute(text("ALTER TABLE issues ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP;"))
        conn.execute(text("ALTER TABLE issues ADD COLUMN IF NOT EXISTS muted_at TIMESTAMP;"))
        conn.execute(text("ALTER TABLE issues ADD COLUMN IF NOT EXISTS is_regression BOOLEAN DEFAULT FALSE NOT NULL;"))
        conn.execute(text("ALTER TABLE issues ADD COLUMN IF NOT EXISTS regressed_at TIMESTAMP;"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_issues_project_status ON issues (project_id, status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_error_events_issue_received ON error_events (issue_id, received_at DESC);"))

        # Phase 7 multi-tenancy migrations
        conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS tenant_id INTEGER;"))
        conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS api_key VARCHAR(64);"))

        # Seed deterministic default organization for legacy/dev projects
        conn.execute(text("""
            INSERT INTO tenants (id, name, slug, created_at, updated_at)
            VALUES (1, 'Default Organization', 'default', NOW(), NOW())
            ON CONFLICT (id) DO NOTHING;
        """))

        # Backfill existing projects with default tenant and generated API key
        conn.execute(text("UPDATE projects SET tenant_id = 1 WHERE tenant_id IS NULL;"))
        conn.execute(text("UPDATE projects SET api_key = 'rg_live_' || md5(id::text || name) WHERE api_key IS NULL;"))

        # Phase 8 indexes
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_releases_project_env ON releases (project_id, environment);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_feature_flags_project ON feature_flags (project_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_flag_settings_env ON flag_settings (environment_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_flag_audit_logs_flag ON flag_audit_logs (flag_id, created_at);"))

        # Phase 9 indexes
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_incidents_tenant_project ON incidents (tenant_id, project_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_incidents_status_env ON incidents (project_id, environment, status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_incidents_related_issue ON incidents (project_id, related_issue_id, created_at);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_incident_events_incident ON incident_events (incident_id, created_at);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_incident_mitigations_incident ON incident_mitigations (incident_id, status);"))

app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(releases_router, prefix="/api/v1")
app.include_router(flags_router, prefix="/api/v1")
app.include_router(incidents_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "service": "ReleaseGuard"}
