"""Generate the SC-002 proposal evidence file.

This module is not a test.  It is a small script the committed evidence file
`proposal_output.txt` was produced with, so a reviewer can reproduce the
pasted output.  Run it as:

    uv run python tests/_us2_outputs/proposal_output.py

It drives the same `build_proposal` entry point the tests exercise, over
in-memory enrichment fixtures only — no network.
"""

from __future__ import annotations

from pathlib import Path

from factory.config import load_personas
from factory.discovery.llm_enrichment import EnrichmentRecord
from factory.discovery.proposal import build_proposal


def main() -> None:
    example_path = Path(__file__).resolve().parents[2] / "personas.example.yaml"
    personas = load_personas(example_path)

    out: list[str] = []

    # Rich gateway: full proposal with reasons.
    rich_records = (
        EnrichmentRecord(
            alias="claude-sonnet-4",
            tool_calling=True,
            structured_output=True,
            reasoning=False,
            context_window=200000,
            input_cost_per_token=3.0e-6,
            output_cost_per_token=1.5e-5,
            detail="rich",
        ),
        EnrichmentRecord(
            alias="claude-opus-4",
            tool_calling=True,
            structured_output=True,
            reasoning=True,
            context_window=200000,
            input_cost_per_token=1.5e-5,
            output_cost_per_token=7.5e-5,
            detail="rich",
        ),
        EnrichmentRecord(
            alias="cheap-tool-caller",
            tool_calling=True,
            structured_output=False,
            reasoning=False,
            context_window=8000,
            input_cost_per_token=1.0e-7,
            output_cost_per_token=1.0e-7,
            detail="rich",
        ),
    )
    rich = build_proposal(personas=personas, records=rich_records)
    out.append("## Rich gateway proposal")
    for name in sorted(rich):
        out.append(f"{name}: {rich[name]}")

    # Refusal: judge requires structured output, but no candidate has it.
    refusal_records = (
        EnrichmentRecord(
            alias="llama3.1",
            tool_calling=True,
            structured_output=False,
            reasoning=False,
            context_window=131072,
            detail="ollama",
        ),
        EnrichmentRecord(
            alias="qwq",
            tool_calling=False,
            structured_output=False,
            reasoning=True,
            context_window=32768,
            detail="ollama",
        ),
    )
    refusal = build_proposal(personas=personas, records=refusal_records)
    out.append("\n## Refusal: no qualifying judge candidate")
    for name in sorted(refusal):
        out.append(f"{name}: {refusal[name]}")

    dest = Path(__file__).with_suffix(".txt")
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
