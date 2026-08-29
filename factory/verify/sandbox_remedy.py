"""Single source of sandbox-refusal remedy text.

The demo driver's sandbox refusal and the host probe's bwrap finding both read
from this module, so the two tiers cannot drift into two different pieces of
advice. The function is pure: it takes the probe's stderr and returns the
remedy that matches the failure it recognises.
"""

from __future__ import annotations

import re

#: Profile this repository ships for the host's AppArmor policy.
BWRAP_APPARMOR_PROFILE_PATH = "container/ergane-bwrap.apparmor"

_UID_MAP_RE = re.compile(r"setting up uid map: Permission denied")
_MOUNT_PROC_RE = re.compile(r"Can't mount proc")


_APPARMOR_REMEDY = (
    "remedy: AppArmor's unprivileged-userns restriction refused the sandbox "
    "(`kernel.apparmor_restrict_unprivileged_userns=1`). The `apparmor=unconfined` "
    "option on the container does not lift it, because AppArmor attaches by "
    "executable path on exec. Load the profile this repository ships, once, with "
    f"`sudo apparmor_parser -r {BWRAP_APPARMOR_PROFILE_PATH}`."
)

_MASKED_PROC_REMEDY = (
    "remedy: Docker's masked `/proc` paths refused the fresh procfs mount the "
    "sandbox needs (bubblewrap#284). Add "
    "`security_opt: [systempaths=unconfined]` to the engine service — it is "
    "already set in container/compose.demo.yaml."
)


def sandbox_remedy(stderr: str) -> str:
    """Return the remedy that matches a sandbox probe's stderr.

    Two failures are recognised:
    - ``setting up uid map: Permission denied`` — AppArmor's
      ``kernel.apparmor_restrict_unprivileged_userns`` restriction.
    - ``Can't mount proc`` — Docker's masked ``/proc`` paths.

    Anything else returns the probe's own stderr verbatim plus a line that admits
    the failure is unrecognised and names both known remedies as candidates.
    """
    if _UID_MAP_RE.search(stderr):
        return _APPARMOR_REMEDY
    if _MOUNT_PROC_RE.search(stderr):
        return _MASKED_PROC_REMEDY

    return (
        f"{stderr}\n"
        "The failure above is not one of the two known shapes. "
        "Known remedies are: load the AppArmor profile for bwrap at "
        f"`{BWRAP_APPARMOR_PROFILE_PATH}` (which allows unprivileged user namespaces "
        "despite `kernel.apparmor_restrict_unprivileged_userns=1`), or set "
        "`security_opt: [systempaths=unconfined]` on the engine service."
    )
