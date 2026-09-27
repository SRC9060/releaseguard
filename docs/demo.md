# ReleaseGuard End-to-End Demonstration Guide

This guide documents the full 18-step operator and engineering demonstration of ReleaseGuard. It demonstrates error tracking, Redis Streams ingestion, fingerprinting, release tracking, deterministic feature flagging, and controlled incident mitigation.

---

## Prerequisites & Demo Credentials

- **Backend API**: Running at `http://localhost:8000`
- **Dashboard UI**: Running at `http://localhost:5173` (or port 80 in Docker)
- **Demo User Account**:
  - **Email**: `demo@releaseguard.dev`
  - **Password**: `DemoPassword123!`
  - **Tenant / Workspace**: `Acme Corp` (Role: Owner)
  - **Project**: `Checkout Service`

If not already populated, initialize demo data:
```bash
python backend/scripts/seed_demo.py
```

---

## The 18-Step Live Walkthrough

### Step 1: Access Deployed Application
- Open `http://localhost:5173` in a web browser.
- Log in with `demo@releaseguard.dev` / `DemoPassword123!`.
- Observe the **Acme Corp** workspace loaded in the top header with **Checkout Service** selected.

### Step 2: Review or Select Project
- Click on the **Project Selector** dropdown in the header.
- Confirm **Checkout Service** is active.
- Note the project API key format: `rg_live_demo_checkout_service_key_99`.

### Step 3: Create a New Release
- Navigate to **Releases** in the sidebar.
- Observe existing releases (`1.0.0`, `1.1.0`, `1.2.0`).
- Click **Create Release**.
- Enter:
  - **Version**: `1.3.0`
  - **Commit SHA**: `a8f9c2d`
  - **Environment**: `production`
- Click **Deploy Release**. Observe the new release badge with "Active" state.

### Step 4: Create a New Feature Flag
- Navigate to **Feature Flags** in the sidebar.
- Click **Create Flag**.
- Configure:
  - **Flag Key**: `express_stripe_checkout`
  - **Flag Name**: `Express Stripe Checkout Button`
  - **Description**: `Enables one-click Stripe payment modal on checkout`
- Click **Save Flag**.

### Step 5: Configure Deterministic Rollout
- In the **Feature Flags** list, click on `express_stripe_checkout`.
- Set **Global Status**: `Enabled`.
- Under **Production Rollout**, move the slider to `25%`.
- Click **Update Rollout**.
- Observe the audit log entry recorded immediately below the flag definition.

### Step 6: Generate Application Errors via SDK / API
Simulate error events using either the UI or curl.

**Option A — In Dashboard**:
- Click **Simulate Error** in the top navigation bar.
- Select Exception Type: `PaymentGatewayTimeout`.
- Message: `Stripe connection timeout after 3000ms`.
- Click **Dispatch Error**.

**Option B — Direct API Ingestion**:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/projects/1/events \
  -H "Content-Type: application/json" \
  -H "X-ReleaseGuard-Key: rg_live_demo_checkout_service_key_99" \
  -d '{
    "exception_type": "PaymentGatewayTimeout",
    "message": "Stripe connection timeout after 3000ms",
    "stack_trace": "File \"/app/payment.py\", line 84, in execute_charge\n  raise PaymentGatewayTimeout(\"Stripe connection timeout\")",
    "environment": "production",
    "release": "1.3.0"
  }'
```

### Step 7: Verify Event Enqueuing in Redis
- The API responds with `HTTP 202 Accepted` and a JSON payload containing the assigned `event_id`:
  ```json
  {"status": "queued", "event_id": "018f...-....", "fingerprint": "a93e..."}
  ```
- The event is appended to the Redis Stream `events:stream`.

### Step 8: Verify Worker Processing
- The standalone worker process (`python -m app.worker`) consumes the event via `XREADGROUP`.
- Check worker logs:
  ```text
  [INFO] releaseguard.worker: Ingested event 018f... for project 1 (issue_id=4)
  ```
- The worker issues `XACK` to remove the message from the pending entry list.

### Step 9: Verify PostgreSQL Persistence
- Verify the event is committed in the relational database:
  - Table `error_events` records the specific event payload, timestamp, and environment.
  - Table `issues` increments the aggregate count and updates `last_seen`.

### Step 10: Verify Issue in Dashboard
- Navigate to **Issues** in the sidebar.
- Observe `PaymentGatewayTimeout` displayed at the top of the issue list.
- Click on the issue to inspect:
  - 24-hour occurrence time series
  - Exception stack trace with highlighted lines
  - Correlated release tag (`1.3.0`)
  - Environment badge (`production`)

### Step 11: Trigger / Open an Incident
- Navigate to **Incidents** in the sidebar.
- Click **Create Incident**.
- Configure:
  - **Title**: `Production Payment Gateway Degradation`
  - **Severity**: `Critical`
  - **Environment**: `production`
  - **Issue Association**: Select `PaymentGatewayTimeout`
- Click **Open Incident**.

### Step 12: Correlate Release and Feature Flag
- Click on the incident to open the **Incident Command Center**.
- Notice the **Root Cause Correlation** pane:
  - Correlated Release: `1.3.0` deployed 12 minutes ago.
  - Correlated Flag: `express_stripe_checkout` rolled out to 25%.
- The system automatically formulates an advisory mitigation plan.

### Step 13: Initiate Investigation
- Click the **Investigate** button to transition incident status from `Open` to `Investigating`.
- Add an investigation timeline note:
  > *"Error spike isolated to express stripe checkout flow post release 1.3.0."*

### Step 14: Review & Approve Mitigation
- In the **Recommended Mitigations** section:
  - Action: **Kill Switch Feature Flag** (`express_stripe_checkout` -> `0% / Disabled`).
- Notice that mitigation is **strictly human-approved** (autonomous destructive changes are rejected).
- Click **Approve & Execute Mitigation**.
- Enter confirmation dialog when prompted.

### Step 15: Verify Feature Flag Disabled
- Navigate back to **Feature Flags**.
- Confirm `express_stripe_checkout` is now toggled **Disabled** with rollout set to **0%**.
- Check `/api/v1/projects/1/config?environment=production` to verify downstream SDKs receive `false`.

### Step 16: Verify Audit Trail
- Under `express_stripe_checkout`, view the **Audit Log**:
  - **Action**: `update_rollout` / `kill_switch`
  - **Actor**: `demo@releaseguard.dev`
  - **Before State**: `{"enabled": true, "rollout_percentage": 25}`
  - **After State**: `{"enabled": false, "rollout_percentage": 0}`
  - **Reason**: `Incident Mitigation #1`

### Step 17: Resolve Incident
- Return to the **Incident Command Center**.
- Click **Mark as Mitigated**, then **Resolve Incident**.
- The incident badge updates to green (`Resolved`).

### Step 18: Verify Final System State
- Return to **Overview**:
  - Health probe shows healthy status.
  - Incident count reflects 0 active critical incidents.
  - Issue status reflects mitigated trend.
- End of walkthrough.
