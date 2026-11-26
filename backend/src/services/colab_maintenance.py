"""Best-effort official Colab upkeep at app start and when a block is seen (#60).

1. Renew stored Google tokens (Colab, Drive) so a merely expired access token
   never shows as "not connected".
2. Recover this app's own unresolved Runtime records through the existing
   RuntimeOwnership.recover() (no create, no broad list, deletes only an
   owned Runtime proven by the record).
3. Once every owned Runtime is CLEANED and no Job is active, settle file
   checkpoints left ACTIVE / STATE_UNCERTAIN / CLEANUP_REQUIRED: no remote
   work can outlive its deleted Runtime, so they become FAILED (the existing
   explicit-retry state). Verified chunk caches are kept for reuse.

Never raises; never creates a Runtime; never touches Local or paid paths.
"""

import json
import logging
import threading
import time
from pathlib import Path

from src.services.colab_runtime_ownership import OwnershipState, OwnershipStore, RuntimeOwnership

logger = logging.getLogger(__name__)

UNSETTLED = {"ACTIVE", "STATE_UNCERTAIN", "CLEANUP_REQUIRED"}


def refresh_tokens(colab_auth, drive_auth):
    try:
        if colab_auth.refreshable():
            colab_auth.check(include_preflight=False)
    except Exception as exc:
        logger.info("Colab token refresh skipped (%s)", type(exc).__name__)
    try:
        if drive_auth.token_path.exists():
            drive_auth.ensure_client()
    except Exception as exc:
        logger.info("Drive token refresh skipped (%s)", type(exc).__name__)


def recover_owned_runtimes(colab_auth, store, *, client_factory=None):
    """One pass. Returns True when every record is CLEANED afterwards."""
    pending = [r for r in store.load() if r.state is not OwnershipState.CLEANED]
    if not pending:
        return True
    try:
        credentials = colab_auth.for_launch()
    except Exception as exc:
        logger.info("Colab recovery needs a connected account (%s)", type(exc).__name__)
        return False
    if credentials is None:
        return False
    if client_factory is None:
        from src.services.colab_account_verifier import GoogleAccountVerifier
        from src.services.colab_runtime_client import ColabRuntimeClient

        def client_factory(token):
            return ColabRuntimeClient(token, account_verifier=GoogleAccountVerifier())
    for record in pending:
        client = client_factory(credentials.access_token)
        try:
            result = RuntimeOwnership(store, client).recover(record.execution_id)
            logger.info("Colab recovery %s -> %s", record.execution_id[:8], getattr(result.state, "value", result.state))
        except Exception as exc:
            logger.info("Colab recovery %s failed (%s)", record.execution_id[:8], type(exc).__name__)
        finally:
            try:
                client.close()
            except Exception:
                pass
    return all(r.state is OwnershipState.CLEANED for r in store.load())


def settle_file_checkpoints(cache_root, store, *, job_active):
    """Returns the number of checkpoints moved to FAILED."""
    if job_active():
        return 0
    if any(r.state is not OwnershipState.CLEANED for r in store.load()):
        return 0
    from src.services.colab_full_file_pipeline import ColabFullFilePipeline

    settled = 0
    for checkpoint in sorted(Path(cache_root).glob(".pipeline-locks/*/attempt.json")):
        try:
            value = json.loads(checkpoint.read_text(encoding="utf-8"))
            if value.get("status") not in UNSETTLED:
                continue
            with OwnershipStore(checkpoint.parent).transaction():
                if job_active():
                    return settled
                ColabFullFilePipeline._checkpoint(checkpoint, value["execution_id"], "FAILED")
            settled += 1
        except Exception as exc:
            logger.info("Colab checkpoint left unchanged (%s)", type(exc).__name__)
    return settled


class ColabMaintenance:
    """Runs the steps above on a daemon thread, at most once per interval."""

    def __init__(self, *, colab_auth, drive_auth, store, cache_root, job_active, min_interval=60.0,
                 clock=time.monotonic):
        self._colab_auth, self._drive_auth = colab_auth, drive_auth
        self._store, self._cache_root, self._job_active = store, cache_root, job_active
        self._min_interval, self._clock = min_interval, clock
        self._lock = threading.Lock()
        self._running, self._last = False, None

    def run_once(self, *, refresh=True):
        if refresh:
            refresh_tokens(self._colab_auth, self._drive_auth)
        try:
            if self._job_active():
                return
            if recover_owned_runtimes(self._colab_auth, self._store):
                settle_file_checkpoints(self._cache_root, self._store, job_active=self._job_active)
        except Exception as exc:
            logger.info("Colab maintenance skipped (%s)", type(exc).__name__)

    def start(self, *, refresh=True, force=False):
        with self._lock:
            now = self._clock()
            if self._running or (not force and self._last is not None
                                 and now - self._last < self._min_interval):
                return False
            self._running, self._last = True, now

        def work():
            try:
                self.run_once(refresh=refresh)
            finally:
                with self._lock:
                    self._running = False
        threading.Thread(target=work, name="colab-maintenance", daemon=True).start()
        return True
