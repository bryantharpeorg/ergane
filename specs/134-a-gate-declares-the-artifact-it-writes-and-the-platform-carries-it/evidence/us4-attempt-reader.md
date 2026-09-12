# US4: attempt-scoped reader output

The calls below were made over a read-only connection for the same node.
Attempt 1 returned only its first artifact; attempt 2 returned only its second.

```text
attempt=1
[
  {
    "gate": "test",
    "path": "first.xml",
    "type": "coverage",
    "present": true,
    "stored_path": "/tmp/coverage.xml",
    "dispatch": "workflow-run-1",
    "capture_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "digest": null
  }
]
attempt=2
[
  {
    "gate": "test",
    "path": "second.xml",
    "type": "coverage",
    "present": true,
    "stored_path": "/tmp/coverage.xml",
    "dispatch": "workflow-run-1",
    "capture_id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "digest": null
  }
]
```
