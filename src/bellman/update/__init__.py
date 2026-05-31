"""Self-update: GitHub release check, download, and binary install."""

from bellman.update.background import maybe_notify_update
from bellman.update.check import CheckResult, check_for_update, run_update_command

__all__ = [
    "CheckResult",
    "check_for_update",
    "maybe_notify_update",
    "run_update_command",
]
