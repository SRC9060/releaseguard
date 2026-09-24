"""
ReleaseGuard SDK Configuration.
"""

from dataclasses import dataclass


@dataclass
class Config:
    project_id: int
    base_url: str = "http://127.0.0.1:8000"
    api_key: str = ""
    release: str | None = None
    environment: str = "production"
    max_queue_size: int = 1000
    flush_interval: float = 0.5
    batch_size: int = 20
    max_retries: int = 3
    retry_backoff: float = 0.1
    timeout: float = 5.0
    debug: bool = False

    def __post_init__(self):
        # Normalize base_url to strip trailing slashes
        if self.base_url.endswith("/"):
            self.base_url = self.base_url.rstrip("/")
