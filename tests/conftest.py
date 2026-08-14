"""Shared test fixtures: a fake LiteLLM admin API, and real fixture git repos.

`FakeLiteLLM` serves the four proxy endpoints this component touches, over an
`httpx.MockTransport` (plan.md § Testing). It is deliberately strict where the
spec's invariants live, so a violation fails at the seam rather than in an
assertion someone forgot to write:

- `POST /key/generate` rejects `max_budget`/`soft_budget` — budget enforcement is
  deferred (D-021, FR-004) and no code in this component may send a cap.
- Every route requires the master key as `Authorization: Bearer …`; a wrong or
  missing credential is a 401 whose body never echoes the offered key (FR-009,
  SC-004).
- `POST /key/delete` keeps the key's spend-log rows: rows outlive the key, which
  is what makes R3's delete-last ordering observable.

State is per-instance and every request is recorded in `calls`, so tests can
assert *ordering* (R3) as well as payload shape.

The fake is the contract-under-test for `factory/usage/litellm_client.py`; the
real-proxy smoke test (T025) is what proves the contract matches production.

The `target_repo` / `node_worktree` fixtures at the bottom go the other way: no
fake at all. Gates run real subprocesses and the diff check reads real `git`
output, so those tests get a real repository built from
`tests/fixtures/target_repo/` (see `tests/target_repo.py`) under `tmp_path`.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx
import pytest

from factory.activities.agent_activities import (
    ERGANE_ROOT_ENV,
    FACTORY_ROOT_ENV,
)
from factory.activities.notify_activities import (
    TELEGRAM_BOT_TOKEN_ENV,
    TELEGRAM_CHAT_ID_ENV,
)
from factory.activities.usage_activities import (
    ERGANE_LEDGER_PATH_ENV,
    LEDGER_PATH_ENV,
)
from factory.activities.verify_activities import (
    ERGANE_VERIFICATION_DB_PATH_ENV,
    VERIFICATION_DB_PATH_ENV,
)
from factory.env import (
    ERGANE_CONFIG_PATH_ENV,
    FACTORY_CONFIG_PATH_ENV,
)
from tests.target_repo import add_worktree, build_target_repo

FAKE_PROXY_URL = "http://litellm.test"
FAKE_MASTER_KEY = "sk-fake-master-do-not-log"

DEFAULT_PAGE_SIZE = 100

#: What `/spend/logs/v2` accepts for `start_date`/`end_date` — the real proxy's
#: own error message spells these two shapes and rejects everything else.
_SPEND_LOG_DATE = re.compile(r"\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?")
DEFAULT_MODEL = "fake-provider/CHANGEME"

# Cache detail lives only in the per-row metadata JSON (research R2).
CACHE_READ_FIELD = "cache_read_input_tokens"
CACHE_WRITE_FIELD = "cache_creation_input_tokens"


@dataclass(frozen=True)
class RecordedCall:
    """One request the fake received, in arrival order."""

    method: str
    path: str
    params: dict[str, str]
    body: dict[str, Any] | None

    @property
    def route(self) -> str:
        return f"{self.method} {self.path}"


class FakeLiteLLM:
    """Stateful in-memory stand-in for the LiteLLM proxy's admin API."""

    def __init__(
        self,
        *,
        base_url: str = FAKE_PROXY_URL,
        master_key: str = FAKE_MASTER_KEY,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.master_key = master_key

        # key -> mutable key record; dropped on delete.
        self.keys: dict[str, dict[str, Any]] = {}
        # key -> spend-log rows; retained after the key is deleted (R3).
        self.spend_rows: dict[str, list[dict[str, Any]]] = {}
        # key -> alias; retained after delete so alias filtering still resolves.
        self.aliases: dict[str, str] = {}

        # The aliases `/v1/models` advertises (US2 preflight FR-004).
        self.served_models: set[str] = set()

        self.calls: list[RecordedCall] = []

        # Test levers.
        self.max_page_size: int | None = None
        self.enforce_alias_uniqueness = False
        # A transport that drops every request, for the unreachable-proxy path
        # (FR-005): set by `make_unreachable`.
        self._refuse_requests = False

        self._failures: dict[str, list[tuple[int, str]]] = {}
        self._issued = 0

        self.transport = httpx.MockTransport(self._handle)

    # --- test-facing helpers ------------------------------------------------

    def client(self, **kwargs: Any) -> httpx.AsyncClient:
        """An `AsyncClient` wired to this fake — no credentials attached."""
        kwargs.setdefault("base_url", self.base_url)
        return httpx.AsyncClient(transport=self.transport, **kwargs)

    def add_spend_row(
        self,
        key: str,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        spend: float,
        cache_read_tokens: int | None = None,
        cache_write_tokens: int | None = None,
        model: str = DEFAULT_MODEL,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Record one request against `key`, as `/spend/logs/v2` would report it.

        Cache counters are omitted from the row's metadata when left as None —
        that is the "metric absent from the backend" case aggregation must map
        to NULL rather than 0 (FR-004).
        """
        rows = self.spend_rows.setdefault(key, [])
        additional: dict[str, int] = {}
        if cache_read_tokens is not None:
            additional[CACHE_READ_FIELD] = cache_read_tokens
        if cache_write_tokens is not None:
            additional[CACHE_WRITE_FIELD] = cache_write_tokens

        metadata: dict[str, Any] = {"user_api_key_alias": self.aliases.get(key)}
        if additional:
            metadata["additional_usage_values"] = additional

        row = {
            "request_id": request_id or f"req-{key}-{len(rows) + 1}",
            "call_type": "acompletion",
            # The store's convention, not the credential: the real proxy keys
            # spend rows by the token's sha256 and a row never carries the raw
            # key (probed live 2026-08-05).
            "api_key": hashlib.sha256(key.encode()).hexdigest(),
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "spend": spend,
            "metadata": metadata,
        }
        rows.append(row)

        record = self.keys.get(key)
        if record is not None:
            record["spend"] = round(record["spend"] + spend, 10)
        return row

    def set_spend(self, key: str, spend: float) -> None:
        """Force the `/key/info` spend, independent of any recorded rows."""
        self.keys[key]["spend"] = spend

    def fail_next(self, path: str, *, status: int = 500, times: int = 1) -> None:
        """Queue `times` failures for `path`, consumed one per request."""
        queue = self._failures.setdefault(path, [])
        queue.extend([(status, f"injected {status} for {path}")] * times)

    def make_unreachable(self) -> None:
        """Drop every request, as if the address were dead (US2 FR-005)."""
        self._refuse_requests = True

    def key_for_alias(self, alias: str) -> str | None:
        for key, key_alias in self.aliases.items():
            if key_alias == alias:
                return key
        return None

    def rows_for(self, key: str) -> list[dict[str, Any]]:
        return list(self.spend_rows.get(key, []))

    @property
    def routes(self) -> list[str]:
        """`["POST /key/generate", "GET /key/info", …]` in arrival order (R3)."""
        return [call.route for call in self.calls]

    def calls_to(self, path: str) -> list[RecordedCall]:
        return [call for call in self.calls if call.path == path]

    # --- request handling ---------------------------------------------------

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if self._refuse_requests:
            # The connection-refused shape: an httpx.HTTPError the client maps
            # to a credential-free error with status None (FR-005).
            raise httpx.ConnectError("connection refused", request=request)

        body = self._json_body(request)
        path = request.url.path
        self.calls.append(
            RecordedCall(
                method=request.method,
                path=path,
                params=dict(request.url.params),
                body=body,
            )
        )

        if request.headers.get("Authorization") != f"Bearer {self.master_key}":
            # Never echo the offered credential (FR-009).
            return self._error(401, "Authentication Error: invalid admin credential")

        injected = self._pop_failure(path)
        if injected is not None:
            return injected

        route = (request.method, path)
        if route == ("POST", "/key/generate"):
            return self._key_generate(body)
        if route == ("GET", "/key/info"):
            return self._key_info(dict(request.url.params))
        if route == ("POST", "/key/delete"):
            return self._key_delete(body)
        if route == ("GET", "/spend/logs/v2"):
            return self._spend_logs(dict(request.url.params))
        if route == ("GET", "/v1/models"):
            return self._models()
        if route == ("GET", "/key/list"):
            return self._key_list(dict(request.url.params))
        return self._error(404, f"unknown route {request.method} {path}")

    def _models(self) -> httpx.Response:
        """`GET /v1/models`: the aliases the proxy says it can route (FR-004)."""
        return httpx.Response(
            200,
            json={
                "data": [{"id": alias} for alias in sorted(self.served_models)]
            },
        )

    def _key_list(self, params: dict[str, Any]) -> httpx.Response:
        """`GET /key/list`: every *live* key's alias (US2 FR-006 preflight).

        Live only: a deleted key is gone from `/key/list` the way it is on the
        real proxy, so an orphaned alias that would collide with an epic's first
        attempt is exactly one that is still live (a dead worker that never ran
        teardown) — never a key that already tore down.

        Shape hardened to the live proxy 2026-08-07: entries ride a `keys`
        array with pagination metadata, and they are full objects only when
        `return_full_object=true` — without it the proxy answers bare token
        hashes, which is exactly the response that hid the first preflight's
        parse bug. The fake enforces that contract behaviorally.
        """
        entries: list[Any]
        if str(params.get("return_full_object", "")).lower() == "true":
            # The fake returns `hash-<raw_key>` as the token, matching the
            # spend-log convention so tests can assert deletion by token. Real
            # LiteLLM returns the sha256 hex; both are accepted by the proxy.
            entries = [
                {"key_alias": self.aliases[key], "token": f"hash-{key}"}
                for key in self.keys
            ]
        else:
            entries = [f"hash-{key}" for key in self.keys]
        size = max(1, int(params.get("size", 100)))
        page = max(1, int(params.get("page", 1)))
        total_pages = max(1, -(-len(entries) // size))
        start = (page - 1) * size
        return httpx.Response(
            200,
            json={
                "keys": entries[start : start + size],
                "total_count": len(entries),
                "current_page": page,
                "total_pages": total_pages,
            },
        )

    def _key_generate(self, body: dict[str, Any] | None) -> httpx.Response:
        body = body or {}
        caps = [field for field in ("max_budget", "soft_budget") if field in body]
        if caps:
            return self._error(
                400,
                f"budget caps are deferred to spec 004 (D-021); unexpected: {caps}",
            )

        alias = body.get("key_alias")
        if not alias:
            return self._error(400, "key_alias is required — spend must be attributable")
        if self.enforce_alias_uniqueness and self.key_for_alias(alias) is not None:
            return self._error(400, f"key_alias {alias!r} already exists")

        self._issued += 1
        key = f"sk-fake-{self._issued}"
        self.keys[key] = {
            "key": key,
            "key_alias": alias,
            "models": list(body.get("models") or []),
            "metadata": dict(body.get("metadata") or {}),
            "duration": body.get("duration"),
            "spend": 0.0,
            "max_budget": None,
        }
        self.aliases[key] = alias
        self.spend_rows.setdefault(key, [])

        return httpx.Response(
            200,
            json={
                "key": key,
                "key_alias": alias,
                "models": self.keys[key]["models"],
                "metadata": self.keys[key]["metadata"],
                "duration": self.keys[key]["duration"],
                "max_budget": None,
                "spend": 0.0,
                "expires": None,
            },
        )

    def _key_info(self, params: dict[str, str]) -> httpx.Response:
        key = params.get("key")
        if not key:
            return self._error(400, "key query parameter is required")
        # Accept either the raw key or the fake's hashed-token form.
        record = self.keys.get(key)
        if record is None and key.startswith("hash-"):
            record = self.keys.get(key[len("hash-"):])
        if record is None:
            return self._error(404, "key not found")

        return httpx.Response(
            200,
            json={
                "key": key,
                "info": {
                    "key_alias": record["key_alias"],
                    "spend": record["spend"],
                    "models": record["models"],
                    "metadata": record["metadata"],
                    "max_budget": None,
                    "expires": None,
                },
            },
        )

    def _key_delete(self, body: dict[str, Any] | None) -> httpx.Response:
        body = body or {}
        keys = body.get("keys")
        if not isinstance(keys, list) or not keys:
            return self._error(400, "keys must be a non-empty list")

        keys_to_delete: list[str] = []
        for token_or_key in keys:
            # Accept either the raw key (used by teardown) or the hashed token
            # returned by /key/list (used by US3 recovery).
            raw = token_or_key
            if raw.startswith("hash-"):
                raw = raw[len("hash-"):]
            if raw in self.keys:
                keys_to_delete.append(raw)

        if not keys_to_delete:
            return self._error(404, "no matching keys found")

        for key in keys_to_delete:
            # Spend rows survive deletion (R3); the alias mapping does too, so
            # tests can still resolve spend rows by alias after the key is gone.
            # A new key with the same alias may be issued, so this entry is
            # removed to keep the alias-to-key lookup truthful.
            self.aliases.pop(key, None)
            del self.keys[key]
        return httpx.Response(200, json={"deleted_keys": list(keys_to_delete)})

    def _spend_logs(self, params: dict[str, str]) -> httpx.Response:
        # The real proxy REQUIRES the window (probed live 2026-08-05,
        # `main-stable`): absent dates are an error, not "all time", and the
        # accepted formats are exactly these two. The fake does not filter by
        # the window — its rows carry no timestamps and `api_key` is the true
        # selector — but a client that stopped sending the dates would fail
        # here the way it fails in production.
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        if not start_date or not end_date:
            return self._error(400, "Start date and end date are required")
        for value in (start_date, end_date):
            if not _SPEND_LOG_DATE.fullmatch(value):
                return self._error(
                    400,
                    f"Invalid date format: {value}. Expected: 'YYYY-MM-DD' "
                    "or 'YYYY-MM-DD HH:MM:SS'",
                )

        api_key = params.get("api_key")
        alias = params.get("key_alias")
        if not api_key and not alias:
            return self._error(400, "api_key or key_alias filter is required")

        if api_key:
            # Hash-only matching, like the real proxy: a raw `sk-` filter
            # resolves no rows, so a client that forgot to hash reads an empty
            # log here exactly as it would in production.
            match = next(
                (
                    key
                    for key in self.spend_rows
                    if hashlib.sha256(key.encode()).hexdigest() == api_key
                ),
                None,
            )
            rows = list(self.spend_rows.get(match, [])) if match else []
        else:
            key = self.key_for_alias(alias or "")
            rows = list(self.spend_rows.get(key, [])) if key else []

        try:
            page = int(params.get("page", 1))
            page_size = int(params.get("page_size", DEFAULT_PAGE_SIZE))
        except ValueError:
            return self._error(400, "page and page_size must be integers")
        if page < 1 or page_size < 1:
            return self._error(400, "page and page_size must be >= 1")
        if page_size > 100:
            # The real proxy 422s above 100 (probed live 2026-08-05); a fake
            # that honored a bigger page would let a caller drift past it.
            return self._error(422, "Input should be less than or equal to 100")
        if self.max_page_size is not None:
            page_size = min(page_size, self.max_page_size)

        total = len(rows)
        total_pages = max(1, math.ceil(total / page_size))
        start = (page - 1) * page_size

        return httpx.Response(
            200,
            json={
                "data": rows[start : start + page_size],
                "total_records": total,
                "current_page": page,
                "total_pages": total_pages,
            },
        )

    # --- plumbing -----------------------------------------------------------

    def _pop_failure(self, path: str) -> httpx.Response | None:
        queue = self._failures.get(path)
        if not queue:
            return None
        status, message = queue.pop(0)
        return self._error(status, message)

    @staticmethod
    def _json_body(request: httpx.Request) -> dict[str, Any] | None:
        if not request.content:
            return None
        try:
            body = json.loads(request.content)
        except json.JSONDecodeError:
            return None
        return body if isinstance(body, dict) else None

    @staticmethod
    def _error(status: int, message: str) -> httpx.Response:
        return httpx.Response(
            status,
            json={"error": {"message": message, "code": str(status)}},
        )


# --- suite-wide store isolation ---------------------------------------------


@dataclass(frozen=True)
class TelegramCredentials:
    """Values the session fixture captured from the shell before deleting them.

    Tests that need real credentials must request this fixture explicitly.
    """

    token: str | None
    chat_id: str | None


# Module-level stash populated by `_isolated_test_store` before it deletes the
# env vars.  It is the only place the original values survive.
_telegram_credential_stash: dict[str, str | None] = {"token": None, "chat_id": None}


@pytest.fixture(scope="session", autouse=True)
def _isolated_test_store(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """Redirect all state-locating env variables into pytest's tmp base.

    Runs before any test body so the operator's exports cannot reach a test.
    Overwrites, never ``setdefault`` — the shell must lose.
    """
    # Capture first, delete second: the live smoke reads the stash to opt in.
    _telegram_credential_stash["token"] = os.environ.get(TELEGRAM_BOT_TOKEN_ENV)
    _telegram_credential_stash["chat_id"] = os.environ.get(TELEGRAM_CHAT_ID_ENV)

    base = tmp_path_factory.getbasetemp()
    patch = pytest.MonkeyPatch()

    # Absolute by construction; worktree.py hands this to `git -C ... worktree add`.
    # Both ERGANE_* and FACTORY_* names are set to the SAME path so a partially
    # migrated tree cannot leak, and a per-test override of either name wins
    # cleanly (US3, trap 5).
    root = str(base / "session-factory-root")
    patch.setenv(ERGANE_ROOT_ENV, root)
    patch.setenv(FACTORY_ROOT_ENV, root)
    db = str(base / "session-verification.db")
    patch.setenv(ERGANE_VERIFICATION_DB_PATH_ENV, db)
    patch.setenv(VERIFICATION_DB_PATH_ENV, db)
    ledger = str(base / "session-ledger.db")
    patch.setenv(ERGANE_LEDGER_PATH_ENV, ledger)
    patch.setenv(LEDGER_PATH_ENV, ledger)
    config = str(base / "session-ergane-config.toml")
    patch.setenv(ERGANE_CONFIG_PATH_ENV, config)
    patch.setenv(FACTORY_CONFIG_PATH_ENV, config)
    patch.delenv(TELEGRAM_BOT_TOKEN_ENV, raising=False)
    patch.delenv(TELEGRAM_CHAT_ID_ENV, raising=False)

    try:
        yield
    finally:
        patch.undo()


@pytest.fixture(scope="session")
def telegram_credentials() -> TelegramCredentials:
    """The Telegram credentials the session fixture removed from env.

    Request this explicitly to consume real credentials deliberately; tests that
    do not request it see an env with no Telegram credentials.
    """
    return TelegramCredentials(
        token=_telegram_credential_stash.get("token"),
        chat_id=_telegram_credential_stash.get("chat_id"),
    )


# --- fixtures --------------------------------------------------------------


@pytest.fixture
def fake_litellm() -> Iterator[FakeLiteLLM]:
    """A fresh fake proxy; assert against `fake.calls` / `fake.routes`."""
    yield FakeLiteLLM()


@pytest.fixture
def litellm_env(
    fake_litellm: FakeLiteLLM, monkeypatch: pytest.MonkeyPatch
) -> FakeLiteLLM:
    """Point the activities' env credentials at the fake (contracts/activities.md)."""
    monkeypatch.setenv("LITELLM_PROXY_URL", fake_litellm.base_url)
    monkeypatch.setenv("LITELLM_MASTER_KEY", fake_litellm.master_key)
    return fake_litellm


@pytest.fixture
def target_repo(tmp_path: Path) -> Callable[..., Path]:
    """Build a fixture target repo: `target_repo("failing-gate")` → repo path.

    A factory rather than a plain path because several tests need two variants
    side by side, and because the variant name reads better at the call site than
    in the fixture list.
    """

    def build(variant: str = "passing", name: str | None = None) -> Path:
        return build_target_repo(tmp_path / (name or variant), variant=variant)

    return build


@pytest.fixture
def node_worktree(
    target_repo: Callable[..., Path], tmp_path: Path
) -> Callable[..., Path]:
    """Build a repo variant and attach a node worktree to it, returning the worktree.

    This is the topology the factory actually runs against — gates and diffs see a
    worktree, never the repo's own checkout — so it is the default a test should
    reach for.
    """

    def build(variant: str = "passing", branch: str = "node/work") -> Path:
        repo = target_repo(variant)
        return add_worktree(repo, tmp_path / f"{repo.name}-worktree", branch=branch)

    return build
