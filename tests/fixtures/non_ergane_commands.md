# Fixture page with legitimate non-Ergane commands

The near-miss detector must stay bounded: it compares the first word of each
code span against the known Ergane entrypoints, and a word that is nothing like
any of them is somebody else's tool, not a typo.

```bash
git clone https://github.com/bryantharpeorg/ergane.git
cd ergane
uv venv
uv pip install -e .
gh auth login
systemctl --user daemon-reload
```

Evaluated environment snippets are also not commands:

```bash
eval "$(scripts/ergane-env.sh)"
```
