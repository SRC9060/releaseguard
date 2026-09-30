# ReleaseGuard 5–8 Minute Production Demonstration Script

This script provides an executive, end-to-end demonstration flow for ReleaseGuard v1.0.0. It showcases error tracking, Redis Streams ingestion, fingerprinting, release tracking, deterministic feature flagging, reversible incident mitigation, and the AI Incident Copilot.

---

## Demo Setup & Prerequisites

- **Production / Staging Dashboard**: `https://releaseguard-two.vercel.app` (or `http://localhost:5173`)
- **Backend API**: `https://releaseguard-api-0jbc.onrender.com` (or `http://localhost:8000`)
- **Demo Credentials**:
  - Email: `demo@releaseguard.dev`
  - Password: `DemoPassword123!`
  - Workspace: **Acme Corp** (Role: Owner)
  - Project: **Checkout Service**

---

## Timed Demo Walkthrough (Total: ~6.5 Minutes)

### 1. Project Overview & Architecture (0:00 – 0:45)
- **Action**: Log in to ReleaseGuard Dashboard. Show the clean Overview screen with error volume trends, active releases, and recent issues.
- **Narrative**:
  > *"ReleaseGuard is a modern developer reliability and release protection platform. Unlike passive error trackers, ReleaseGuard bridges real-time error tracking with deterministic feature flags and reversible incident mitigation. When bad releases or broken feature flags trigger regressions, ReleaseGuard empowers engineering teams to isolate root causes and apply controlled kill switches without rolling back entire codebases."*

---

### 2. Trigger an Error Event via API / SDK (0:45 – 1:30)
- **Action**: In the UI, click **"Send Test Event"** (or execute curl in terminal):
  ```bash
  curl -X POST https://releaseguard-api-0jbc.onrender.com/api/v1/projects/1/events \
    -H "Content-Type: application/json" \
    -H "X-ReleaseGuard-Key: rg_live_demo_checkout_service_key_99" \
    -d '{
      "exception_type": "PaymentGatewayTimeout",
      "message": "Stripe checkout gateway timeout after 3000ms",
      "stack_trace": "File \"/app/checkout.py\", line 142, in process_payment\n  raise PaymentGatewayTimeout(\"Stripe gateway timeout\")",
      "environment": "production",
      "release": "v2.4.1"
    }'
  ```
- **Narrative**:
  > *"The ingestion endpoint immediately returns `HTTP 202 Accepted` in ~23ms by queuing the event onto a Redis Stream. The host application is never blocked by database overhead."*

---

### 3. Issue Grouping & Cryptographic Fingerprinting (1:30 – 2:15)
- **Action**: Navigate to **Issues**. Click on the newly ingested `PaymentGatewayTimeout` issue.
- **Narrative**:
  > *"Notice how ReleaseGuard groups error events into issues using normalized stack trace fingerprinting. Transient line numbers and memory pointers are stripped, hashing the frame hierarchy with SHA-256. Even across hundreds of simultaneous client errors, all events collapse into a single actionable issue record."*

---

### 4. Releases & Deployment Correlation (2:15 – 2:45)
- **Action**: Navigate to **Releases**. Point out release `v2.4.1`.
- **Narrative**:
  > *"ReleaseGuard correlates incoming error events directly against deployment tags and commit SHAs. Here we can immediately see that `v2.4.1` deployed 20 minutes ago and immediately preceded the spike in payment timeouts."*

---

### 5. Feature Flags & Deterministic Rollout (2:45 – 3:30)
- **Action**: Navigate to **Feature Flags**. Open the flag `new_checkout_flow`.
- **Narrative**:
  > *"Feature flags in ReleaseGuard use deterministic CRC32 evaluation. A user assigned to a 25% canary rollout stays consistently in that bucket across all sessions without server-side database lookups. Config polling is served in under 7ms using HTTP ETag caching."*

---

### 6. Incident Creation & Scope Association (3:30 – 4:15)
- **Action**: Navigate to **Incidents**. Open Incident **#3: Performance Degradation & Timeouts on Checkout Flow**.
- **Narrative**:
  > *"Notice the Phase 16 information architecture. The top shows high-level status highlights: Severity (Critical), Environment (production), Active Duration (42m), and Correlated Impact (1 Linked Issue, 42 Events). Directly below is the investigation workspace showing the linked issue and activity timeline."*

---

### 7. Controlled Reversible Mitigation (Kill Switch) (4:15 – 5:00)
- **Action**: Under **Feature-Flag Mitigations**, show the active mitigation for `new_checkout_flow`.
- **Narrative**:
  > *"When the incident escalated, the on-call engineer applied a controlled kill switch. Notice the `Pre-Mitigation Snapshot`: ReleaseGuard recorded that the flag was originally `enabled: true` with `rollout: 100%`. Applying the kill switch immediately set rollout to 0% and disabled the flag in production, halting the error spike."*

---

### 8. Reversible Rollback (Restore Configuration) (5:00 – 5:30)
- **Action**: Click **"Revert Mitigation"** (or show the confirmation modal).
- **Narrative**:
  > *"Once the patch is prepared or verified, the engineer clicks 'Revert Mitigation'. ReleaseGuard restores the exact pre-mitigation state without requiring anyone to remember previous percentage settings. Every action is recorded in the immutable audit trail."*

---

### 9. AI Incident Copilot: Executive Summary & Hypotheses (5:30 – 6:30)
- **Action**: Scroll to **AI Incident Copilot** at the bottom of Incident #3.
- **Narrative**:
  > *"ReleaseGuard includes a built-in AI Incident Copilot powered by Gemini (with automated low-latency failover to Flash Lite). Notice how clean the interface is:
  > - **Executive Summary**: A concise breakdown of the incident.
  > - **Root-Cause Hypotheses**: H1 and H2.
  > Click 'View Observed Evidence & Inference Detail': ReleaseGuard strictly separates observed telemetry facts (in green) from AI deductive reasoning (in purple).
  > - **Evidence & Uncertainties**: Collapsed by default to avoid visual overload, expandable in one click."*

---

### 10. Conversational Copilot Chat & Grounding (6:30 – 7:15)
- **Action**: Click the suggested question pill: *"Why do you think H1 is probable?"*
- **Narrative**:
  > *"Copilot answers using only authorized project incident telemetry and persisted analysis context. Every claim includes verifiable citation badges: Issue #1, Release v2.4.1, Flag `new_checkout_flow`. If we ask about missing telemetry like 'What was database connection pool usage?', Copilot explicitly refuses to hallucinate and guides the operator where to look."*

---

### 11. Security, Secret Refusal & Safety Guarantees (7:15 – 7:45)
- **Action**: Show the mandatory safety banner:
  > *`AI-generated analysis is advisory. Verify evidence before taking action. AI does not automatically modify feature flags, releases, or incident status.`*
- **Narrative**:
  > *"ReleaseGuard enforces strict safety invariants:
  > 1. AI is strictly advisory; it has zero autonomous mutation permissions.
  > 2. Adversarial prompt injections inside stack traces or user chats are treated strictly as inert data.
  > 3. Zero secrets or API keys are ever stored in prompts or printed in logs.
  > ReleaseGuard keeps human engineers in control of every production action."*
