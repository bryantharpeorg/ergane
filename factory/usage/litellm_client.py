"""The single seam between this component and the LiteLLM proxy.

Every proxy call in the factory goes through here, which is what makes the
component's credential and enforcement invariants checkable in one file:

- **The master key stops at this boundary.** It is read from the worker-host
  environment (`from_env`), lives only in this client's request headers, and is
  redacted out of anything a caller can observe — a failed call raises
  `LiteLLMError` carrying an HTTP status and a scrubbed proxy message, never the
  credential that authenticated it (FR-009, SC-004).
- **No cap is ever sent.** `issue_key` builds a `/key/generate` body of alias,
  model list, metadata and TTL. `max_budget` is absent by construction, not by
  configuration, because budget enforcement is deferred to spec 004 (D-021,
  FR-004).
- **Reads are complete; writes are tolerant.** `fetch_spend_log_rows` drains
  every page — a client that stopped at page one would silently under-report an
  attempt's usage, the exact fabrication FR-005 forbids — and `revoke_key`
  reports an already-absent key as `False` rather than raising, because Temporal
  runs teardown at least once (R2, R3, FR-002).

Rows come back exactly as the proxy sent them: interpreting them, including the
absent-versus-zero cache rule, belongs to `aggregate.py`. Retries belong to the
workflow's retry policy (R4), so nothing here loops on failure.
"""

from __future__ import annotations

import os
from types import TracebackType
from typing import Any, Iterable, Mapping

import httpx

#: R5: the backstop against teardown never running, not a run limit — long
#: enough that no legitimate attempt is truncated, short enough that a leaked
#: key dies within a day.
DEFAULT_KEY_TTL = "24h"

#: Rows requested per `/spend/logs/v2` page. Pagination is driven by the
#: response's `total_pages`, so the proxy is free to return fewer.
SPEND_LOG_PAGE_SIZE = 100

#: Loop guard: a proxy that never reports a last page is a bug, and hanging on
#: it during teardown would be worse than failing loudly.
MAX_SPEND_LOG_PAGES = 1_000

DEFAULT_TIMEOUT_SECONDS = 30.0

PROXY_URL_ENV = "LITELLM_PROXY_URL"
MASTER_KEY_ENV = "LITELLM_MASTER_KEY"

#: Deleting a key the proxy no longer knows about. LiteLLM answers 404, older
#: builds 400; both mean the same thing to a teardown that ran twice.
_KEY_ALREADY_GONE = frozenset({400, 404})

_REDACTED = "<redacted>"


