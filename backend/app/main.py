from contextlib import asynccontextmanager
import logging
import time
import uuid
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.logging import configure_logging, project_id_ctx, redact_sensitive, request_id_ctx, tenant_id_ctx
from app.queue import get_queue
from app.routes.auth import router as auth_router
from app.routes.events import router as events_router
from app.routes.flags import router as flags_router
from app.routes.incidents import router as incidents_router
from app.routes.projects import router as projects_router
from app.routes.releases import router as releases_router
from app.routes.tenants import router as tenants_router

logger = logging.getLogger("releaseguard.api")
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup validation
    settings.validate_production()

    # Schema management:
    # In production, schemas must be managed via Alembic migrations.
    # In development/test, ensure tables exist safely.
    if settings.ENVIRONMENT != "production":
        Base.metadata.create_all(bind=engine)
        if engine.dialect.name == "postgresql":
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO tenants (id, name, slug, created_at, updated_at)
                    VALUES (1, 'Default Organization', 'default', NOW(), NOW())
                    ON CONFLICT (id) DO NOTHING;
                """))
                conn.execute(text("UPDATE projects SET tenant_id = 1 WHERE tenant_id IS NULL;"))
                conn.execute(text("UPDATE projects SET api_key = 'rg_live_' || md5(id::text || name) WHERE api_key IS NULL;"))

    logger.info("ReleaseGuard API started in '%s' mode.", settings.ENVIRONMENT)
    yield
    logger.info("ReleaseGuard API shutting down.")


app = FastAPI(title="ReleaseGuard", version="0.1.0", lifespan=lifespan)

# CORS Middleware with strict origin control
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security Headers & Request Correlation Middleware
@app.middleware("http")
async def security_and_tracing_middleware(request: Request, call_next):
    # 1. Correlation ID
    req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request_id_ctx.set(req_id)

    # 2. Extract tenant/project context if available
    tenant_header = request.headers.get("X-Tenant-ID", "")
    tenant_id_ctx.set(tenant_header)
    project_id_ctx.set("")

    # 3. Payload size enforcement
    content_length = request.headers.get("Content-Length")
    if content_length:
        try:
            length = int(content_length)
            is_bulk = request.url.path.endswith("/events/bulk")
            max_size = settings.MAX_BULK_PAYLOAD_SIZE if is_bulk else settings.MAX_PAYLOAD_SIZE
            if length > max_size:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "detail": f"Payload too large. Maximum allowed size is {max_size} bytes.",
                        "request_id": req_id,
                    },
                    headers={"X-Request-ID": req_id},
                )
        except ValueError:
            pass

    # 4. Process Request
    response: Response = await call_next(request)

    # 5. Attach Correlation & Security Headers
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    return response


# Global Exception Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = request_id_ctx.get("")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "request_id": req_id},
        headers={"X-Request-ID": req_id},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    req_id = request_id_ctx.get("")
    headers = exc.headers or {}
    headers["X-Request-ID"] = req_id
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "request_id": req_id},
        headers=headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    req_id = request_id_ctx.get("")
    logger.exception("Unhandled server exception processing %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error. An unexpected error occurred.",
            "request_id": req_id,
        },
        headers={"X-Request-ID": req_id},
    )


# Routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(releases_router, prefix="/api/v1")
app.include_router(flags_router, prefix="/api/v1")
app.include_router(incidents_router, prefix="/api/v1")


# Health & Readiness Endpoints
@app.get("/health", tags=["system"])
def health_liveness():
    """Liveness probe: indicates whether the API process is alive."""
    return {"status": "ok", "service": "ReleaseGuard"}


from fastapi import Depends
from app.queue import EventQueue, get_queue


@app.get("/health/ready", tags=["system"])
def health_readiness(queue: EventQueue = Depends(get_queue)):
    """
    Readiness probe: indicates whether critical downstream dependencies
    (PostgreSQL and Redis) are connected and ready to process traffic.
    """
    db_connected = False
    redis_connected = False
    details = {}

    # Check Database
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_connected = True
        details["database"] = "connected"
    except Exception as exc:
        details["database"] = "disconnected"
        details["database_error"] = redact_sensitive(str(exc))

    # Check Redis
    try:
        queue_health = queue.get_health()
        redis_connected = queue_health.get("redis_connected", False)
        details["redis"] = "connected" if redis_connected else "disconnected"
        details["queue"] = queue_health
    except Exception as exc:
        details["redis"] = "disconnected"
        details["redis_error"] = redact_sensitive(str(exc))

    is_ready = db_connected and redis_connected
    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if is_ready else "unready",
            "dependencies": details,
        },
    )
