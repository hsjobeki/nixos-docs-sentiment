"""Minimal stdlib HTTP client: throttling + bounded retry with backoff.

Kept dependency-free (urllib) so the tool needs nothing outside the pinned
Python interpreter. Collectors own their own error policy; this layer only
retries transient failures (429/5xx, network errors) and raises ``HttpError``
on hard failures so callers can degrade a single source gracefully.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request


class HttpError(Exception):
    pass


class Http:
    def __init__(self, user_agent: str, delay: float = 1.0,
                 retries: int = 3, timeout: float = 30.0) -> None:
        self.ua = user_agent
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self._last = 0.0

    def _throttle(self) -> None:
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def get_json(self, url: str, headers: dict | None = None):
        h = {"User-Agent": self.ua, "Accept": "application/json"}
        if headers:
            h.update(headers)
        last: Exception | None = None
        for attempt in range(self.retries):
            self._throttle()
            req = urllib.request.Request(url, headers=h)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504):
                    ra = e.headers.get("Retry-After")
                    back = float(ra) if (ra and ra.isdigit()) else float(2 ** attempt)
                    last = e
                    time.sleep(min(back, 30.0))
                    continue
                raise HttpError(f"{e.code} {e.reason} for {url}") from e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = e
                time.sleep(float(2 ** attempt))
                continue
        raise HttpError(f"exhausted {self.retries} retries for {url}: {last}")

    def post_form(self, url: str, data: dict, headers: dict | None = None):
        h = {"User-Agent": self.ua, "Accept": "application/json",
             "Content-Type": "application/x-www-form-urlencoded"}
        if headers:
            h.update(headers)
        body = urllib.parse.urlencode(data).encode("utf-8")
        self._throttle()
        req = urllib.request.Request(url, data=body, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise HttpError(f"{e.code} {e.reason} for {url}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise HttpError(f"network error for {url}: {e}") from e
