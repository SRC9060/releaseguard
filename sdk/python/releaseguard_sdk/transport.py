"""
HTTP Transport implementation for ReleaseGuard SDK.
Uses standard-library urllib to maintain zero external dependencies.
"""

from abc import ABC, abstractmethod
import json
import urllib.error
import urllib.request
from typing import Any

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


class HttpTransport(BaseTransport):
    def __init__(self, config: Config):
        self.config = config
        self.endpoint = f"{config.base_url}/api/v1/projects/{config.project_id}/events"

    def send_event(self, event: Event) -> dict[str, Any]:
        data = json.dumps(event.to_dict()).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "releaseguard-python-sdk/0.1.0",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        req = urllib.request.Request(
            url=self.endpoint,
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
                f"Network failure connecting to {self.endpoint}: {net_err}"
            ) from net_err
        except Exception as unexpected:
            raise TransientTransportError(
                f"Unexpected transport failure: {unexpected}"
            ) from unexpected
