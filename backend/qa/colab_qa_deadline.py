"""Coordinator-owned wall-clock budget for one QA run. Fake clock in tests.

A socket timeout bounds inactivity of ONE operation; it is not a total deadline.
This object is the only authority on whether a NEW step may start, and it
records overruns after a step returns. It cannot interrupt a call that never
returns, abort an in-flight request or survive process loss. Those limits stay
NOT VERIFIED; the durable ownership record (never CLEANED) is then the recovery
signal and blocks any further Runtime creation.

Work window: work start -> cleanup start, at most 25 minutes.
Runtime window: Runtime creation mark (before create POST) -> confirmed CLEANED,
at most 30 minutes. New work never starts unless a cleanup reserve remains.
Cleanup itself is never skipped for time: deleting is the safe action.
"""
import math
import time

from src.services.colab_runtime_ownership import OwnershipState

WORK_LIMIT_SECONDS = 25 * 60
RUNTIME_LIMIT_SECONDS = 30 * 60
REQUEST_TIMEOUT_SECONDS = 20
# ESTIMATE, not a worst-case bound: file DELETE/GETs, run-dir list/DELETE/GET,
# Runtime DELETE/GET, list. Account checks, up to 5 list pages and per-phase
# httpx timeouts can exceed it; an overrun is then recorded FAIL, never hidden,
# and cleanup still runs.
CLEANUP_RESERVE_SECONDS = 12 * REQUEST_TIMEOUT_SECONDS
MAX_RUNTIMES_PER_RUN = 1


def bounded_timeout(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and 0 < value <= REQUEST_TIMEOUT_SECONDS)


class RunDeadline:
    """Single-run monotonic budget. A non-monotonic clock invalidates the run."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._last = None
        self.work_started = self.runtime_created = None
        self.cleanup_started = self.runtime_cleaned = None
        self.runtimes_created = 0
        self.overrun = False
        self.clock_invalid = False

    def _now(self):
        try:
            value = self._clock()
        except Exception:
            value = None
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or (self._last is not None and value < self._last)):
            self.clock_invalid = True
            return None
        self._last = value
        return value

    def start_work(self):
        if self.work_started is not None:
            return False
        self.work_started = self._now()
        return self.work_started is not None

    def mark_runtime_created(self):
        """Call immediately BEFORE the create POST; counts even if create fails."""
        if self.work_started is None or self.runtimes_created >= MAX_RUNTIMES_PER_RUN:
            return False
        now = self._now()
        if now is None:
            return False
        self.runtimes_created += 1
        self.runtime_created = now
        return True

    def may_start(self, step_seconds=REQUEST_TIMEOUT_SECONDS):
        """New work may start only if it and the cleanup reserve still fit."""
        if (not bounded_timeout(step_seconds) or self.clock_invalid or self.overrun
                or self.work_started is None or self.runtime_created is None
                or self.cleanup_started is not None):
            return False
        now = self._now()
        if now is None:
            return False
        return (now - self.work_started + step_seconds <= WORK_LIMIT_SECONDS
                and now - self.runtime_created + step_seconds + CLEANUP_RESERVE_SECONDS
                <= RUNTIME_LIMIT_SECONDS)

    def may_create_runtime(self):
        if (self.clock_invalid or self.work_started is None or self.runtime_created is not None
                or self.runtimes_created >= MAX_RUNTIMES_PER_RUN or self.cleanup_started is not None):
            return False
        now = self._now()
        return now is not None and (now - self.work_started + REQUEST_TIMEOUT_SECONDS
                                    + CLEANUP_RESERVE_SECONDS <= WORK_LIMIT_SECONDS)

    def check_step(self):
        """After any returned step: record (never hide) a limit overrun."""
        now = self._now()
        if now is None:
            return
        if self.work_started is not None and self.cleanup_started is None and (
                now - self.work_started > WORK_LIMIT_SECONDS):
            self.overrun = True
        if (self.runtime_created is not None and self.runtime_cleaned is None
                and now - self.runtime_created > RUNTIME_LIMIT_SECONDS):
            self.overrun = True

    def begin_cleanup(self):
        if self.cleanup_started is None:
            self.check_step()
            self.cleanup_started = self._now()

    def mark_runtime_cleaned(self):
        """Only after DELETE + GET/list absence + durable CLEANED were observed."""
        if self.runtime_cleaned is None and self.runtime_created is not None:
            self.check_step()
            self.runtime_cleaned = self._now()

    def elapsed(self):
        work = (None if None in (self.work_started, self.cleanup_started)
                else int(self.cleanup_started - self.work_started))
        runtime = (None if None in (self.runtime_created, self.runtime_cleaned)
                   else int(self.runtime_cleaned - self.runtime_created))
        return work, runtime

    def verdict(self):
        """Measured compliance only. It is not proof of hard enforcement."""
        if self.clock_invalid:
            return "NOT_VERIFIED"
        if self.overrun:
            return "FAIL"
        if None in (self.work_started, self.runtime_created, self.cleanup_started, self.runtime_cleaned):
            return "NOT_VERIFIED"
        if (self.cleanup_started - self.work_started > WORK_LIMIT_SECONDS
                or self.runtime_cleaned - self.runtime_created > RUNTIME_LIMIT_SECONDS):
            return "FAIL"
        return "PASS"


def authorize_runtime_creation(store, deadline):
    """QA gate a future live script must pass before RuntimeOwnership.create().

    At most one Runtime per run; any non-CLEANED record (uncertain ownership,
    pending recovery or a previous crash) blocks; no automatic recreation.
    It never creates, deletes, resets or quarantines anything itself.
    """
    if type(deadline) is not RunDeadline or not deadline.may_create_runtime():
        return False
    try:
        records = store.load()
    except Exception:
        return False
    if any(record.state is not OwnershipState.CLEANED for record in records):
        return False
    return deadline.mark_runtime_created()
