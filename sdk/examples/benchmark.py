"""
ReleaseGuard SDK Benchmarking Script.
Measures:
1. Application thread latency of capture_exception()
2. Events queued per second
3. Worker transmission throughput
4. Bounded queue overflow behavior (events dropped when queue full)
"""

import os
import sys
import time
from typing import Any

# Ensure releaseguard_sdk is importable
current_dir = os.path.dirname(os.path.abspath(__file__))
sdk_root = os.path.abspath(os.path.join(current_dir, "..", "python"))
if sdk_root not in sys.path:
    sys.path.insert(0, sdk_root)

import releaseguard_sdk
from releaseguard_sdk.config import Config
from releaseguard_sdk.client import ReleaseGuardClient
from releaseguard_sdk.transport import BaseTransport
from releaseguard_sdk.event import Event


class MockBenchmarkTransport(BaseTransport):
    """Zero-latency mock transport for measuring internal worker overhead."""

    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.call_count = 0

    def send_event(self, event: Event) -> dict[str, Any]:
        self.call_count += 1
        if self.delay > 0:
            time.sleep(self.delay)
        return {"event_id": self.call_count}


def run_benchmark():
    print("=" * 65)
    print("ReleaseGuard Python SDK — Performance & Latency Benchmark")
    print("=" * 65)

    # -------------------------------------------------------------
    # 1. Measure Application Thread capture_exception() Latency
    # -------------------------------------------------------------
    num_samples = 5000
    mock_transport = MockBenchmarkTransport(delay=0.0)
    config = Config(
        project_id=1,
        max_queue_size=10000,
        flush_interval=0.01,
        batch_size=50,
    )
    client = ReleaseGuardClient(config=config, transport=mock_transport)

    latencies_us = []

    print(f"\n[1] Measuring capture_exception() latency over {num_samples} invocations...")
    for _ in range(num_samples):
        try:
            raise RuntimeError("Benchmark synthetic failure")
        except RuntimeError:
            t0 = time.perf_counter()
            client.capture_exception()
            t1 = time.perf_counter()
            latencies_us.append((t1 - t0) * 1_000_000)

    avg_us = sum(latencies_us) / len(latencies_us)
    min_us = min(latencies_us)
    max_us = max(latencies_us)
    latencies_us.sort()
    p50_us = latencies_us[int(num_samples * 0.50)]
    p95_us = latencies_us[int(num_samples * 0.95)]
    p99_us = latencies_us[int(num_samples * 0.99)]

    events_per_sec = num_samples / (sum(latencies_us) / 1_000_000)

    print(f"  - Mean Latency:         {avg_us:.2f} us")
    print(f"  - Median (p50):         {p50_us:.2f} us")
    print(f"  - 95th Percentile:      {p95_us:.2f} us")
    print(f"  - 99th Percentile:      {p99_us:.2f} us")
    print(f"  - Min / Max:            {min_us:.2f} us / {max_us:.2f} us")
    print(f"  - Queue Throughput:     {events_per_sec:,.0f} events/second (app thread)")

    # -------------------------------------------------------------
    # 2. Worker Transmission Throughput
    # -------------------------------------------------------------
    print("\n[2] Measuring background worker transmission throughput...")
    worker_start = time.perf_counter()
    client.flush(timeout=5.0)
    worker_elapsed = time.perf_counter() - worker_start
    worker_eps = client.stats.sent / worker_elapsed if worker_elapsed > 0 else 0

    print(f"  - Events Transmitted:   {client.stats.sent}")
    print(f"  - Worker Time to Drain: {worker_elapsed*1000:.2f} ms")
    print(f"  - Worker Throughput:    {worker_eps:,.0f} events/second")

    client.shutdown(timeout=1.0)

    # -------------------------------------------------------------
    # 3. Bounded Queue Overflow Benchmark
    # -------------------------------------------------------------
    print("\n[3] Measuring Bounded Queue Overflow Behavior...")
    queue_cap = 100
    burst_count = 500

    # Slow transport to guarantee queue fills up
    slow_transport = MockBenchmarkTransport(delay=0.01)
    overflow_config = Config(
        project_id=1,
        max_queue_size=queue_cap,
        flush_interval=1.0,
        batch_size=10,
    )
    overflow_client = ReleaseGuardClient(config=overflow_config, transport=slow_transport)

    for i in range(burst_count):
        try:
            raise KeyError(f"Key #{i}")
        except KeyError:
            overflow_client.capture_exception()

    stats = overflow_client.stats
    print(f"  - Queue Capacity:       {queue_cap}")
    print(f"  - Events Injected:      {burst_count}")
    print(f"  - Events Queued:        {stats.queued}")
    print(f"  - Events Dropped:       {stats.dropped}")
    print(f"  - Overflow Protection:  {'ACTIVE (Bounded memory)' if stats.dropped > 0 else 'UNEXPECTED'}")

    overflow_client.shutdown(timeout=1.0)

    print("\n" + "=" * 65)
    print("Benchmark complete.")
    print("=" * 65)


if __name__ == "__main__":
    run_benchmark()