class LiteLLMError(Exception):
    """A proxy call that did not succeed, described without the credential.

    `status` is the HTTP status when the proxy answered — teardown branches to
    its snapshot fallback on 404 (R3) — and `None` when the request never got
    that far (connection refused, timeout, unparseable body).
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class LiteLLMClient:
    """Async admin client for the four endpoints this component touches.

    Construct with an explicit `base_url`/`master_key` in tests, or with
    `from_env` in activities, where the credential must come from the worker
    host's environment rather than an activity input (contracts/activities.md).
    Use as an async context manager; the underlying connection pool is closed on
    exit.
    """

    def __init__(
        self,
        *,
        base_url: str,
        master_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._master_key = master_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {master_key}"},
            transport=transport,
            timeout=timeout,
        )

    @classmethod
    def from_env(
        cls,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> LiteLLMClient:
        """Build a client from the worker host's environment.

        Raises `LiteLLMError` naming the missing variable — the name only; an
        environment value never enters an error message (FR-009).
        """
        base_url = os.environ.get(PROXY_URL_ENV)
        if not base_url:
            raise LiteLLMError(f"{PROXY_URL_ENV} is not set in the worker environment")
        if not os.environ.get(MASTER_KEY_ENV):
            raise LiteLLMError(f"{MASTER_KEY_ENV} is not set in the worker environment")

        return cls(
            base_url=base_url,
            master_key=os.environ[MASTER_KEY_ENV],
            transport=transport,
            timeout=timeout,
        )

    # --- lifecycle ----------------------------------------------------------

    async def __aenter__(self) -> LiteLLMClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def __repr__(self) -> str:
        # Explicit, so a client rendered into a traceback frame cannot spill the
        # credential it holds.
        return f"{type(self).__name__}(base_url={self.base_url!r})"

    # --- proxy operations ---------------------------------------------------

    async def issue_key(
        self,
        *,
        key_alias: str,
        models: Iterable[str],
        metadata: Mapping[str, Any] | None = None,
        ttl: str = DEFAULT_KEY_TTL,
    ) -> str:
        """Mint the attempt's virtual key and return it (R1, FR-001).

        The body carries the attribution alias, the persona's allowed models,
        the dimension metadata and a TTL. It carries no `max_budget` and no
        `soft_budget`: this client has no way to express a cap (D-021).
        """
        body = await self._call(
            "POST",
            "/key/generate",
            payload={
                "key_alias": key_alias,
                "models": list(models),
                "metadata": dict(metadata or {}),
                "duration": ttl,
            },
        )

        key = body.get("key")
        if not isinstance(key, str) or not key:
            raise LiteLLMError("/key/generate succeeded but returned no key")
        return key

    async def get_spend(self, key: str) -> float:
        """The proxy's computed spend for `key` (R9's heartbeat read, R3 step 1).

        A returned `0.0` is a measurement — an unpriced model spends nothing —
        so unknown usage is this method raising, never a zero it invented
        (FR-005). Raises with `status == 404` once the key has been revoked,
        which is the signal teardown falls back on.
        """
        body = await self._call("GET", "/key/info", params={"key": key})

        info = body.get("info")
        spend = info.get("spend") if isinstance(info, dict) else body.get("spend")
        if isinstance(spend, bool) or not isinstance(spend, (int, float)):
            raise LiteLLMError("/key/info returned no numeric spend for the attempt key")
        return float(spend)

    async def fetch_spend_log_rows(self, key: str) -> list[dict[str, Any]]:
        """Every per-request spend row recorded against `key`, verbatim (R2).

        Pages are drained to the last one the proxy reports; rows are passed
        through untouched, cache metadata and all, for `aggregate.py` to
        interpret.
        """
        rows: list[dict[str, Any]] = []

        for page in range(1, MAX_SPEND_LOG_PAGES + 1):
            body = await self._call(
                "GET",
                "/spend/logs/v2",
                params={
                    "api_key": key,
                    "page": page,
                    "page_size": SPEND_LOG_PAGE_SIZE,
                },
            )

            data = body.get("data")
            if not isinstance(data, list):
                raise LiteLLMError("/spend/logs/v2 returned no row array")
            rows.extend(row for row in data if isinstance(row, dict))

            total_pages = body.get("total_pages")
            if isinstance(total_pages, int) and not isinstance(total_pages, bool):
                if page >= total_pages:
                    return rows
            elif not data:
                # No page count to trust: an empty page is the end of the log.
                return rows

        raise LiteLLMError(
            f"/spend/logs/v2 did not report a last page within {MAX_SPEND_LOG_PAGES} pages"
        )

    async def revoke_key(self, key: str) -> bool:
        """Delete the attempt's key; `True` if this call removed it.

        `False` means it was already gone — an expired TTL, or a teardown
        Temporal ran twice — which is a normal outcome of the last step of
        teardown, not a failure (R3, FR-002).
        """
        try:
            await self._call("POST", "/key/delete", payload={"keys": [key]})
        except LiteLLMError as exc:
            if exc.status in _KEY_ALREADY_GONE:
                return False
            raise
        return True

    # --- plumbing -----------------------------------------------------------

    async def _call(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """One admin request. Any failure becomes a credential-free error."""
        try:
            response = await self._client.request(method, path, params=params, json=payload)
        except httpx.HTTPError as exc:
            raise LiteLLMError(
                f"{method} {path} failed: {self._scrub(str(exc))}"
            ) from exc

        if response.status_code >= 400:
            raise LiteLLMError(
                f"{method} {path} -> {response.status_code}: {self._proxy_message(response)}",
                status=response.status_code,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise LiteLLMError(
                f"{method} {path} returned a non-JSON body", status=response.status_code
            ) from exc

        if not isinstance(body, dict):
            raise LiteLLMError(
                f"{method} {path} returned {type(body).__name__}, expected a JSON object",
                status=response.status_code,
            )
        return body

    def _proxy_message(self, response: httpx.Response) -> str:
        """The proxy's own explanation, scrubbed and bounded."""
        try:
            body: Any = response.json()
        except ValueError:
            body = None

        detail: Any = None
        if isinstance(body, dict):
            error = body.get("error")
            detail = error.get("message") if isinstance(error, dict) else error
            if detail is None:
                detail = body.get("detail")
        if detail is None:
            detail = response.text

        return self._scrub(str(detail))[:500]

    def _scrub(self, text: str) -> str:
        """Remove the master key from text that is about to become an error.

        The fake proxy never echoes credentials and a well-behaved LiteLLM does
        not either, but an error path is the one place a credential must not
        reach by accident (SC-004), so the guarantee is enforced here rather
        than assumed of the server.
        """
        return text.replace(self._master_key, _REDACTED) if self._master_key else text
