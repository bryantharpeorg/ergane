"""Environment variable name resolution for the factory's state paths (US3).

Every operator-facing path variable gained an `ERGANE_*` alias while the old
`FACTORY_*` name remains honored.  Resolvers live here so every module reads the
same names and emits one deprecation per command, not one per read (trap 7).
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

#: Modern names an operator should export (US3).
ERGANE_ROOT_ENV = "ERGANE_ROOT"
ERGANE_VERIFICATION_DB_PATH_ENV = "ERGANE_VERIFICATION_DB_PATH"
ERGANE_LEDGER_PATH_ENV = "ERGANE_LEDGER_PATH"
ERGANE_EVIDENCE_STORE_ALLOW_REAL_ENV = "ERGANE_EVIDENCE_STORE_ALLOW_REAL"

#: 033: the control-plane config file may be relocated by the operator.
ERGANE_CONFIG_PATH_ENV = "ERGANE_CONFIG_PATH"

#: Legacy names still honored during the rename.
FACTORY_ROOT_ENV = "FACTORY_ROOT"
FACTORY_VERIFICATION_DB_PATH_ENV = "FACTORY_VERIFICATION_DB_PATH"
FACTORY_LEDGER_PATH_ENV = "FACTORY_LEDGER_PATH"
FACTORY_EVIDENCE_STORE_ALLOW_REAL_ENV = "FACTORY_EVIDENCE_STORE_ALLOW_REAL"

#: 033 legacy alias for the control-plane config path.
FACTORY_CONFIG_PATH_ENV = "FACTORY_CONFIG_PATH"

#: Keys already warned about this process.  One deprecation per variable pair.
_WARNED: set[tuple[str, str]] = set()


def resolve_env_path(
    new_name: str,
    old_name: str,
    default: str | Path,
    *,
    _seen: set[tuple[str, str]] | None = None,
) -> Path:
    """Return the path for a variable with a modern and a legacy name.

    - `ERGANE_*` wins when both are set.
    - A conflict is reported once, naming both variables and both values.
    - Only the legacy name set is honored with a single deprecation warning
      that names the old and new variable.
    - Neither set falls back to `default`.

    The warning is gated by a process-level set so resolvers called many times
    per epic (e.g. `_store_path`) do not flood the operator (trap 7).
    """
    seen = _seen if _seen is not None else _WARNED
    key = (new_name, old_name)

    new_value = os.environ.get(new_name)
    old_value = os.environ.get(old_name)

    if new_value is not None:
        if old_value is not None and old_value != new_value:
            _warn_once(
                seen,
                key,
                f"{new_name} and {old_name} are both set; "
                f"{new_name} wins ({new_value!r} vs {old_value!r})",
            )
        return Path(new_value)

    if old_value is not None:
        _warn_once(
            seen,
            key,
            f"{old_name} is deprecated; use {new_name} instead "
            f"(current value: {old_value!r})",
        )
        return Path(old_value)

    return Path(default)


def _warn_once(
    seen: set[tuple[str, str]], key: tuple[str, str], message: str
) -> None:
    """Emit a deprecation warning for `key` at most once per Python process."""
    if key in seen:
        return
    seen.add(key)
    warnings.warn(message, DeprecationWarning, stacklevel=3)


def resolve_env_flag(new_name: str, old_name: str) -> bool:
    """Return True when either the modern or legacy flag variable is set.

    The modern name wins if both are present; the legacy name is honored with
    the same one-per-process deprecation warning.
    """
    new_value = os.environ.get(new_name)
    old_value = os.environ.get(old_name)

    if new_value is not None:
        if old_value is not None and old_value != new_value:
            _warn_once(
                _WARNED,
                (new_name, old_name),
                f"{new_name} and {old_name} are both set; "
                f"{new_name} wins ({new_value!r} vs {old_value!r})",
            )
        return bool(new_value)

    if old_value is not None:
        _warn_once(
            _WARNED,
            (new_name, old_name),
            f"{old_name} is deprecated; use {new_name} instead "
            f"(current value: {old_value!r})",
        )
        return bool(old_value)

    return False
