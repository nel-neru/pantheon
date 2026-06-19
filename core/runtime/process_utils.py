"""Cross-platform process liveness / termination helpers.

The single source of truth for "is this pid alive?" and "terminate this pid".
On POSIX these are the classic ``os.kill(pid, 0)`` / ``os.kill(pid, SIGTERM)``
idioms. On Windows those idioms are **wrong**:

* ``os.kill(pid, 0)`` does NOT behave like a POSIX existence probe — it reports
  a recently-exited (reaped) pid as still alive (false positive), because the
  process object lingers while any handle to it is open. That made daemon
  liveness checks report crashed daemons as "running", so the watchdog never
  resurrected them. We instead query the real exit code via
  ``OpenProcess`` + ``GetExitCodeProcess`` and treat ``STILL_ACTIVE`` as alive.
* ``signal.SIGTERM`` is meaningless to ``os.kill`` on Windows; we call
  ``TerminateProcess`` directly.

Lifting these into one module keeps the Windows-safe logic from drifting across
the multiple call sites (``daemon_registry``, the headless driver,
``commands/platform.py``) that each need it.
"""

from __future__ import annotations

import os
import signal

_STILL_ACTIVE = 259  # Windows GetExitCodeProcess: process has not terminated
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_TERMINATE = 0x0001


def pid_alive(pid: int) -> bool:
    """Return True iff ``pid`` names a currently-running process.

    Windows-safe: distinguishes a live process from a recently-exited (reaped)
    pid, unlike ``os.kill(pid, 0)`` which yields a false positive on Windows.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == _STILL_ACTIVE
            return False
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    # POSIX: a child that has been killed but not yet ``wait()``-reaped lingers
    # as a *zombie* (defunct). ``os.kill(pid, 0)`` still succeeds for a zombie,
    # but a zombie has terminated — it is NOT a running process. Reporting it as
    # alive is the exact same false-positive class this module exists to prevent
    # on Windows for reaped pids (a dead process probed as live blocks watchdog
    # resurrection). Treat zombies as dead. Linux exposes the state via /proc;
    # platforms without /proc (e.g. macOS) degrade gracefully to the old behavior.
    return not _is_zombie(pid)


def _is_zombie(pid: int) -> bool:
    """True iff ``pid`` is a zombie (terminated, awaiting reap) on Linux.

    Reads ``/proc/<pid>/stat`` and inspects the process state field. Returns
    False on any platform/condition where the state can't be read (no /proc,
    permission error, race) so callers fall back to the ``os.kill`` verdict.
    """
    try:
        with open(f"/proc/{pid}/stat", "rb") as fh:
            data = fh.read()
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return False
    # Format: "<pid> (<comm>) <state> ...". ``comm`` may itself contain spaces
    # and parentheses, so anchor on the LAST ')' before reading the state char.
    rparen = data.rfind(b")")
    if rparen == -1:
        return False
    rest = data[rparen + 1 :].split()
    return bool(rest) and rest[0] == b"Z"


def terminate_pid(pid: int) -> bool:
    """Best-effort terminate ``pid``. Returns True if the kill was issued.

    Windows-safe: uses ``TerminateProcess`` rather than ``os.kill(pid, SIGTERM)``.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_PROCESS_TERMINATE, False, pid)
        if not handle:
            return False
        try:
            return bool(kernel32.TerminateProcess(handle, 1))
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except (OSError, ProcessLookupError):
        return False
