# US1 evidence: what the journal holds, before and after

SC-001 is an observation of a journal, and the judge sees only this diff (plan
trap 10), so the observation is pasted here rather than described. Two runs of
the same send are shown: one with the seams installing nothing — the world
before this story — and one as shipped. The transport is `httpx.MockTransport`,
so no socket opens, but the client, the URL and the `HTTP Request:` line are
the real library's; that line is the leak.

Both halves matter. The credential is gone, **and** the send is still there:
the request occurred (`delivered=True`, `message_id=7`, `getMe` then
`sendMessage`), the host and the operation still read back, and the status is
still `200 OK`. Silencing `httpx` would have satisfied the first half and cost
the second (trap 1).

```
--- before (the seams install nothing) ------------------------
send occurred: delivered=True message_id=7 requests=['getMe', 'sendMessage']
  httpx INFO HTTP Request: POST https://api.telegram.org/bot8100000042:AAFake-do-not-log-me-0000000000000000000/getMe "HTTP/1.1 200 OK"
  httpx INFO HTTP Request: POST https://api.telegram.org/bot8100000042:AAFake-do-not-log-me-0000000000000000000/sendMessage "HTTP/1.1 200 OK"
token present in journal: True

--- after (shipped) -------------------------------------------
send occurred: delivered=True message_id=7 requests=['getMe', 'sendMessage']
  httpx INFO HTTP Request: POST https://api.telegram.org/bot<redacted>/getMe "HTTP/1.1 200 OK"
  httpx INFO HTTP Request: POST https://api.telegram.org/bot<redacted>/sendMessage "HTTP/1.1 200 OK"
token present in journal: False

--- webhook, before -------------------------------------------
send occurred: delivered=True
  httpx INFO HTTP Request: POST https://hooks.example.test/services/T000/B000/FakeHookSecret "HTTP/1.1 200 OK"
secret present in journal: True

--- webhook, after --------------------------------------------
send occurred: delivered=True
  httpx INFO HTTP Request: POST https://hooks.example.test/<redacted> "HTTP/1.1 200 OK"
secret present in journal: False

--- traceback, before -----------------------------------------
Traceback (most recent call last):
  File "/home/admin/code/ergane/.factory/worktrees/064-the-on-ramp-stops-leaking-and-guessing/us1/tests/test_the_token_never_reaches_the_journal.py", line 449, in a_real_status_error
    response.raise_for_status()
  File "/home/admin/code/ergane/.factory/worktrees/064-the-on-ramp-stops-leaking-and-guessing/us1/.venv/lib/python3.12/site-packages/httpx/_models.py", line 829, in raise_for_status
    raise HTTPStatusError(message, request=request, response=self)
httpx.HTTPStatusError: Client error '401 Unauthorized' for url 'https://api.telegram.org/bot8100000042:AAFake-do-not-log-me-0000000000000000000/sendMessage'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
token present: True

--- traceback, after (sys.excepthook) -------------------------
Traceback (most recent call last):
  File "/home/admin/code/ergane/.factory/worktrees/064-the-on-ramp-stops-leaking-and-guessing/us1/tests/test_the_token_never_reaches_the_journal.py", line 449, in a_real_status_error
    response.raise_for_status()
  File "/home/admin/code/ergane/.factory/worktrees/064-the-on-ramp-stops-leaking-and-guessing/us1/.venv/lib/python3.12/site-packages/httpx/_models.py", line 829, in raise_for_status
    raise HTTPStatusError(message, request=request, response=self)
httpx.HTTPStatusError: Client error '401 Unauthorized' for url 'https://api.telegram.org/bot<redacted>/sendMessage'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
```

## The tests can fail

An absence assertion that cannot fail proves nothing (trap 2). With `redact()`
reduced to `return text` — the mechanism removed, everything else untouched —
every one of the nine scenarios fails:

```
$ uv run pytest tests/test_the_token_never_reaches_the_journal.py -q   # with redact() stubbed out
FAILED tests/test_the_token_never_reaches_the_journal.py::test_a_telegram_send_writes_no_token_to_the_journal
FAILED tests/test_the_token_never_reaches_the_journal.py::test_the_request_is_still_observable_in_redacted_form
FAILED tests/test_the_token_never_reaches_the_journal.py::test_both_entry_points_configure_a_redacting_journal[factory.worker]
FAILED tests/test_the_token_never_reaches_the_journal.py::test_both_entry_points_configure_a_redacting_journal[factory.notify.service]
FAILED tests/test_the_token_never_reaches_the_journal.py::test_constructing_an_adapter_is_enough
FAILED tests/test_the_token_never_reaches_the_journal.py::test_constructing_the_webhook_adapter_is_enough
FAILED tests/test_the_token_never_reaches_the_journal.py::test_a_webhook_send_writes_no_url_secret_to_the_journal
FAILED tests/test_the_token_never_reaches_the_journal.py::test_a_traceback_does_not_render_the_token
FAILED tests/test_the_token_never_reaches_the_journal.py::test_install_is_idempotent_and_keeps_a_callers_own_record_factory
9 failed in 0.15s
```

Restored, on the shipped mechanism:

```
$ uv run pytest tests/test_the_token_never_reaches_the_journal.py -q
.........                                                                [100%]
9 passed in 0.10s
```

And the repository's own gate, whole:

```
$ uv run pytest -q
3967 passed, 49 skipped, 7 warnings in 313.59s (0:05:13)
```

## What still needs a human and a real credential

This is a stub transport, so it cannot prove the shipped worker's journal. The
operator check the plan names stays worth running once, after the worker is
restarted on this code: trigger a live escalation, then

```
journalctl --user -u ergane-worker | grep -c "$(printf %s "$TELEGRAM_BOT_TOKEN" | cut -c1-12)"
```

expecting `0`, while confirming from the same journal — `grep "HTTP Request.*sendMessage"` —
that the send actually happened. A zero count with no send is not evidence.
