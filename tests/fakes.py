"""Shared offline fakes for the test suite (never touches the real network)."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Union


class FakeResp:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, url: str = "", status_code: int = 200,
                 text: str = "", headers: Optional[dict] = None):
        self.url = url
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class FakeSession:
    """Mimics requests.Session.get() for HttpClient tests.

    `responses` may be:
      * a dict  {url: FakeResp}
      * a list  (FIFO queue popped on each call)
      * a callable(url) -> FakeResp
    """

    def __init__(self,
                 responses: Union[Dict[str, FakeResp], List[FakeResp], Callable, None] = None,
                 default: Optional[FakeResp] = None):
        self._responses = responses
        self._default = default
        self.calls: List[str] = []
        self.headers: dict = {}

    def get(self, url, timeout=None, allow_redirects=True, stream=False, **kwargs):
        self.calls.append(url)
        r = self._responses
        if callable(r):
            return r(url)
        if isinstance(r, dict):
            return r.get(url, self._default or FakeResp(url, 200, ""))
        if isinstance(r, list):
            return r.pop(0)
        return self._default or FakeResp(url, 200, "")

    def close(self):
        pass


class FakeClock:
    """Deterministic replacement for the `time` module inside http_client.

    time() only advances when sleep() is called, so tests can assert exactly
    how long the client *would* have slept without any real waiting.
    """

    def __init__(self, start: float = 1000.0):
        self.t = start
        self.slept: List[float] = []

    def time(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds
