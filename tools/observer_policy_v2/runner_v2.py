"""Fail-closed fixture runner; no credentials, build account or build commands."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from observer_v2 import (ObservationError, PERMIT, ROOTS, VERSION, check_ancestors,
                         digest, exclusive_json, file_hash, journal_lock, load,
                         process_start, require_fixture, publish_json, latch_stop,
                         snapshot)


class Gate:
    def __init__(self, fixture, run_id, max_age=2.0):
        self.root = require_fixture(fixture, run_id)
        self.audit = self.root / "audit"
        self.run_id = run_id
        self.baseline_hash = file_hash(self.audit / "baseline.json")
        self.policy_hash = digest({"version": VERSION, "roots": ROOTS, "fixture_only": True})
        self.sequence = 0
        self.max_age = max_age
        self.identity = load(self.audit / "OBSERVER_IDENTITY.json")
        if not 0 < max_age <= 90:
            raise ObservationError("INVALID_FRESHNESS_BOUND")

    def validate(self, final_nonce=None, request_at=None, after_sequence=None):
        with journal_lock(self.audit):
            return self._validate(final_nonce, request_at, after_sequence)

    def _validate(self, final_nonce, request_at, after_sequence):
        check_ancestors(self.audit)
        for name in ("baseline.json", "heartbeat.json", "OBSERVER_IDENTITY.json"):
            check_ancestors(self.audit / name)
        if (self.audit / "STOP.json").exists():
            raise ObservationError("STOP_PRESENT")
        if file_hash(self.audit / "baseline.json") != self.baseline_hash:
            raise ObservationError("BASELINE_CHANGED")
        if load(self.audit / "OBSERVER_IDENTITY.json") != self.identity:
            raise ObservationError("OBSERVER_IDENTITY_RECORD_CHANGED")
        heartbeat = load(self.audit / "heartbeat.json")  # All I/O failures propagate.
        sequence = heartbeat["sequence"]
        if type(sequence) is not int or sequence < 1 or sequence < self.sequence:
            raise ObservationError("SEQUENCE_INVALID")
        if heartbeat.get("run_id") != self.run_id:
            raise ObservationError("RUN_ID_MISMATCH")
        if (heartbeat.get("observer") != self.identity
                or process_start(self.identity["pid"]) != self.identity["start"]):
            raise ObservationError("OBSERVER_PROCESS_IDENTITY_CHANGED")
        if heartbeat.get("policy_hash") != self.policy_hash or heartbeat.get("baseline_hash") != self.baseline_hash:
            raise ObservationError("PINNED_IDENTITY_MISMATCH")
        age = time.time() - heartbeat["at"]
        if age < 0 or age > self.max_age:
            raise ObservationError("HEARTBEAT_EXPIRED_OR_FUTURE")
        if heartbeat.get("permit") is not True or heartbeat.get("classification") not in PERMIT:
            raise ObservationError("NO_OBSERVER_PERMISSION")
        previous = None
        # Validate the complete chain, not just a mutable heartbeat assertion.
        for number in range(1, sequence + 1):
            commit_path = self.audit / f"commit-{number:08d}.json"
            check_ancestors(commit_path)
            commit = load(commit_path)
            if (commit.get("run_id") != self.run_id or commit.get("sequence") != number
                    or commit.get("baseline_hash") != self.baseline_hash
                    or commit.get("policy_hash") != self.policy_hash
                    or commit.get("observer") != self.identity
                    or commit.get("previous_commit") != previous):
                raise ObservationError("AUDIT_CHAIN_MISMATCH")
            for kind in ("raw", "decision", "state"):
                path = self.audit / f"{kind}-{number:08d}.json"
                check_ancestors(path)
                if file_hash(path) != commit["hashes"][kind]:
                    raise ObservationError("AUDIT_HASH_MISMATCH")
                payload = load(path)
                if any(payload.get(k) != commit.get(k) for k in ("run_id", "sequence", "policy_hash", "baseline_hash", "at", "final_nonce", "observer")):
                    raise ObservationError("AUDIT_SEQUENCE_MISMATCH")
                if kind == "decision" and (payload["decision"]["permit"] is not True
                                           or payload["decision"]["classification"] not in PERMIT):
                    raise ObservationError("HISTORICAL_HOLD_OR_STOP")
            previous = digest(commit)
        # A partial transaction or unpublished commit must never reuse old permission.
        for kind in ("raw", "decision", "state", "commit"):
            names = {p.name for p in self.audit.glob(kind + "-*.json")}
            expected = {f"{kind}-{i:08d}.json" for i in range(1, sequence + 1)}
            if names != expected:
                raise ObservationError("INCOMPLETE_OR_UNPUBLISHED_TRANSACTION")
        if (heartbeat.get("commit_hash") != previous
                or any(heartbeat.get(k) != commit.get(k) for k in ("at", "final_nonce"))):
            raise ObservationError("HEARTBEAT_COMMIT_MISMATCH")
        decision = load(self.audit / f"decision-{sequence:08d}.json")["decision"]
        if heartbeat["classification"] != decision["classification"]:
            raise ObservationError("HEARTBEAT_DECISION_MISMATCH")
        if final_nonce is not None:
            if (heartbeat.get("final_nonce") != final_nonce or heartbeat["at"] < request_at
                    or sequence <= after_sequence):
                raise ObservationError("FINAL_OBSERVATION_NOT_CONFIRMED")
        if (self.audit / "STOP.json").exists():
            raise ObservationError("FINAL_STOP_PRESENT")
        self.sequence = sequence
        return heartbeat


def stop_owned(process):
    # Popen retains the owned process handle; no name-wide or PID-only termination.
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def final_state(gate, heartbeat):
    expected = load(gate.audit / f"state-{heartbeat['sequence']:08d}.json")["snapshot"]
    if snapshot(gate.root) != expected or snapshot(gate.root) != expected:
        raise ObservationError("POST_NONCE_OBSERVATION_CHANGED")
    return digest(expected)


def verify_completion(gate, heartbeat):
    """Caller holds journal lock. Existence or a candidate result is insufficient."""
    for name in ("FINAL_REQUEST.json", "RUNNER_RESULT.json", "COMPLETION.json"):
        check_ancestors(gate.audit / name)
    request = load(gate.audit / "FINAL_REQUEST.json")
    result = load(gate.audit / "RUNNER_RESULT.json")
    completion = load(gate.audit / "COMPLETION.json")
    seal = result.pop("seal", None)
    if seal != digest(result):
        raise ObservationError("RESULT_SEAL_INVALID")
    binding = {k: heartbeat[k] for k in ("run_id", "sequence", "policy_hash", "baseline_hash", "observer", "final_nonce", "commit_hash")}
    if (not isinstance(request.get("nonce"), str) or not re.fullmatch(r"[0-9a-f]{32}", request["nonce"])
            or request.get("run_id") != gate.run_id or request.get("nonce") != heartbeat["final_nonce"]
            or heartbeat["at"] < request["at"] or heartbeat["sequence"] <= request["after_sequence"]
            or result.get("binding") != binding
            or result.get("snapshot_hash") != final_state(gate, heartbeat)
            or any(result.get(k) != v for k, v in {"run_id": gate.run_id, "success": True,
                   "permit": True, "child_exit": 0, "runner_exit": 0, "cleanup_verified": True}.items())
            or completion != {"run_id": gate.run_id, "final_nonce": request["nonce"],
                              "result_sha256": file_hash(gate.audit / "RUNNER_RESULT.json"),
                              "commit_hash": heartbeat["commit_hash"]}):
        raise ObservationError("COMPLETION_CONTRACT_INVALID")
    if (gate.audit / "STOP.json").exists() or (gate.audit / "RUNNER_FAILURE.json").exists():
        raise ObservationError("COMPLETION_STOP_LATCHED")
    return result


def finalize(gate, result, nonce, request_at, after_sequence):
    # Candidate + completion commit, both create-new atomic publications. Completion
    # is the success boundary; a latched STOP invalidates both records for readers.
    with journal_lock(gate.audit):
        hb = gate._validate(nonce, request_at, after_sequence)
        candidate = {**result, "success": True, "permit": True, "runner_exit": 0,
                     "cleanup_verified": True, "reason": "FINAL_OBSERVATION_CONFIRMED",
                     "binding": {k: hb[k] for k in ("run_id", "sequence", "policy_hash", "baseline_hash", "observer", "final_nonce", "commit_hash")},
                     "snapshot_hash": final_state(gate, hb)}
        candidate["seal"] = digest(candidate)
        try:
            publish_json(gate.audit / "RUNNER_RESULT.json", candidate)
        except Exception as error:
            raise ObservationError("RESULT_AUDIT_FAILED") from error
        gate._validate(nonce, request_at, after_sequence)
        final_state(gate, hb)
        publish_json(gate.audit / "COMPLETION.json",
                     {"run_id": gate.run_id, "final_nonce": nonce,
                      "result_sha256": file_hash(gate.audit / "RUNNER_RESULT.json"),
                      "commit_hash": hb["commit_hash"]})
        # Detect STOP injected during publication, including noncooperating writers.
        hb = gate._validate(nonce, request_at, after_sequence)
        return verify_completion(gate, hb)


def run_guarded(fixture, run_id, command, max_age=2.0, final_timeout=3.0, task_timeout=5.0):
    root = require_fixture(fixture, run_id)
    # A CLI build adapter is deliberately absent in STEP 1-A. This API also restricts
    # children to the synthetic fixture helper shipped with this module.
    helper = Path(__file__).with_name("synthetic_child.py").resolve()
    if (len(command) != 5 or Path(command[0]).resolve() != Path(sys.executable).resolve()
            or Path(command[1]).resolve() != helper or command[2] != str(root)
            or command[3] != run_id or command[4] not in {"success", "wait", "stop-at-exit"}):
        raise ObservationError("SYNTHETIC_CHILD_ONLY")
    gate = None
    process = None
    result = {"run_id": run_id, "success": False, "permit": False, "child_started": False,
              "child_exit": None, "runner_exit": 1, "reason": None}
    started_at = time.monotonic()
    try:
        gate = Gate(root, run_id, max_age)
        gate.validate()  # Before process creation, including a fast exit-0 child.
        process = subprocess.Popen(command, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        result["child_started"] = True
        while True:
            gate.validate()  # I/O failure never skips into a successful iteration.
            if process.poll() is not None:
                break
            if time.monotonic() - started_at > task_timeout:
                raise ObservationError("OWNED_TASK_TIMEOUT")
            time.sleep(0.02)
        result["child_exit"] = process.returncode
        if process.returncode != 0:
            raise ObservationError("CHILD_FAILED")
        # Exit 0 is insufficient. Request a new same-run observation after exit.
        after_sequence = gate.sequence
        request_at = time.time()
        nonce = uuid.uuid4().hex
        with journal_lock(gate.audit):
            publish_json(gate.audit / "FINAL_REQUEST.json",
                           {"run_id": run_id, "nonce": nonce, "at": request_at,
                            "after_sequence": after_sequence})
        deadline = time.monotonic() + final_timeout
        while True:
            heartbeat = gate.validate()
            if heartbeat.get("final_nonce") == nonce:
                # Owned child must be cleaned up BEFORE any success record exists.
                stop_owned(process)
                if process.poll() != 0:
                    raise ObservationError("OWNED_PROCESS_CLEANUP_UNVERIFIED")
                result.update(finalize(gate, result, nonce, request_at, after_sequence))
                break
            if time.monotonic() >= deadline:
                raise ObservationError("FINAL_OBSERVATION_TIMEOUT")
            time.sleep(0.02)
    except Exception as error:
        result["reason"] = type(error).__name__ + ":" + str(error)
        if str(error) == "RESULT_AUDIT_FAILED":
            result["reason"] = "RESULT_AUDIT_FAILED"
    if not result["success"]:
        result.update(success=False, permit=False, runner_exit=1)
        try:
            if process is not None:
                stop_owned(process)
                result["child_exit"] = process.returncode
        except Exception as error:
            result["reason"] = "OWNED_PROCESS_CLEANUP_FAILED:" + type(error).__name__
        try:
            latch_stop(root / "audit", run_id, result["reason"])
            publish_json(root / "audit" / "RUNNER_FAILURE.json", result)
            if not (root / "audit" / "RUNNER_RESULT.json").exists():
                publish_json(root / "audit" / "RUNNER_RESULT.json", result)
        except Exception:
            result["reason"] = "RESULT_AUDIT_FAILED"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--child-mode", choices=("success", "wait", "stop-at-exit"), default="success")
    args = parser.parse_args()
    try:
        root = require_fixture(args.fixture, args.run_id)
        command = [sys.executable, str(Path(__file__).with_name("synthetic_child.py").resolve()),
                   str(root), args.run_id, args.child_mode]
        return run_guarded(root, args.run_id, command)["runner_exit"]
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
