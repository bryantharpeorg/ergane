# US4 T028 — SC-004: the unversioned unit leaves the host

Run 2026-08-22: the real `install` and `migrate_off_legacy_unit` over a real
unit directory and manifest under a temp root, with the systemd command seam
recording rather than executing. The host was seeded as a pre-082 install —
`ergane-worker.service` in `layout.unit_dir`, its digest recorded by
`_write_manifest(layout, {LEGACY_WORKER_UNIT: _digest(text)})` — plus two
`layout.deployment_tree(...)` checkouts, as deploy leaves them. Decisive lines
only (D-050).

**The half this cannot contain.** SC-004 also names `systemctl --user
list-units 'ergane-worker*'`. No node of this factory can run it — a node
worktree has no systemd user session:

```
$ systemctl --user list-units 'ergane-worker*' --all
Failed to connect to bus: No medium found
$ ls -d /run/user
ls: cannot access '/run/user': No such file or directory
```

and the session that does have one is the host's, where `disable --now
ergane-worker.service` would stop the worker running this attempt. So the
unit-directory half is measured here and the `list-units` half is the
operator's, after this lands; the commands the engine issues are pasted
verbatim so the two can be checked against each other.

## A pre-082 host, installed and then migrated

```
$ ergane worker install
wrote 6 file(s) to the unit directory
  active+enabled: ergane-bridge.service
  active+enabled: ergane-probe.timer
  the worker is versioned: `ergane worker deploy` puts one on the floor
  retired, still installed: ergane-worker.service — `ergane worker migrate` removes it
```

Install writes the template and never the legacy unit (US4-S1/FR-006), and
names the legacy file it did not write rather than leaving it to be found.

```
versioned instances on the floor: ('ergane-worker@9f8e7d6.service', 'ergane-worker@a1b2c3d.service')

$ ergane worker migrate   # epic-053-skew open, started pre-versioning
refusing to remove ergane-worker.service while epic-053-skew predates
versioning: it carries no deployment version, so stopping that unit takes the
agents it is running down with its cgroup, and whatever survives is adopted onto
whichever version is current at its next workflow task — an epic finishing on
code it did not start with. Let it land, or kill it, then run this again
still installed: True
```

FR-007, refused by name, nothing touched. `epic-082-current`, pinned to a
deployed version, is open throughout and is not named: retiring the unversioned
unit cannot strand it.

```
$ ergane worker migrate   # only pinned epics remain open
retired the unversioned worker unit:
  ergane-worker.service: stopped, disabled, removed

commands issued:
  systemctl --user disable --now ergane-worker.service
  systemctl --user daemon-reload
```

The disable precedes the deletion: systemd holds the parsed unit in memory, and
a file removed out from under a running one leaves it up and invisible to
`disable` until the next boot.

## SC-004: the unit directory, before and after

```
before:                            after:
  ergane-bridge.service              ergane-bridge.service
  ergane-probe.service               ergane-probe.service
  ergane-probe.timer                 ergane-probe.timer
  ergane-worker.service              ergane-worker@.service
  ergane-worker@.service             ergane.slice
  ergane.slice
```

The legacy file is gone; everything else install wrote is untouched — this verb
retires one unit, it does not tear the floor down. On the host, `list-units
'ergane-worker*'` then has only the two instances above to list: an instance is
the only thing systemd can enable from a template, and the legacy unit is by
then neither loaded nor on disk.
