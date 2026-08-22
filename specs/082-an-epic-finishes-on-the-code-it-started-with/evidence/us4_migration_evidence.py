"""082-US4 T028/SC-004: the migration, run end to end against a real host tree.

Real files, real manifest, the real `install`, `uninstall` and
`migrate_off_legacy_unit` — under a temp root, with the systemd command seam
recording rather than executing. That seam is not a convenience here: a node of
this factory has no systemd user session at all (`/run/user` does not exist in
the worktree, `systemctl --user` answers "Failed to connect to bus"), and the
session on the *host* is the one running this attempt, so `disable --now
ergane-worker.service` there would stop the worker mid-story.

What that leaves for SC-004: the unit-directory half is measured here, live;
the `systemctl --user list-units` half is the operator's to run on the host
after this lands. The commands the engine issues are pasted verbatim so the two
halves can be checked against each other.

    $ uv run python specs/082-an-epic-finishes-on-the-code-it-started-with/evidence/us4_migration_evidence.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Sequence

from factory.cli.errors import OperatorError
from factory.supervision.units import (
    LEGACY_WORKER_UNIT,
    CommandResult,
    InstallLayout,
    _digest,
    _read_manifest,
    _write_manifest,
    deployed_instances,
    install,
    migrate_off_legacy_unit,
)
from factory.versioning import OpenEpic

#: What the pre-082 engine wrote to `ergane-worker.service` on this host, and
#: the digest that install recorded to prove it was the engine's.
LEGACY_TEXT = """\
[Unit]
Description=ergane — factory worker (workgraph task queue)

[Service]
ExecStart=/tmp/ergane-run.sh factory.worker
"""

DEPLOYED = ("9f8e7d6", "a1b2c3d")


class Recorder:
    """Every systemd command the engine would have run, in order."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, argv: Sequence[str]) -> CommandResult:
        self.calls.append(" ".join(argv))
        return CommandResult(0)


def units_in(layout: InstallLayout) -> str:
    return "\n".join(f"  {path.name}" for path in sorted(layout.unit_dir.iterdir()))


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        home = Path(temporary)
        interpreter = home / "code/ergane/.venv/bin/python3"
        interpreter.parent.mkdir(parents=True)
        interpreter.touch()
        layout = InstallLayout(
            install_root=home / "code/ergane",
            interpreter=interpreter,
            unit_dir=home / ".config/systemd/user",
            generated_dir=home / ".local/state/ergane/supervision",
        )

        # The host as it is the day this lands: a pre-082 install, its worker
        # unit on disk, its digest in the manifest.
        layout.unit_dir.mkdir(parents=True)
        layout.generated_dir.mkdir(parents=True)
        (layout.unit_dir / LEGACY_WORKER_UNIT).write_text(LEGACY_TEXT, encoding="utf-8")
        _write_manifest(layout, {LEGACY_WORKER_UNIT: _digest(LEGACY_TEXT)})

        print("--- `ergane worker install` on that host ---")
        print(install(layout, run=Recorder()).render())
        print("\nunit directory after install:")
        print(units_in(layout))

        # Two versions deployed beside it, as `ergane worker deploy` leaves them.
        for build_id in DEPLOYED:
            layout.deployment_tree(build_id).mkdir(parents=True)
        print(f"\nversioned instances on the floor: {deployed_instances(layout)}")

        print("\n--- `ergane worker migrate` with a pre-versioning epic open ---")
        try:
            migrate_off_legacy_unit(
                layout,
                run=Recorder(),
                open_epics=lambda: (
                    OpenEpic("epic-053-skew"),
                    OpenEpic("epic-082-current", behavior=1, build_id=DEPLOYED[1]),
                ),
            )
        except OperatorError as refusal:
            print(f"$ ergane worker migrate\n{refusal}")
        print(f"\nstill installed: {(layout.unit_dir / LEGACY_WORKER_UNIT).is_file()}")

        print("\n--- `ergane worker migrate` once nothing predates versioning ---")
        issued = Recorder()
        report = migrate_off_legacy_unit(
            layout,
            run=issued,
            open_epics=lambda: (
                OpenEpic("epic-082-current", behavior=1, build_id=DEPLOYED[1]),
            ),
        )
        print(f"$ ergane worker migrate\n{report.render()}")
        print("\ncommands issued:")
        print("\n".join(f"  {call}" for call in issued.calls))
        print("\nunit directory after migration:")
        print(units_in(layout))
        print(f"\nmanifest now records: {sorted(_read_manifest(layout))}")


if __name__ == "__main__":
    main()
