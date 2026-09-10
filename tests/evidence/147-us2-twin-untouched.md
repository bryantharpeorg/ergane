# T020: the pre-`ergane` twin was not edited

The story's implementation range is `333350b` through `6685ab0`.

```text
$ git diff --name-only 333350b..6685ab0 -- factory/workgraph/cli.py
```

The command produced no output. The imports and test references shown above read
other names from `factory/workgraph/cli.py`; neither `_live_spend` nor its local
`render_status` is imported or called by `factory/` or `tests/`.
