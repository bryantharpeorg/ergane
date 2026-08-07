"""The preflight reads (US2 FR-004/005/006), pinned against the fake proxy.

The factory starts an epic only after it has confirmed two facts the graph
cannot carry: that the proxy serves every model alias the resolved registry
names, and that the credentials the first attempts need are still free. Both
are read-only admin calls, and this is the only module that knows their
shapes, so the contract is pinned here, once:

- **A model list is complete and a key list is aliases only.** The served set
  is the whole `data` array (a client that stops at page one would let an
  unserved alias slip through); the key list returns aliases, never tokens —
  FR-009 holds on this path too, and no key value may cross the boundary.
- **A non-200 and a dead transport are distinct, named failures.** The first is
  "the proxy answered and said no" (FR-005's service-not-answering is *not*
  this); the second is "nothing is listening", and carries the address tried.
  A caller that cannot tell them apart would report a reachable-but-erroring
  proxy as unreachable, or vice versa — the exact ambiguity FR-005 exists to
  remove.
- **No alias leaks into a message.** Only the alias list is returned; the error
  paths name the endpoint and the status, never a model or key value.

Written before the two read-only calls exist on `LiteLLMClient` (T014 precedes
T015): until they land, every test here fails at attribute/import time.
"""

from __future__ import annotations

import httpx
import pytest

from factory.usage.litellm_client import LiteLLMClient, LiteLLMError
from tests.conftest import FakeLiteLLM

#: The standard attempt's first key alias — what US2's key-collision check must
#: predict from the graph alone (FR-006).
ALIAS = "epic-7:node-3:1:implementer"


async def _client(fake_litellm: FakeLiteLLM) -> LiteLLMClient:
    return LiteLLMClient(
        base_url=fake_litellm.base_url,
        master_key=fake_litellm.master_key,
        transport=fake_litellm.transport,
    )


async def test_list_model_ids_returns_every_alias_the_proxy_serves(
    fake_litellm: FakeLiteLLM,
) -> None:
    fake_litellm.served_models = {
        "anthropic/claude-opus-5",
        "local/qwen3.6-27b",
        "ollama-cloud/deepseek-v4-flash",
    }
    async with await _client(fake_litellm) as client:
        served = await client.list_model_ids()

    assert served == {
        "anthropic/claude-opus-5",
        "local/qwen3.6-27b",
        "ollama-cloud/deepseek-v4-flash",
    }
    (call,) = fake_litellm.calls_to("/v1/models")
    assert call.method == "GET"


async def test_list_key_aliases_returns_every_live_key_alias(
    fake_litellm: FakeLiteLLM,
) -> None:
    async with await _client(fake_litellm) as client:
        await client.issue_key(
            key_alias="epic-7:node-3:1:implementer", models=["anthropic/CHANGEME"]
        )
        await client.issue_key(
            key_alias="epic-7:node-9:1:debugger", models=["anthropic/CHANGEME"]
        )

        aliases = await client.list_key_aliases()

    assert aliases == {
        "epic-7:node-3:1:implementer",
        "epic-7:node-9:1:debugger",
    }
    (call,) = fake_litellm.calls_to("/key/list")
    assert call.method == "GET"
    # No credential leaves the client: the key list answers in aliases only
    # (FR-009), and never exposes a raw key.
    assert "key" not in str(call.body) and "sk-" not in str(aliases)


async def test_a_non_200_model_read_is_a_named_failure(
    fake_litellm: FakeLiteLLM,
) -> None:
    fake_litellm.fail_next("/v1/models", status=500)
    async with await _client(fake_litellm) as client:
        with pytest.raises(LiteLLMError) as excinfo:
            await client.list_model_ids()

    # The proxy answered; this is a *reachable* proxy with a problem, which is
    # distinct from the connection-refused case FR-005 must tell apart.
    assert excinfo.value.status == 500


async def test_a_non_200_key_read_is_a_named_failure(
    fake_litellm: FakeLiteLLM,
) -> None:
    fake_litellm.fail_next("/key/list", status=503)
    async with await _client(fake_litellm) as client:
        with pytest.raises(LiteLLMError) as excinfo:
            await client.list_key_aliases()

    assert excinfo.value.status == 503


async def test_a_dead_transport_is_a_distinct_status_none_failure(
    fake_litellm: FakeLiteLLM,
) -> None:
    # The connection-refused shape: an httpx.HTTPError, so `status` is None —
    # the "nothing is listening" reading FR-005 distinguishes from "not served".
    fake_litellm._refuse_requests = True
    async with await _client(fake_litellm) as client:
        with pytest.raises(LiteLLMError) as excinfo:
            await client.list_model_ids()

    assert excinfo.value.status is None


async def test_the_master_key_never_reaches_a_preflight_error(
    fake_litellm: FakeLiteLLM,
) -> None:
    # A wrong master key is a 401 that must not echo the offered credential
    # anywhere in the raised chain (FR-009, SC-004).
    async with LiteLLMClient(
        base_url=fake_litellm.base_url,
        master_key="sk-wrong-master",
        transport=fake_litellm.transport,
    ) as client:
        with pytest.raises(LiteLLMError) as excinfo:
            await client.list_model_ids()

    error: BaseException | None = excinfo.value
    while error is not None:
        rendering = f"{str(error)} {str(error.args)}"
        assert "sk-wrong-master" not in rendering
        error = error.__cause__ or error.__context__
