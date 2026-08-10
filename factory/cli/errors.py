"""One shared error boundary for every `ergane` handler.

The dispatcher owns the contract, not the individual nouns. Every handler
raises one of three things:

- `OperatorError` — an operator-fixable problem; rendered as one line on
  stderr with the code the exception carries (default 1).
- `ServiceError` — a service the factory talks to did not answer; rendered as
  one line naming the address that was dialled, with exit 3.
- anything else — a bug; rendered as one line telling the operator to use
  `--debug`, with exit 1. With `--debug` the traceback is printed.

`KeyboardInterrupt` exits 130 with nothing on stderr. Only requested output ever
reaches stdout.
"""

from __future__ import annotations

import sys
import traceback
from typing import Sequence, Callable

EXIT_OK = 0
EXIT_USER = 1
EXIT_USAGE = 2
EXIT_TRANSPORT = 3
EXIT_INTERRUPT = 130


class OperatorError(Exception):
    """Something the operator can fix without leaving the terminal.

    Carries its own exit code so that a transport failure (code 3) and a
    broken spec (code 1) can share one handler and differ only in the number
    they return.
    """

    def __init__(self, message: str, code: int = EXIT_USER) -> None:
        super().__init__(message)
        self.code = code


class ServiceError(Exception):
    """A service the factory talks to did not answer."""

    def __init__(self, service: str, address: str) -> None:
        self.service = service
        self.address = address
        super().__init__(f"cannot reach {service} at {address}")


def run_cli(entry: Callable[[], int], *, debug: bool = False) -> int:
    """Run one handler and render the result to the contract.

    This is the single place the exit-code table is implemented. A noun added
    later inherits the contract because its handler is wrapped here, not because
    it remembered to print before returning.
    """
    try:
        return entry()
    except OperatorError as error:
        print(f"ergane: {error}", file=sys.stderr)
        return error.code
    except ServiceError as error:
        print(f"ergane: {error}", file=sys.stderr)
        return EXIT_TRANSPORT
    except KeyboardInterrupt:
        return EXIT_INTERRUPT
    except Exception as error:  # pragma: no cover - defensive boundary
        if debug:
            traceback.print_exc(file=sys.stderr)
        else:
            print(
                f"ergane: unexpected error ({error}); re-run with --debug for the traceback",
                file=sys.stderr,
            )
        return EXIT_USER
