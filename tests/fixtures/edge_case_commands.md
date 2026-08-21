# Fixture page for edge cases

A shell pipeline's first word is a legitimate non-Ergane command:

```bash
cat file | grep thing
```

A correctly-spelled but nonexistent Ergane command must not be caught by the
near-miss detector; it should fail later, through `--help`:

```bash
ergane nonexistent
```
