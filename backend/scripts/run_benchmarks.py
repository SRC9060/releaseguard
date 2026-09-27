"""
Practical Local Performance Benchmark for ReleaseGuard.
Measures latency (sample count, mean, median, p95) across key hardened endpoints:
1. Paginated issue query
2. Paginated event query
3. Config document evaluation endpoint
4. Authenticated API request
5. Bulk event ingestion (HTTP 202)
6. Hardened worker batch processing
"""

import os
import sys
import time
import uuid

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fakeredis
import statistics
from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.db import SessionLocal, get_db
from app.main import app
from app.models import ErrorEvent, FeatureFlag, FlagSetting, Issue, Membership, Project, Rollout, Tenant, User
from app.queue import EventQueue, get_queue
from app.worker import IngestionWorker


def run_benchmarks():
    print("=" * 70)
    print("ReleaseGuard v0.1 - Practical Local Performance Benchmarks")
    print("=" * 70)

    fake_queue = EventQueue(redis_client=fakeredis.FakeRedis(decode_responses=True))
    app.dependency_overrides[get_queue] = lambda: fake_queue

    client = TestClient(app)
    db = SessionLocal()

    # Setup test data
    tenant = Tenant(name="Bench Org", slug=f"bench-{uuid.uuid4().hex[:6]}")
    db.add(tenant)
    db.flush()

    user = User(email=f"bench_{uuid.uuid4().hex[:6]}@example.com", password_hash="dummy", is_active=True)
    db.add(user)
    db.flush()

    membership = Membership(tenant_id=tenant.id, user_id=user.id, role="owner")
    db.add(membership)

    project = Project(name="Bench Project", tenant_id=tenant.id, api_key=f"rg_live_{uuid.uuid4().hex}")
    db.add(project)
    db.flush()

    # Seed 50 issues and 200 events
    issues = []
    for i in range(50):
        iss = Issue(
            project_id=project.id,
            fingerprint=f"bench_fp_{i}_{uuid.uuid4().hex}",
            title=f"BenchError: failure {i}",
            count=4,
            status="unresolved",
            first_seen=time.strftime("%Y-%m-%d %H:%M:%S"),
            last_seen=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        db.add(iss)
        issues.append(iss)
    db.flush()

    target_issue = issues[0]
    for i in range(100):
        ev = ErrorEvent(
            event_id=f"bench_ev_{i}_{uuid.uuid4().hex[:8]}",
            project_id=project.id,
            issue_id=target_issue.id,
            exception_type="BenchError",
            message=f"Event {i}",
            stack_trace="bench trace",
            received_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        db.add(ev)

    # Seed flag for config endpoint
    flag = FeatureFlag(project_id=project.id, key="bench_flag", name="Bench Flag")
    db.add(flag)
    db.flush()

    db.commit()

    token = create_access_token(user.id)
    auth_headers = {"Authorization": f"Bearer {token}"}
    ingest_headers = {"X-ReleaseGuard-Key": project.api_key}

    results = {}

    def measure(name, func, samples=50):
        latencies = []
        # Warm-up
        for _ in range(5):
            func()
        # Measurement
        for _ in range(samples):
            t0 = time.perf_counter()
            func()
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)  # ms

        mean_val = float(statistics.mean(latencies))
        median_val = float(statistics.median(latencies))
        sorted_lat = sorted(latencies)
        p95_idx = int(round(0.95 * (len(sorted_lat) - 1)))
        p95_val = float(sorted_lat[p95_idx])
        results[name] = {
            "samples": samples,
            "mean_ms": round(mean_val, 2),
            "median_ms": round(median_val, 2),
            "p95_ms": round(p95_val, 2),
        }
        print(f"[{name}] {samples} samples | Mean: {mean_val:.2f}ms | Median: {median_val:.2f}ms | P95: {p95_val:.2f}ms")

    # 1. Paginated Issue Query
    measure(
        "Paginated Issue Query (limit=20)",
        lambda: client.get(f"/api/v1/projects/{project.id}/issues?limit=20&offset=0"),
        samples=50,
    )

    # 2. Paginated Event Query
    measure(
        "Paginated Event Query (limit=20)",
        lambda: client.get(f"/api/v1/projects/{project.id}/issues/{target_issue.id}/events?limit=20&offset=0"),
        samples=50,
    )

    # 3. Config Evaluation Endpoint
    measure(
        "Config Evaluation Endpoint",
        lambda: client.get(f"/api/v1/projects/{project.id}/config?environment=production"),
        samples=50,
    )

    # 4. Authenticated API Request
    measure(
        "Authenticated API Request",
        lambda: client.get(f"/api/v1/tenants/{tenant.id}/projects/{project.id}", headers=auth_headers),
        samples=50,
    )

    # 5. Bulk Event Ingestion (25 events)
    bulk_payload = {
        "events": [
            {
                "event_id": f"bench_b_{i}_{uuid.uuid4().hex[:6]}",
                "exception_type": "BulkBenchError",
                "message": f"Bulk msg {i}",
                "stack_trace": "bench trace",
            }
            for i in range(25)
        ]
    }
    measure(
        "Bulk Event Ingestion (25 events)",
        lambda: client.post(f"/api/v1/projects/{project.id}/events/bulk", json=bulk_payload, headers=ingest_headers),
        samples=50,
    )

    # 6. Worker Batch Processing
    worker = IngestionWorker(queue=fake_queue)
    def worker_bench():
        fake_queue.enqueue_events(
            project.id,
            [
                {
                    "event_id": f"w_bench_{i}_{uuid.uuid4().hex[:6]}",
                    "exception_type": "WorkerError",
                    "message": "w msg",
                    "stack_trace": "w trace",
                }
                for i in range(10)
            ],
        )
        worker.process_next_batch(batch_size=10)

    measure(
        "Hardened Worker Batch Processing (10 events)",
        worker_bench,
        samples=25,
    )

    db.close()
    print("=" * 70)
    print("Benchmarks completed successfully.")
    return results


if __name__ == "__main__":
    run_benchmarks()
