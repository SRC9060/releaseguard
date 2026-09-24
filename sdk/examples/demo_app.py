import json
import os
import sys
import time
import urllib.request
import urllib.error

# Ensure releaseguard_sdk is importable
current_dir = os.path.dirname(os.path.abspath(__file__))
sdk_root = os.path.abspath(os.path.join(current_dir, "..", "python"))
if sdk_root not in sys.path:
    sys.path.insert(0, sdk_root)

import releaseguard_sdk


def ensure_demo_project(base_url: str) -> int:
    """Ensures a demo project exists in ReleaseGuard and returns its ID."""
    url = f"{base_url.rstrip('/')}/api/v1/projects"
    payload = json.dumps({"name": "SDK Demo Application"}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["id"]
    except urllib.error.HTTPError as err:
        print(f"Note: Could not auto-create project (HTTP {err.code}). Using project_id=1")
        return 1
    except Exception as exc:
        print(f"Note: Backend unreachable ({exc}). Using project_id=1")
        return 1


def main():
    base_url = os.getenv("RELEASEGUARD_URL", "http://127.0.0.1:8000")
    project_id = int(os.getenv("RELEASEGUARD_PROJECT_ID", "0"))

    print("=" * 60)
    print("ReleaseGuard Python SDK - Live Demo")
    print(f"Connecting to: {base_url}")
    print("=" * 60)

    if project_id == 0:
        project_id = ensure_demo_project(base_url)

    print(f"Using Project ID: {project_id}")

    # 1. Initialize SDK
    client = releaseguard_sdk.init(
        project_id=project_id,
        base_url=base_url,
        release="1.0.0",
        environment="demo",
        debug=False,
    )

    # 2. Capture a one-off exception
    print("\n[1] Capturing single ZeroDivisionError...")
    try:
        result = 10 / 0
    except ZeroDivisionError:
        releaseguard_sdk.capture_exception()
        print("  -> capture_exception() returned immediately (non-blocking).")

    # 3. Simulate high-frequency identical errors (e.g. downstream service outage)
    num_errors = 100
    print(f"\n[2] Generating {num_errors} identical ValueError events in a rapid loop...")
    start_time = time.time()

    for i in range(num_errors):
        try:
            raise ValueError("Order payment payload missing currency code")
        except ValueError:
            releaseguard_sdk.capture_exception()

    elapsed = time.time() - start_time
    print(f"  -> Generated and enqueued {num_errors} events in {elapsed*1000:.2f} ms")
    print(f"  -> Average enqueue latency per event: {(elapsed / num_errors)*1000:.4f} ms")

    # 4. Flush the background worker queue
    print("\n[3] Flushing background worker queue...")
    flushed = releaseguard_sdk.flush(timeout=5.0)
    print(f"  -> Flush completed: {flushed}")

    # 5. Display SDK Telemetry Counters
    stats = client.stats
    print("\n[4] SDK Internal Telemetry:")
    print(f"  - Events Queued:  {stats.queued}")
    print(f"  - Events Sent:    {stats.sent}")
    print(f"  - Events Dropped: {stats.dropped}")
    print(f"  - Events Failed:  {stats.failed}")

    # Clean shutdown
    releaseguard_sdk.shutdown(timeout=2.0)
    print("\n[5] SDK shutdown cleanly.")

    # 6. Verify grouped issues in backend
    print("\n[6] Querying ReleaseGuard backend issues:")
    issues_url = f"{base_url.rstrip('/')}/api/v1/projects/{project_id}/issues"
    try:
        req = urllib.request.Request(issues_url, method="GET")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            issues = json.loads(resp.read().decode("utf-8"))
            for issue in issues:
                print(f"  - Issue #{issue['id']}: [{issue['title']}] -> count = {issue['count']}")
    except Exception as exc:
        print(f"  Note: Could not query issues ({exc})")

    print("\nDemo complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
