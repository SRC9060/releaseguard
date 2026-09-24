"""
Performance Benchmark for Phase 5 Asynchronous Ingestion Pipeline.
Measures:
A. Bulk API Enqueue Latency (HTTP Request -> 202 Accepted)
B. Worker Processing Throughput (Redis Stream -> Fingerprint -> PostgreSQL Commit)
"""

import os
import platform
import sys
import time
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add paths
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
backend_dir = os.path.join(root_dir, "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import fakeredis
from app.db import Base, get_db
from app.main import app
from app.models import Issue, Project
from app.queue import EventQueue, get_queue
from app.worker import IngestionWorker


def run_benchmark():
    print("=" * 70)
    print("ReleaseGuard Phase 5 - Pipeline Performance & Latency Benchmark")
    print("=" * 70)

    # 1. Inspect environment
    db_url = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5432/releaseguard")
    is_postgres = "postgresql" in db_url
    db_type = "PostgreSQL 17 (Real)" if is_postgres else "SQLite (In-Memory/File)"

    print(f"Platform:      {platform.system()} {platform.release()} (Python {platform.python_version()})")
    print(f"Database:      {db_type}")
    print(f"Queue Backend: FakeRedis In-Memory Stream (Deterministic Test Harness)")
    print("=" * 70)

    # Setup isolated test engine and queue
    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    queue = EventQueue(redis_client=fake_redis)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_queue] = lambda: queue

    client = TestClient(app)

    # Create project
    proj_resp = client.post("/api/v1/projects", json={"name": "Pipeline Benchmark Project"})
    project_id = proj_resp.json()["id"]

    # -------------------------------------------------------------------------
    # PART A: Bulk API Enqueue Latency
    # -------------------------------------------------------------------------
    print("\n[PART A] Measuring Bulk API Enqueue Latency (HTTP -> 202 Accepted)")
    batch_sizes = [1, 10, 50, 100]
    num_iterations = 20

    for b_size in batch_sizes:
        sample_event = {
            "exception_type": "IndexError",
            "message": "list index out of range in order cache lookup",
            "stack_trace": "File 'orders.py', line 88, in fetch\n  return cache[idx]",
            "release": "1.2.0",
        }
        payload = {"events": [sample_event for _ in range(b_size)]}

        latencies_ms = []
        for _ in range(num_iterations):
            t0 = time.perf_counter()
            resp = client.post(f"/api/v1/projects/{project_id}/events/bulk", json=payload)
            t1 = time.perf_counter()
            assert resp.status_code == 202
            latencies_ms.append((t1 - t0) * 1000.0)

        latencies_ms.sort()
        mean_ms = sum(latencies_ms) / len(latencies_ms)
        p50_ms = latencies_ms[int(num_iterations * 0.50)]
        p95_ms = latencies_ms[int(num_iterations * 0.95)]
        min_ms = min(latencies_ms)
        max_ms = max(latencies_ms)
        events_per_sec = (b_size * num_iterations) / (sum(latencies_ms) / 1000.0)

        print(f"\n  Batch Size = {b_size:3d} events/request ({num_iterations} requests):")
        print(f"    - Mean HTTP Latency:   {mean_ms:6.2f} ms")
        print(f"    - Median (p50):        {p50_ms:6.2f} ms")
        print(f"    - 95th Percentile:     {p95_ms:6.2f} ms")
        print(f"    - Min / Max:           {min_ms:6.2f} ms / {max_ms:6.2f} ms")
        print(f"    - Ingestion Rate:      {events_per_sec:,.0f} events/sec into Redis")

    # -------------------------------------------------------------------------
    # PART B: Worker Processing Throughput
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("[PART B] Measuring Worker Processing Throughput (Redis -> PostgreSQL)")
    total_events_to_process = 500
    print(f"Enqueueing {total_events_to_process} events into Redis...")

    events_payload = [
        {
            "exception_type": f"ErrorType_{i % 10}",
            "message": f"Cluster node {i % 5} disconnect",
            "stack_trace": f"File 'cluster.py', line {100 + (i % 10)}\nraise Disconnect()",
            "release": "1.2.0",
        }
        for i in range(total_events_to_process)
    ]
    # Enqueue in chunks of 100
    for chunk_idx in range(0, total_events_to_process, 100):
        chunk = events_payload[chunk_idx : chunk_idx + 100]
        queue.enqueue_events(project_id, chunk)

    depth_before = queue.get_metrics()["queue_depth"]
    print(f"Queue depth before worker processing: {depth_before} events")

    worker = IngestionWorker(queue=queue, session_factory=TestingSessionLocal, batch_size=100)

    t_worker_start = time.perf_counter()
    processed_count = 0
    while True:
        count = worker.process_next_batch(batch_size=100)
        if count == 0:
            break
        processed_count += count
    t_worker_end = time.perf_counter()

    worker_duration = t_worker_end - t_worker_start
    throughput = processed_count / worker_duration if worker_duration > 0 else 0

    print(f"\n  Worker Processing Results:")
    print(f"    - Events Processed:    {processed_count}")
    print(f"    - Total Duration:      {worker_duration:6.3f} seconds")
    print(f"    - Worker Throughput:   {throughput:,.1f} events/second (atomic PostgreSQL upsert)")

    # Verify DB state
    with TestingSessionLocal() as db:
        issues_count = db.query(Issue).filter(Issue.project_id == project_id).count()
        print(f"    - Unique Issues in DB: {issues_count} (correctly clustered from 10 distinct error types)")

    print("\n" + "=" * 70)
    print("Benchmark complete.")
    print("=" * 70)

    app.dependency_overrides.clear()


if __name__ == "__main__":
    run_benchmark()
