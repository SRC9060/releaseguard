# ReleaseGuard Production Deployment Guide

## 1. Production Topology & Process Separation

ReleaseGuard is architected to run as three independent services connected to managed data stores:

```
                    +------------------------+
                    |  Client Web Browsers   |
                    +-----------+------------+
                                |
                                v
               +----------------------------------+
               |  Frontend Service (Nginx Alpine) |
               |     Container Port: 80           |
               +----------------+-----------------+
                                | API Requests
                                v
               +----------------------------------+
               |    Backend API (Uvicorn ASGI)    |
               |     Container Port: 8000         |
               +--------+----------------+--------+
                        |                |
           Read/Write   |                | Telemetry Ingestion (XADD)
           Relational   |                |
                        v                v
      +--------------------+      +--------------------+
      |   PostgreSQL 17    |      |      Redis 7       |
      | (Managed Database) |      | (In-Memory Buffer) |
      +---------^----------+      +---------^----------+
                |                           |
                | Persist Events & Issues   | Consume Streams (XREADGROUP)
                |                           |
               +----------------------------+-----+
               |      Worker Service (Python)     |
               |       Stand-alone Process        |
               +----------------------------------+
```

### Process Separation Rules
- **API Service**: Handles HTTP traffic, JWT authentication, configuration requests, and fast event queuing (`XADD`). It does **not** process stack traces or execute heavy database upserts directly.
- **Worker Service**: Standalone background consumer executing `python -m app.worker`. Consumes Redis Streams, groups issues, handles stale PEL recovery, and dead-letters poison messages.
- **Frontend Service**: Static SPA bundle served via Nginx with HTTP security headers and client-side push-state routing.

---

## 2. Production Deployment Sequence

To prevent schema mismatch and downtime during zero-downtime rolling upgrades, follow this strict deployment order:

```
Step 1: Provision Persistent PostgreSQL 17 & Redis 7
  |
Step 2: Export Production Environment Variables
  |
Step 3: Run Database Migrations: `alembic upgrade head`
  |
Step 4: Launch Backend API Instances (`uvicorn app.main:app`)
  |
Step 5: Launch Ingestion Worker Instances (`python -m app.worker`)
  |
Step 6: Deploy Pre-compiled Frontend Static Bundle
  |
Step 7: Verify Orchestration with Liveness & Readiness Probes
```

> **IMPORTANT**: Never invoke `Base.metadata.create_all()` in production. Always manage and apply schema changes exclusively via `alembic upgrade head`.

---

## 3. Environment Variable Configuration

Create a secure `.env` file on the production host or configure these secrets in your orchestration system (Kubernetes Secrets, AWS SSM, HashiCorp Vault):

| Variable | Description | Production Example |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Runtime environment name (`production`, `staging`, `development`) | `production` |
| `DATABASE_URL` | Persistent PostgreSQL connection URI | `postgresql://rg_user:SuperSecretPass@db.internal:5432/releaseguard` |
| `REDIS_URL` | Redis cluster or standalone connection URI | `redis://redis.internal:6379/0` |
| `JWT_SECRET` | Cryptographically random secret for signing tokens | `d9e0f3b8a1c54e2...` (min 32 bytes) |
| `CORS_ORIGINS` | Explicit comma-separated list of allowed frontend origins (No wildcards!) | `https://app.releaseguard.io` |
| `FRONTEND_URL` | Primary canonical URL of the deployed frontend dashboard | `https://app.releaseguard.io` |
| `JWT_EXPIRATION_MINUTES` | Access token lifespan in minutes | `1440` (24 hours) |
| `AUTH_MAX_ATTEMPTS` | Maximum failed login attempts before lockout | `5` |
| `AUTH_LOCKOUT_SECONDS` | Duration in seconds of failed login lockout | `900` (15 minutes) |
| `LOG_LEVEL` | Application logging granularity | `INFO` |

---

## 4. Docker Deployment Artifacts

ReleaseGuard provides production-ready multi-stage Dockerfiles.

### 4.1 Backend / Worker Image (`backend/Dockerfile`)
The backend Docker image packages the Python runtime as an unprivileged system user (`appuser` UID 10001):

```dockerfile
# Build image
docker build -t releaseguard-backend:latest -f backend/Dockerfile backend

# Run Migration Container
docker run --rm \
  --env-file .env \
  releaseguard-backend:latest \
  alembic upgrade head

# Run API Instance
docker run -d --name releaseguard-api \
  --env-file .env \
  -p 8000:8000 \
  releaseguard-backend:latest

# Run Worker Instance
docker run -d --name releaseguard-worker \
  --env-file .env \
  releaseguard-backend:latest \
  python -m app.worker
```

### 4.2 Frontend Image (`frontend/Dockerfile`)
The frontend container compiles Vite assets using Node 20 and serves them using lightweight Alpine Nginx:

```dockerfile
# Build image with production API base URL
docker build \
  --build-arg VITE_API_BASE_URL=https://api.releaseguard.io \
  -t releaseguard-frontend:latest \
  -f frontend/Dockerfile frontend

# Run Frontend Container
docker run -d --name releaseguard-frontend \
  -p 80:80 \
  releaseguard-frontend:latest
```

---

## 5. Orchestration via Docker Compose

For single-host production or staging environments, use the included `docker-compose.yml`:

```bash
# 1. Copy and populate production environment
cp .env.example .env

# 2. Build and launch all services in detached mode
docker compose up -d --build

# 3. Inspect running containers
docker compose ps

# 4. View real-time logs
docker compose logs -f api worker
```

---

## 6. Health & Readiness Probes

ReleaseGuard exposes two standardized health probes for container orchestrators (Kubernetes / ECS / Nomad):

### 6.1 Liveness Probe (`GET /health`)
- **URL**: `http://localhost:8000/health`
- **Expected Status**: `200 OK`
- **Response**: `{"status": "ok", "service": "releaseguard-api"}`
- **Purpose**: Verifies the ASGI process loop is alive and responding.

### 6.2 Readiness Probe (`GET /health/ready`)
- **URL**: `http://localhost:8000/health/ready`
- **Expected Status**: `200 OK`
- **Sample Healthy Response**:
  ```json
  {
    "status": "ready",
    "checks": {
      "database": "connected",
      "redis": "connected"
    }
  }
  ```
- **Failing Response**: `503 Service Unavailable` if PostgreSQL or Redis cannot be contacted.
- **Purpose**: Prevents the load balancer from routing traffic to an API node that cannot query the database or enqueue telemetry.
