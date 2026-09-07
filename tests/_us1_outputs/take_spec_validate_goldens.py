"""Take the six golden captures for 133-US1 (T010).

Run once, with the tree at the pre-relocation state (only US1's finding-type
move landed), and commit the output. Every later story re-runs the comparison
in `tests/test_133_us1_typed_report_and_golden_captures.py`; the artifacts are
re-taken only when a fixture trio changes, in the same commit as the trio.

    uv run python tests/_us1_outputs/take_spec_validate_goldens.py
"""

from __future__ import annotations

import io
import contextlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "spec_validate"
GOLDEN = REPO_ROOT / "tests" / "golden" / "spec_validate"

TRIOS = (
    (FIXTURES / "clean-specs" / "001-clean-trio", "clean"),
    (FIXTURES / "defective-specs" / "002-defective-trio", "defective"),
)


def run(spec_dir: Path, *, as_json: bool) -> tuple[int, str, str]:
    from factory.cli.main import main

    argv = ["spec", "validate", str(spec_dir), "--target-repo", str(FIXTURES / "target-repo")]
    if as_json:
        argv.append("--json")
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def normalise(text: str) -> str:
    return text.replace(str(REPO_ROOT), "<REPO_ROOT>")


def main() -> None:
    for spec_dir, name in TRIOS:
        out = GOLDEN / name
        out.mkdir(parents=True, exist_ok=True)
        code, stdout, stderr = run(spec_dir, as_json=False)
        (out / "stdout.txt").write_text(normalise(stdout), encoding="utf-8")
        (out / "stderr.txt").write_text(normalise(stderr), encoding="utf-8")
        _code, json_stdout, json_stderr = run(spec_dir, as_json=True)
        assert json_stderr == "", "the --json face prints nothing on stderr"
        (out / "json.txt").write_text(normalise(json_stdout), encoding="utf-8")
        print(f"{name}: exit={code}, artifacts written to {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()