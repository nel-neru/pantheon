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
        return True
    except (OSError, ProcessLookupError):
        return False


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
