# ReleaseGuard Security Audit & Architecture Review

## 1. Executive Summary

This document provides a comprehensive security review and architectural breakdown of ReleaseGuard following the Phase 10 Production Hardening milestone. The review assesses authentication, authorization, multi-tenant isolation, data scoping, API key safety, audit logging, and residual security constraints.

---

## 2. Authentication Model

- **Mechanisms**: JSON Web Tokens (JWT) signed via HMAC-SHA256 (`HS256`).
- **Token Structure**:
  - `sub`: User ID (integer represented as string)
  - `exp`: Configurable expiration timestamp (default: 1440 minutes / 24 hours, controlled via `JWT_EXPIRATION_MINUTES`)
  - `iat`: Token issuance timestamp
- **Transport**: Standard HTTP `Authorization: Bearer <token>` header.
- **Why Short-Lived JWT is Retained**: ReleaseGuard uses a stateless JWT model to support horizontal worker and API scaling without shared session database lookups on high-frequency evaluation requests. In production, revoking compromised tokens is achieved via client-side logout token removal and expiration timeouts.
- **Credential Storage**: Passwords hashed using bcrypt with salt generation. Plaintext passwords are never stored or logged.
- **Brute-Force & Lockout Protection**: The `/auth/login` endpoint incorporates an `AuthRateLimiter` that monitors consecutive failed authentication attempts. After 5 failed attempts within 15 minutes (`AUTH_MAX_ATTEMPTS` = 5, `AUTH_LOCKOUT_SECONDS` = 900), the account is locked and returns `429 Too Many Requests`.

---

## 3. Authorization Model (RBAC)

ReleaseGuard enforces strict Role-Based Access Control (RBAC) across three hierarchical roles within each tenant:

| Role | Hierarchy Level | Capabilities |
| :--- | :--- | :--- |
| **Owner** | 3 | Full administrative authority. Can invite/delete members, transfer/demote roles, delete projects, approve mitigations, mutate feature flags. |
| **Admin** | 2 | Operational management. Can create/archive feature flags, update rollouts, create releases, trigger incidents. Cannot delete owners or demote tenant owners. |
| **Member** | 1 | Read-only access to projects, issues, releases, and feature flags. Cannot execute administrative mutations or approve incident mitigations. |

### Last-Owner Invariant Protection
Tenants must always retain at least one active Owner. Concurrency-safe transactional row locking (`SELECT ... FOR UPDATE` or atomic count validation) is enforced in membership update and deletion endpoints to prevent race conditions demoting or removing the final owner.

---

## 4. Multi-Tenant Isolation Strategy

- **Tenant-Scoped URLs**: Sensitive administrative routes require explicit URL tenant scoping (`/api/v1/tenants/{tenant_id}/...`).
- **Server-Side Identity Verification**: Client-supplied `tenant_id` parameters are never implicitly trusted. Every request verifies:
  1. The authenticated user has an active membership record in the target `tenant_id`.
  2. The target resource (`project_id`, `flag_id`, `incident_id`, `release_id`) explicitly belongs to the specified `tenant_id` at the SQL query level.
- **Database Query Filtering**: Tenant boundaries are enforced directly in database SQL queries (`WHERE project.tenant_id = :tenant_id`), preventing in-memory leakage or unindexed cross-tenant lookups.
- **404 Not Found Masking**: Mismatched or non-permitted tenant resources return HTTP `404 Not Found` rather than `403 Forbidden` to prevent malicious actors from inferring the existence of other tenants' resource IDs.

---

## 5. API Key Model & Ingestion Scoping

- **Key Format**: High-entropy keys formatted as `rg_live_<32-byte-hex>` generated via cryptographically secure random bytes (`secrets.token_hex`).
- **Ingestion Protection**:
  - The single event endpoint (`POST /api/v1/projects/{project_id}/events`) and bulk ingestion endpoint (`POST /api/v1/projects/{project_id}/events/bulk`) require API key verification via `X-ReleaseGuard-Key`.
  - Keys are strictly scoped to the target project. Cross-project key injection is rejected with `401 Unauthorized`.
  - One tenant cannot ingest errors or metrics into another tenant's project.

---

## 6. Audit Logging

Every administrative state mutation records an audit record with actor identity and timestamp:
- **Feature Flags**: Logged in `flag_audit_logs` (`flag_id`, `environment_id`, `actor_id`, `action`, `before_state`, `after_state`, `created_at`).
- **Incidents & Mitigation**: Logged in `incident_events` and `incident_mitigations` (`incident_id`, `actor_id`, `event_type`, `approved_by`, `approved_at`, `executed_at`).
- **Redaction**: Secret values, passwords, raw JWT tokens, and API keys are automatically stripped from all structured application logs by `RedactingFormatter`.

---

## 7. Known Security Limitations & Residual Risks

1. **In-Flight JWT Revocation**: Because JWTs are stateless, tokens cannot be individually blacklisted before expiration without an active distributed Redis blocklist or token generation versioning.
2. **Rate Limiting Scope**: Auth rate limiting is applied on `/login`. In high-scale deployments, edge DDoS protection (e.g. Cloudflare / Nginx rate limiting) should front the ingestion endpoints.
3. **Database Network Isolation**: PostgreSQL and Redis connections should reside within an isolated VPC or private subnet with TLS (`sslmode=require`) enabled for production environments.
