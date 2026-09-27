"""
HTTP Transport implementation for ReleaseGuard SDK.
Uses standard-library urllib to maintain zero external dependencies.
Supports both bulk ingestion and single-event endpoints.
"""

from abc import ABC, abstractmethod
import json
from typing import Any
import urllib.error
import urllib.request

from releaseguard_sdk.config import Config
from releaseguard_sdk.event import Event


class TransportError(Exception):
    """Base transport error."""


class PermanentClientError(TransportError):
    """4xx HTTP error that should not be retried."""


class TransientTransportError(TransportError):
    """Network, timeout, or 5xx error eligible for retry."""


class BaseTransport(ABC):
    @abstractmethod
    def send_event(self, event: Event) -> dict[str, Any]:
        """Send a single event."""

    def send_batch(self, events: list[Event]) -> dict[str, Any]:
        """Send a batch of events. Defaults to sending each event individually."""
        res: dict[str, Any] = {}
        for event in events:
            res = self.send_event(event)
        return res

    def get_config(
        self,
        environment: str,
        etag: str | None = None,
        user_id: str | None = None,
    ) -> tuple[int, dict[str, Any], str | None]:
        """Fetch remote configuration document. Returns (status_code, document_dict, etag)."""
        return 200, {}, None


class HttpTransport(BaseTransport):
    def __init__(self, config: Config):
        self.config = config
        base = config.base_url.rstrip("/")
        self.single_endpoint = f"{base}/api/v1/projects/{config.project_id}/events"
        self.bulk_endpoint = f"{base}/api/v1/projects/{config.project_id}/events/bulk"

    def get_config(
        self,
        environment: str,
        etag: str | None = None,
        user_id: str | None = None,
    ) -> tuple[int, dict[str, Any], str | None]:
        base = self.config.base_url.rstrip("/")
        url = f"{base}/api/v1/config/{self.config.project_id}/{environment}"
        if user_id:
            import urllib.parse
            url += f"?user_id={urllib.parse.quote(str(user_id))}"

        headers = {
            "Accept": "application/json",
            "User-Agent": "releaseguard-python-sdk/0.2.0",
        }
        if self.config.api_key:
            headers["X-ReleaseGuard-Key"] = self.config.api_key
        if etag:
            headers["If-None-Match"] = etag

        req = urllib.request.Request(url=url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                resp_etag = resp.headers.get("ETag")
                body = resp.read().decode("utf-8")
                return 200, json.loads(body) if body else {}, resp_etag
        except urllib.error.HTTPError as err:
            if err.code == 304:
                return 304, {}, etag
            return err.code, {}, None
        except Exception:
            return 500, {}, None

    def send_event(self, event: Event) -> dict[str, Any]:
        return self._send_request(self.single_endpoint, event.to_dict())

    def send_batch(self, events: list[Event]) -> dict[str, Any]:
        payload = {"events": [e.to_dict() for e in events]}
        return self._send_request(self.bulk_endpoint, payload)

    def _send_request(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "releaseguard-python-sdk/0.2.0",
        }
        if self.config.api_key:
            headers["X-ReleaseGuard-Key"] = self.config.api_key
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        req = urllib.request.Request(
            url=url,
            data=data,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                resp_body = resp.read().decode("utf-8")
                return json.loads(resp_body) if resp_body else {}
        except urllib.error.HTTPError as http_err:
            code = http_err.code
            try:
                err_body = http_err.read().decode("utf-8")
            except Exception:
                err_body = ""

            if 400 <= code < 500:
                raise PermanentClientError(
                    f"HTTP {code} from ReleaseGuard: {err_body or http_err.reason}"
                ) from http_err
            else:
                raise TransientTransportError(
                    f"HTTP {code} server error from ReleaseGuard: {err_body or http_err.reason}"
                ) from http_err
        except (urllib.error.URLError, TimeoutError, OSError) as net_err:
            raise TransientTransportError(
                f"Network failure connecting to {url}: {net_err}"
            ) from net_err
        except Exception as unexpected:
            raise TransientTransportError(
                f"Unexpected transport failure: {unexpected}"
            ) from unexpected
