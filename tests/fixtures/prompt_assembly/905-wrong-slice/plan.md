# Plan: Peer channel (reconstructed)

One addressee grammar, one mailbox, one expiry beat. The registry is operator
owned; the transport is a file per message; cross-epic delivery rides an
external workflow signal.

This file exists because prompt assembly reads the whole trio, and a fixture
missing one would exercise the missing-file path by accident rather than the
wrong-slice path on purpose.
