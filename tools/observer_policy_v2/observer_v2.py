"""STEP 1-A standalone Observer successor. Fixture-only; never a production adapter."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
import uuid

VERSION = "observer-policy-v2-step1c"
PERMIT = {"NO_CHANGE", "ALLOW_RECORDED", "WARN_RECORDED"}
RANK = {"NO_CHANGE": 0, "ALLOW_RECORDED": 1, "WARN_RECORDED": 2,
        "INVESTIGATE_HOLD": 3, "HARD_STOP": 4}
ROOTS = ("general", "protected", "webview")
EPOCH_TICKS = 621355968000000000


class ObservationError(RuntimeError):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def load(path):
    with open(path, "rb") as stream:
        return json.load(stream)


def file_hash(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def process_start(pid):
    if os.name != "nt":
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ObservationError("OBSERVER_PROCESS_UNAVAILABLE")
    try:
        created, exited, kernel_time, user = (wintypes.FILETIME() for _ in range(4))
        code = wintypes.DWORD()
        if (not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel_time), ctypes.byref(user))
                or not kernel.GetExitCodeProcess(handle, ctypes.byref(code))):
            raise ObservationError("OBSERVER_PROCESS_UNVERIFIABLE")
        if code.value != 259:
            raise ObservationError("OBSERVER_PROCESS_EXITED")
        return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
    finally:
        kernel.CloseHandle(handle)


def reparse(info):
    return bool(getattr(info, "st_file_attributes", 0) & 0x400) or stat.S_ISLNK(info.st_mode)


def check_ancestors(path):
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            if reparse(os.lstat(item)):
                raise ObservationError("REPARSE_ANCESTOR")


def require_fixture(path, run_id):
    path = Path(os.path.abspath(path))
    temp = Path(tempfile.gettempdir()).resolve()
    if path.parent.resolve() != temp or not re.fullmatch(r"sorigul-observer-v2-[0-9a-f]{32}", path.name):
        raise ObservationError("FIXTURE_ONLY_TEMP_ROOT_REQUIRED")
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ObservationError("INVALID_RUN_ID")
    check_ancestors(path)
    if load(path / "fixture.json") != {"run_id": run_id, "fixture_only": True}:
        raise ObservationError("FIXTURE_MARKER_MISMATCH")
    # Audit is a sibling of the observed data, never a child of a watched root.
    for item in (path / "data", path / "audit"):
        check_ancestors(item)
    return path


def create_fixture():
    run_id = uuid.uuid4().hex
    root = Path(tempfile.gettempdir()) / ("sorigul-observer-v2-" + uuid.uuid4().hex)
    root.mkdir()
    (root / "fixture.json").write_bytes(encoded({"run_id": run_id, "fixture_only": True}))
    for name in ROOTS:
        (root / "data" / name).mkdir(parents=True)
    (root / "audit").mkdir()
    require_fixture(root, run_id)
    return root, run_id


def exclusive_json(path, value):
    # Create-new + flush is used for every historical artifact. No replacements.
    with open(path, "xb") as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def publish_json(path, value):
    """Flush a private stage, then publish atomically without replacing history."""
    check_ancestors(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".pending")
    try:
        exclusive_json(temporary, value)
        os.link(temporary, path)  # create-new, same-volume NTFS fixture only
    finally:
        if temporary.exists():
            temporary.unlink()


def latch_stop(audit, run_id, reason):
    # STOP is monotonic and independent of the journal lock. Never clear/rewrite it.
    try:
        exclusive_json(audit / "STOP.json", {"run_id": run_id, "reason": reason})
    except FileExistsError:
        pass


def fixture_scope():
    # Synthetic isolation assertion, NOT evidence about a real build account/ACL.
    # The production R01-R10/F01-F08 mapping remains an unimplemented adapter.
    return {"version": 1, "noncore_roots": ["general"],
            "isolation_intact": True, "observation_complete": True,
            "registered_paths": [], "sensitive_prefixes": [
                "general/settings", "general/jobs", "general/auth", "general/core",
                "general/runtime", "general/results", "general/installed"]}


def atomic_pointer(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        exclusive_json(temporary, value)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def journal_lock(audit, timeout=0.5):
    check_ancestors(audit)
    path = audit / "transaction.lock"
    check_ancestors(path)
    stream = open(path, "a+b")
    if stream.seek(0, 2) == 0:
        stream.write(b"0")
        stream.flush()
    deadline = time.monotonic() + timeout
    locked = False
    try:
        while not locked:
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise ObservationError("AUDIT_LOCK_UNAVAILABLE")
                time.sleep(0.01)
        yield
    finally:
        if locked:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_UN)
        stream.close()


def snapshot(root):
    result = []
    for root_id in ROOTS:
        base = root / "data" / root_id
        check_ancestors(base)
        if not base.is_dir():
            raise ObservationError("PROTECTED_ROOT_MISSING")
        rows = []
        queue = [base]
        while queue:
            directory = queue.pop(0)
            check_ancestors(directory)
            for item in sorted(directory.iterdir(), key=lambda item: item.name):
                info = os.lstat(item)
                linked = reparse(info)
                is_directory = stat.S_ISDIR(info.st_mode)
                relative = item.relative_to(base).as_posix().replace("/", "\\")
                row = {"path": relative, "directory": is_directory, "reparse": linked,
                       "attributes": getattr(info, "st_file_attributes", info.st_mode),
                       "write_ticks": info.st_mtime_ns // 100 + EPOCH_TICKS,
                       "identity": [info.st_dev, info.st_ino], "links": info.st_nlink}
                if not is_directory:
                    row["size"] = info.st_size
                # Preserve the legacy content scope; no general media/auth hashing.
                if not linked and not is_directory and root_id == "protected" and item.name in {"settings.json", "jobs.json", "runtime-manifest.json", "manifest.json"}:
                    row["sha256"] = file_hash(item)
                rows.append(row)
                if is_directory and not linked:
                    queue.append(item)
        result.append({"root": root_id, "exists": True, "entries": rows})
    return result


def index_snapshot(value):
    if len(value) != len(ROOTS) or {v["root"] for v in value} != set(ROOTS):
        raise ObservationError("ROOT_SET_CHANGED")
    indexed = {}
    for root in value:
        if root["exists"] is not True:
            raise ObservationError("ROOT_EXISTENCE_CHANGED")
        for row in root["entries"]:
            path = row["path"]
            if not path or ":" in path or path.startswith(("/", "\\")) or any(p in {"", ".", ".."} for p in path.split("\\")):
                raise ObservationError("UNSAFE_RELATIVE_PATH")
            identity = row.get("identity")
            if (not isinstance(identity, list) or len(identity) != 2
                    or type(identity[1]) is not int or identity[1] <= 0):
                raise ObservationError("FILE_IDENTITY_UNAVAILABLE")
            key = (root["root"], path.casefold())
            if key in indexed:
                raise ObservationError("AMBIGUOUS_PATH_IDENTITY")
            indexed[key] = row
    return indexed


def legacy_fields(row):
    return {k: v for k, v in row.items() if k not in {"identity", "links"}}


def canonical_raw(before, after):
    """Retain the ordinal comparison as raw evidence; it never grants permission."""
    differences = []
    for old_root, new_root in zip(before, after):
        if old_root["root"] != new_root["root"] or old_root["exists"] != new_root["exists"]:
            differences.append({"kind": "root_changed"})
        old_rows, new_rows = old_root["entries"], new_root["entries"]
        for number in range(max(len(old_rows), len(new_rows))):
            old = legacy_fields(old_rows[number]) if number < len(old_rows) else None
            new = legacy_fields(new_rows[number]) if number < len(new_rows) else None
            if old != new:
                differences.append({"root": old_root["root"], "ordinal": number,
                                    "before": old, "after": new})
    if len(before) != len(after):
        differences.append({"kind": "root_count_changed"})
    return {"classification": "HARD_STOP" if differences else "NO_CHANGE",
            "differences": differences,
            "scope": "ordinal captured metadata; separate policy decision"}


def path_delta(before, after):
    old, new = index_snapshot(before), index_snapshot(after)
    events = []
    for key in sorted(old.keys() | new.keys()):
        a, b = old.get(key), new.get(key)
        if a != b:
            events.append({"root": key[0], "path": (b or a)["path"],
                           "kind": "added" if a is None else "deleted" if b is None else "modified",
                           "before": a, "after": b})
    return events


def allowed_mtime(event):
    # Literal #189 boundary; an added entry, file, reparse or other field cannot qualify.
    a, b = event["before"], event["after"]
    return (event["root"] == "webview" and event["kind"] == "modified"
            and a["directory"] is True and b["directory"] is True
            and a["reparse"] is False and b["reparse"] is False
            and "attributes" in a and "attributes" in b
            and bool(re.fullmatch(r"EBWebView(?:\\[^\\/:]+)*", a["path"]))
            and all(p not in {".", ".."} for p in a["path"].split("\\"))
            and {k: v for k, v in a.items() if k != "write_ticks"}
            == {k: v for k, v in b.items() if k != "write_ticks"})


def classify(events, evidence, scope):
    decisions = []
    for event in events:
        row = event["after"]
        status, reason = "INVESTIGATE_HOLD", "INSUFFICIENT_EVIDENCE"
        proof = evidence.get(event["root"] + "/" + event["path"], {})
        key = (event["root"] + "/" + event["path"].replace("\\", "/")).casefold()
        sensitive = any(key == p.casefold() or key.startswith(p.casefold() + "/")
                        for p in scope.get("sensitive_prefixes", []))
        if event["kind"] in {"modified", "deleted"}:
            status, reason = ("WARN_RECORDED", "EXACT_189_DIRECTORY_MTIME") if allowed_mtime(event) else ("HARD_STOP", "EXISTING_ENTRY_CHANGED")
        elif proof.get("build_account_intrusion") is True:
            status, reason = "HARD_STOP", "BUILD_ACCOUNT_INTRUSION"
        elif row["reparse"] or row["links"] != 1:
            reason = "REPARSE_OR_AMBIGUOUS_IDENTITY"
        elif (scope.get("version") != 1 or scope.get("isolation_intact") is not True
              or scope.get("observation_complete") is not True):
            reason = "SCOPE_OR_ISOLATION_UNVERIFIED"
        elif (event["root"] != "general" or event["root"] not in scope.get("noncore_roots", []) or row["directory"]
              or sensitive or key in {p.casefold() for p in scope.get("registered_paths", [])}):
            reason = "SENSITIVE_OR_REGISTERED_ADDITION"
        elif (Path(row["path"]).suffix.lower() in {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".opus", ".mp4", ".srt", ".json", ".msi", ".dll", ".pyd", ".bin"}
              or any(part.lower() in {"exe", "com", "lnk", "ps1", "bat", "cmd", "scr", "js", "vbs"}
                     for part in row["path"].split("\\")[-1].split("."))):
            reason = "AUDIO_REGISTRATION_OR_SENSITIVE_TYPE_UNRESOLVED"
        elif (("metadata_sha256" in proof and proof["metadata_sha256"] != digest(row))
              or ("file_identity" in proof and proof["file_identity"] != row["identity"])):
            reason = "CONFLICTING_BOUND_METADATA"
        else:
            status, reason = "ALLOW_RECORDED", "NONCORE_ADDITION_ONLY_PINNED_SCOPE"
        item = {"root": event["root"], "path": event["path"], "kind": event["kind"],
                "classification": status, "reason": reason, "actor": "UNKNOWN"}
        if status == "ALLOW_RECORDED":
            item["admission"] = {"identity": row["identity"], "metadata_sha256": digest(row)}
        decisions.append(item)
    status = max((d["classification"] for d in decisions), key=RANK.get, default="NO_CHANGE")
    return {"classification": status, "permit": status in PERMIT, "events": decisions}


class Observer:
    def __init__(self, fixture, run_id):
        self.root = require_fixture(fixture, run_id)
        self.run_id = run_id
        self.audit = self.root / "audit"
        self.baseline_path = self.audit / "baseline.json"
        self.baseline = load(self.baseline_path)
        self.baseline_hash = file_hash(self.baseline_path)
        self.policy_hash = digest({"version": VERSION, "roots": ROOTS, "fixture_only": True})
        if self.baseline["run_id"] != run_id:
            raise ObservationError("BASELINE_RUN_MISMATCH")
        self.expected = self.baseline["snapshot"]
        self.scope = self.baseline.get("scope", {})
        self.admissions = []
        self.sequence = 0
        self.previous_commit = None
        # Resuming a stopped/partial run is forbidden; a new fixture/run is required.
        if list(self.audit.glob("commit-*.json")) or list(self.audit.glob("raw-*.json")):
            raise ObservationError("RUN_ALREADY_OBSERVED")
        self.identity = {"pid": os.getpid(), "start": process_start(os.getpid())}
        exclusive_json(self.audit / "OBSERVER_IDENTITY.json", self.identity)

    @classmethod
    def initialize(cls, fixture, run_id):
        root = require_fixture(fixture, run_id)
        exclusive_json(root / "audit" / "baseline.json",
                       {"run_id": run_id, "snapshot": snapshot(root), "fixture_only": True,
                        "scope": fixture_scope()})
        return cls(root, run_id)

    def record(self, evidence=None, final_nonce=None):
        with journal_lock(self.audit):
            return self._record(evidence, final_nonce)

    def _record(self, evidence, final_nonce):
        if self.sequence and load(self.audit / f"decision-{self.sequence:08d}.json")["decision"]["permit"] is not True:
            raise ObservationError("TERMINAL_HOLD_OR_STOP")
        if file_hash(self.baseline_path) != self.baseline_hash:
            raise ObservationError("BASELINE_CHANGED")
        current = snapshot(self.root)
        # Two consecutive full metadata observations must agree before any permit.
        if current != snapshot(self.root):
            raise ObservationError("OBSERVATION_RACE")
        events = path_delta(self.expected, current)
        decision = classify(events, evidence or {}, self.scope)
        raw = {"canonical": canonical_raw(self.baseline["snapshot"], current),
               "path_delta": events}
        sequence = self.sequence + 1
        common = {"run_id": self.run_id, "sequence": sequence, "policy_hash": self.policy_hash,
                  "baseline_hash": self.baseline_hash, "at": time.time(), "final_nonce": final_nonce,
                  "observer": self.identity}
        admissions = self.admissions + [{**e, "sequence": sequence} for e in decision["events"]
                                       if "admission" in e]
        state = {**common, "snapshot": current, "admissions": admissions}
        payloads = {"raw": {**common, **raw}, "decision": {**common, "decision": decision}, "state": state}
        for kind, payload in payloads.items():
            exclusive_json(self.audit / f"{kind}-{sequence:08d}.json", payload)
        commit = {**common, "previous_commit": self.previous_commit,
                  "hashes": {k: file_hash(self.audit / f"{k}-{sequence:08d}.json") for k in payloads}}
        exclusive_json(self.audit / f"commit-{sequence:08d}.json", commit)
        if decision["classification"] in {"HARD_STOP", "INVESTIGATE_HOLD"}:
            exclusive_json(self.audit / "STOP.json", {**common, "classification": decision["classification"]})
        atomic_pointer(self.audit / "heartbeat.json", {**common, "commit_hash": digest(commit),
                       "classification": decision["classification"], "permit": decision["permit"]})
        self.sequence = sequence
        self.previous_commit = digest(commit)
        if decision["permit"]:
            # The on-disk original baseline is never rewritten. Committed state records
            # admit additions, so their subsequent modification/deletion is blocking.
            self.expected = current
            self.admissions = admissions
        return decision


def watch(root, run_id, interval=0.05):
    root = require_fixture(root, run_id)
    observer = Observer(root, run_id)
    try:
        while True:
            final_path = root / "audit" / "FINAL_REQUEST.json"
            nonce = None
            if final_path.exists():
                request = load(final_path)
                if request["run_id"] != run_id or not re.fullmatch(r"[0-9a-f]{32}", request["nonce"]):
                    raise ObservationError("FINAL_REQUEST_INVALID")
                nonce = request["nonce"]
            proof_path = root / "evidence.json"
            decision = observer.record(load(proof_path) if proof_path.exists() else {}, nonce)
            if decision["classification"] == "HARD_STOP":
                return 5
            if decision["classification"] == "INVESTIGATE_HOLD":
                return 7
            if nonce:
                from runner_v2 import Gate, verify_completion
                gate = Gate(root, run_id)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    with journal_lock(observer.audit):
                        hb = gate._validate(nonce, request["at"], request["after_sequence"])
                        if snapshot(root) != observer.expected or snapshot(root) != observer.expected:
                            raise ObservationError("POST_NONCE_OBSERVATION_CHANGED")
                        if (observer.audit / "COMPLETION.json").exists():
                            verify_completion(gate, hb)
                            return 0
                    time.sleep(0.01)
                raise ObservationError("FINAL_RESULT_NOT_ACKNOWLEDGED")
            time.sleep(interval)
    except Exception:
        # Never publish a success heartbeat on any audit/observation error. If even
        # STOP storage fails, the runner's bounded observation failure still stops.
        try:
            latch_stop(root / "audit", run_id, "OBSERVATION_OR_AUDIT_FAILED")
        except OSError:
            pass
        return 6


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", choices=("watch",), default="watch")
    args = parser.parse_args()
    try:
        return watch(args.fixture, args.run_id)
    except Exception:
        return 6


if __name__ == "__main__":
    sys.exit(main())
