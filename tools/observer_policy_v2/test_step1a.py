"""Fail-fast STEP 1-A safety suite. All mutation targets are retained TEMP fixtures."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

import observer_v2 as observer
from observer_v2 import (Observer, ObservationError, atomic_pointer, create_fixture,
                         digest, encoded, exclusive_json, file_hash, load, snapshot)
from runner_v2 import Gate, run_guarded, stop_owned
from windows_fixture_acl import ExclusiveReadLock, restricted_write_probe

TOOLS = Path(__file__).resolve().parent
MANIFEST = None
FIXTURES = []
BASE_HEAD = "38b856a0dfe18448005a59bf7bb36479f3cd2692"
BASE_TREE = "3f874a209d444e5d421441bf3a35b8dbc19f6440"


def preserved():
    return [{"path": row["path"], "sha256": file_hash(row["path"]),
             "expected": row["sha256"], "same": file_hash(row["path"]) == row["sha256"]}
            for row in load(MANIFEST)]


class Safety(unittest.TestCase):
    def setUp(self):
        self.processes = []
        self.fixture()

    def tearDown(self):
        for process in self.processes:
            stop_owned(process)

    def fixture(self):
        self.root, self.run = create_fixture()
        FIXTURES.append({"test": self._testMethodName, "root": str(self.root), "run_id": self.run})
        for name in ("clip.mp3", "result.txt", "result.json", "result.srt", "settings.json",
                     "jobs.json", "runtime-manifest.json", "manifest.json"):
            (self.root / "data" / "protected" / name).write_bytes(b"synthetic-only")
        self.instance = None

    def initialize(self):
        self.instance = Observer.initialize(self.root, self.run)
        return self.instance

    def record(self, expected, proof=None):
        result = self.instance.record(proof)
        self.assertEqual(result["classification"], expected)
        self.assertEqual(result["permit"], expected in observer.PERMIT)
        return result

    def add_document(self, name="document.pdf"):
        path = self.root / "data" / "general" / name
        path.write_bytes(b"synthetic document; not a real PDF")
        row = next(row for root in snapshot(self.root) if root["root"] == "general"
                   for row in root["entries"] if row["path"] == name)
        return {"general/" + name: {"fixture_only": True, "kind": "ordinary_document",
                "user_confirmed": True, "writer_context": "independent_user_action",
                "build_write_denied": True, "ancestor_acl_reviewed": True,
                "metadata_sha256": digest(row), "file_identity": row["identity"]}}

    def command(self, mode="success"):
        return [sys.executable, str(TOOLS / "synthetic_child.py"), str(self.root), self.run, mode]

    def denied(self, mode="success", **kwargs):
        result = run_guarded(self.root, self.run, self.command(mode), **kwargs)
        self.assertFalse(result["success"])
        self.assertFalse(result["permit"])
        self.assertEqual(result["runner_exit"], 1)
        return result

    def wait_for(self, predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("bounded fixture wait expired")

    def native_environment(self, entry):
        env = os.environ.copy()
        env.update(SOV2_ENTRY=str(TOOLS / entry), SOV2_PYTHON=sys.executable,
                   SOV2_ROOT=str(self.root), SOV2_RUN=self.run, SOV2_TOOLS=str(TOOLS))
        return env

    def native_command(self):
        executable = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        command = ("$ErrorActionPreference='Stop'; $t=$null; $e=$null; "
                   "$engine=@{version=$PSVersionTable.PSVersion.ToString();edition=$PSVersionTable.PSEdition}; "
                   "[IO.File]::WriteAllText((Join-Path $env:SOV2_ROOT ([IO.Path]::GetFileName($env:SOV2_ENTRY)+'.engine.json')),($engine|ConvertTo-Json)); "
                   "$a=[Management.Automation.Language.Parser]::ParseFile($env:SOV2_ENTRY,[ref]$t,[ref]$e); "
                   "if($e.Count){exit 90}; & $a.GetScriptBlock() -Python $env:SOV2_PYTHON "
                   "-FixtureRoot $env:SOV2_ROOT -RunId $env:SOV2_RUN -ToolDirectory $env:SOV2_TOOLS")
        return [str(executable), "-NoProfile", "-NonInteractive", "-Command", command]

    def test_B01_missing_heartbeat_no_child(self):
        self.initialize()
        self.assertFalse(self.denied()["child_started"])

    def test_B02_native_heartbeat_read_lock_no_child(self):
        self.initialize().record()
        with ExclusiveReadLock(self.root / "audit" / "heartbeat.json"):
            self.assertFalse(self.denied()["child_started"])

    def test_B03_expired_and_future_heartbeat_no_child(self):
        for offset in (-120, 120):
            with self.subTest(offset=offset):
                self.fixture()
                self.initialize().record()
                hb = load(self.root / "audit" / "heartbeat.json")
                hb["at"] += offset
                atomic_pointer(self.root / "audit" / "heartbeat.json", hb)
                self.assertFalse(self.denied()["child_started"])

    def test_B04_wrong_run_or_pinned_policy_no_child(self):
        for field in ("run_id", "policy_hash", "baseline_hash"):
            with self.subTest(field=field):
                self.fixture()
                self.initialize().record()
                hb = load(self.root / "audit" / "heartbeat.json")
                hb[field] = "wrong"
                atomic_pointer(self.root / "audit" / "heartbeat.json", hb)
                self.assertFalse(self.denied()["child_started"])

    def test_B05_sequence_mismatch_and_boolean_no_child(self):
        for sequence in (2, 0, True):
            with self.subTest(sequence=sequence):
                self.fixture()
                self.initialize().record()
                hb = load(self.root / "audit" / "heartbeat.json")
                hb["sequence"] = sequence
                atomic_pointer(self.root / "audit" / "heartbeat.json", hb)
                self.assertFalse(self.denied()["child_started"])

    def test_B06_audit_missing_tampered_and_partial_no_child(self):
        for kind in ("missing", "tampered", "partial"):
            with self.subTest(kind=kind):
                self.fixture()
                self.initialize().record()
                state = self.root / "audit" / "state-00000001.json"
                if kind == "missing":
                    state.unlink()
                elif kind == "tampered":
                    state.write_bytes(b"{}")
                else:
                    exclusive_json(self.root / "audit" / "raw-00000002.json", {})
                self.assertFalse(self.denied()["child_started"])

    def test_B07_lost_observer_process_no_child(self):
        exclusive_json(self.root / "audit" / "baseline.json",
                       {"run_id": self.run, "snapshot": snapshot(self.root), "fixture_only": True,
                        "scope": observer.fixture_scope()})
        command = [sys.executable, "-c", "from observer_v2 import Observer; import sys; Observer(sys.argv[1],sys.argv[2]).record()", str(self.root), self.run]
        result = subprocess.run(command, cwd=TOOLS, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(self.denied()["child_started"])

    def test_B08_exit_zero_without_new_final_observation_fails(self):
        self.initialize().record()
        result = self.denied(final_timeout=0.15)
        self.assertTrue(result["child_started"])
        self.assertEqual(result["child_exit"], 0)
        self.assertIn("FINAL_OBSERVATION_TIMEOUT", result["reason"])

    def test_B09_stop_immediately_before_child_exit_zero_fails(self):
        self.initialize().record()
        result = self.denied("stop-at-exit")
        self.assertTrue(result["child_started"])
        self.assertTrue((self.root / "audit" / "STOP.json").exists())

    def test_B10_native_ps5_positive_final_handshake(self):
        exclusive_json(self.root / "audit" / "baseline.json",
                       {"run_id": self.run, "snapshot": snapshot(self.root), "fixture_only": True,
                        "scope": observer.fixture_scope()})
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        watcher = subprocess.Popen(self.native_command(), env=self.native_environment("watch-existing-user-v2.ps1"),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        self.processes.append(watcher)
        self.wait_for(lambda: (self.root / "audit" / "heartbeat.json").exists() or watcher.poll() is not None)
        self.assertIsNone(watcher.poll())
        runner = subprocess.run(self.native_command(), env=self.native_environment("run-as-build-v2.ps1"),
                                capture_output=True, timeout=10, creationflags=flags)
        self.assertEqual(runner.returncode, 0, runner.stderr.decode(errors="replace"))
        self.assertEqual(watcher.wait(timeout=5), 0)
        result = load(self.root / "audit" / "RUNNER_RESULT.json")
        self.assertTrue(result["success"])
        self.assertEqual(result["child_exit"], 0)
        self.assertEqual(result["reason"], "FINAL_OBSERVATION_CONFIRMED")
        engine = load(self.root / "run-as-build-v2.ps1.engine.json")
        self.assertEqual(engine["edition"], "Desktop")
        self.assertTrue(engine["version"].startswith("5.1."))
        hb = load(self.root / "audit" / "heartbeat.json")
        request = load(self.root / "audit" / "FINAL_REQUEST.json")
        self.assertEqual(hb["final_nonce"], request["nonce"])
        self.assertGreaterEqual(hb["at"], request["at"])

    def test_B11_pid_start_identity_mismatch_no_child(self):
        self.initialize().record()
        identity = load(self.root / "audit" / "OBSERVER_IDENTITY.json")
        identity["start"] = "0"
        atomic_pointer(self.root / "audit" / "OBSERVER_IDENTITY.json", identity)
        self.assertFalse(self.denied()["child_started"])

    def test_B12_old_sequence_replay_no_child(self):
        self.initialize().record()
        old = load(self.root / "audit" / "heartbeat.json")
        self.instance.record()
        atomic_pointer(self.root / "audit" / "heartbeat.json", old)
        self.assertFalse(self.denied()["child_started"])

    def test_B13_runner_result_storage_failure_is_not_success(self):
        self.initialize().record()
        (self.root / "audit" / "RUNNER_RESULT.json").mkdir()
        errors = []
        def final_observation():
            try:
                self.wait_for(lambda: (self.root / "audit" / "FINAL_REQUEST.json").exists())
                request = load(self.root / "audit" / "FINAL_REQUEST.json")
                self.instance.record(final_nonce=request["nonce"])
            except Exception as error:
                errors.append(str(error))
        worker = threading.Thread(target=final_observation)
        worker.start()
        try:
            result = self.denied()
        finally:
            worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result["reason"], "RESULT_AUDIT_FAILED")
        self.assertEqual(load(self.root / "audit" / "heartbeat.json")["final_nonce"],
                         load(self.root / "audit" / "FINAL_REQUEST.json")["nonce"])

    def test_B14_non_fixture_and_non_synthetic_child_rejected(self):
        self.initialize().record()
        with self.assertRaises(ObservationError):
            run_guarded(self.root, self.run, [sys.executable, "-c", "raise Exception('forbidden')"])
        with self.assertRaises(ObservationError):
            observer.require_fixture(self.root / "data", self.run)

    def test_B15_audit_storage_does_not_observe_itself(self):
        self.initialize()
        before = snapshot(self.root)
        self.record("NO_CHANGE")
        self.record("NO_CHANGE")
        self.assertEqual(before, snapshot(self.root))
        self.assertEqual(load(self.root / "audit" / "raw-00000002.json")["canonical"]["classification"], "NO_CHANGE")

    def test_B16_io_loss_while_child_running_is_bounded_failure(self):
        self.initialize().record()
        result = {}
        def execute():
            result.update(run_guarded(self.root, self.run, self.command("wait")))
        worker = threading.Thread(target=execute)
        started = time.monotonic()
        worker.start()
        try:
            self.wait_for(lambda: (self.root / "audit" / "CHILD_STARTED.json").exists())
            with ExclusiveReadLock(self.root / "audit" / "heartbeat.json"):
                worker.join(timeout=1)
                self.assertFalse(worker.is_alive())
            self.assertFalse(result["success"])
            self.assertTrue(result["child_started"])
            self.assertEqual(result["runner_exit"], 1)
            self.assertLess(time.monotonic() - started, 2)
        finally:
            worker.join(timeout=6)

    def test_B17_wrong_final_nonce_and_reused_sequence_rejected(self):
        self.initialize().record()
        gate = Gate(self.root, self.run)
        gate.validate()
        with self.assertRaises(ObservationError):
            gate.validate("0" * 32, time.time(), gate.sequence)

    def test_T01_unchanged(self):
        self.initialize()
        self.record("NO_CHANGE")
        self.assertTrue(Gate(self.root, self.run).validate()["permit"])

    def test_T02_one_proven_document_raw_not_rewritten(self):
        self.initialize()
        proof = self.add_document()
        self.record("ALLOW_RECORDED", proof)
        raw = load(self.root / "audit" / "raw-00000001.json")
        self.assertEqual(raw["canonical"]["classification"], "HARD_STOP")
        self.assertEqual([e["kind"] for e in raw["path_delta"]], ["added"])
        self.assertTrue(Gate(self.root, self.run).validate()["permit"])

    def test_T03_six_documents_then_modification_or_deletion_stops(self):
        for action in ("modify", "delete"):
            with self.subTest(action=action):
                self.fixture()
                self.initialize()
                baseline_hash = file_hash(self.root / "audit" / "baseline.json")
                proof = {}
                for number in range(6):
                    proof.update(self.add_document(f"document-{number}.pdf"))
                self.record("ALLOW_RECORDED", proof)
                first_raw_hash = file_hash(self.root / "audit" / "raw-00000001.json")
                self.record("NO_CHANGE")
                path = self.root / "data" / "general" / "document-0.pdf"
                if action == "modify":
                    path.write_bytes(b"unauthorized synthetic replacement")
                else:
                    path.unlink()
                self.record("HARD_STOP")
                self.assertEqual(file_hash(self.root / "audit" / "baseline.json"), baseline_hash)
                self.assertEqual(file_hash(self.root / "audit" / "raw-00000001.json"), first_raw_hash)

    def test_T04_existing_mp3_bytes_size_time_change(self):
        for action in ("bytes_size", "mtime"):
            with self.subTest(action=action):
                self.fixture()
                self.initialize()
                path = self.root / "data" / "protected" / "clip.mp3"
                if action == "mtime":
                    info = path.stat()
                    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2000000000))
                else:
                    path.write_bytes(b"changed synthetic bytes")
                self.record("HARD_STOP")

    def test_T05_existing_mp3_delete_rename(self):
        for action in ("delete", "rename"):
            with self.subTest(action=action):
                self.fixture()
                self.initialize()
                path = self.root / "data" / "protected" / "clip.mp3"
                if action == "delete":
                    path.unlink()
                else:
                    path.rename(path.with_name("renamed.mp3"))
                self.record("HARD_STOP")

    def test_T06_existing_transcript_each_change_delete(self):
        for suffix in ("txt", "json", "srt"):
            for action in ("modify", "delete"):
                with self.subTest(suffix=suffix, action=action):
                    self.fixture()
                    self.initialize()
                    path = self.root / "data" / "protected" / ("result." + suffix)
                    if action == "modify":
                        path.write_bytes(b"changed synthetic transcript")
                    else:
                        path.unlink()
                    self.record("HARD_STOP")

    def test_T07_settings_jobs_runtime_manifest_change(self):
        for name in ("settings.json", "jobs.json", "runtime-manifest.json", "manifest.json"):
            with self.subTest(name=name):
                self.fixture()
                self.initialize()
                path = self.root / "data" / "protected" / name
                info = path.stat()
                path.write_bytes(b"SYNTHETIC-ONLY")  # Same size and restored mtime; hashed state still blocks.
                os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
                self.record("HARD_STOP")

    def test_T08_restricted_token_fixture_acl(self):
        results = restricted_write_probe(self.root, self.run)
        exclusive_json(self.root / "acl-probe-result.json", results)
        self.assertEqual(results, {"existing_write": 5, "directory_add_file": 5, "new_file_create": 5})
        self.assertFalse((self.root / "acl-probe" / "denied.txt").exists())
        self.assertEqual((self.root / "acl-probe" / "existing.txt").read_bytes(), b"synthetic-only")
        self.initialize()
        proof = self.add_document()
        proof["general/document.pdf"]["build_account_intrusion"] = True
        self.record("HARD_STOP", proof)

    def test_T09_native_junction_not_traversed(self):
        self.initialize()
        target = self.root / "junction-target"
        target.mkdir()
        (target / "unobserved.txt").write_bytes(b"synthetic")
        env = os.environ.copy()
        env.update(SOV2_LINK=str(self.root / "data" / "general" / "junction"), SOV2_TARGET=str(target))
        executable = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        result = subprocess.run([str(executable), "-NoProfile", "-NonInteractive", "-Command",
                                 "$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path $env:SOV2_LINK -Target $env:SOV2_TARGET | Out-Null"],
                                env=env, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        exclusive_json(self.root / "junction-result.json", {"exit_code": result.returncode, "traversal_allowed": False})
        self.record("INVESTIGATE_HOLD")
        paths = [row["path"] for root in snapshot(self.root) for row in root["entries"]]
        self.assertNotIn("junction\\unobserved.txt", paths)

    def test_T10_mixed_normal_add_and_existing_change_hard_stop(self):
        self.initialize()
        proof = self.add_document()
        (self.root / "data" / "protected" / "clip.mp3").write_bytes(b"unauthorized synthetic change")
        result = self.record("HARD_STOP", proof)
        self.assertIn("ALLOW_RECORDED", [e["classification"] for e in result["events"]])
        self.assertIn("HARD_STOP", [e["classification"] for e in result["events"]])

    def test_T11_exact_189_mtime_boundary(self):
        for root_id, directory, expected in (("webview", "EBWebView", "WARN_RECORDED"),
                                              ("webview", "EBWebViewSibling", "HARD_STOP"),
                                              ("general", "EBWebView", "HARD_STOP")):
            with self.subTest(root=root_id, directory=directory):
                self.fixture()
                path = self.root / "data" / root_id / directory
                path.mkdir()
                self.initialize()
                info = path.stat()
                os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 2000000000))
                self.record(expected)
        self.fixture()
        path = self.root / "data" / "webview" / "EBWebView"
        path.write_bytes(b"a file is not an allowed directory")
        self.initialize()
        path.write_bytes(b"modified file")
        self.record("HARD_STOP")

    def test_T12_audit_race_and_unproven_identity_fail_closed(self):
        self.initialize()
        (self.root / "audit" / "decision-00000001.json").mkdir()
        with self.assertRaises(OSError):
            self.instance.record()
        self.assertFalse((self.root / "audit" / "heartbeat.json").exists())
        self.assertTrue((self.root / "audit" / "raw-00000001.json").exists())
        self.fixture()
        self.initialize()
        a = snapshot(self.root)
        b = copy.deepcopy(a)
        b[1]["entries"][0]["size"] += 1
        with mock.patch.object(observer, "snapshot", side_effect=[a, b]):
            with self.assertRaises(ObservationError):
                self.instance.record()
        self.assertFalse((self.root / "audit" / "heartbeat.json").exists())
        unavailable = copy.deepcopy(a)
        unavailable[1]["entries"][0]["identity"][1] = 0
        with mock.patch.object(observer, "snapshot", side_effect=[unavailable, unavailable]):
            with self.assertRaisesRegex(ObservationError, "FILE_IDENTITY_UNAVAILABLE"):
                self.instance.record()
        self.assertFalse((self.root / "audit" / "heartbeat.json").exists())
        for proof_kind in ("extension_only", "owner_sid_only", "stale_bound_evidence"):
            with self.subTest(proof=proof_kind):
                self.fixture()
                self.initialize()
                proof = self.add_document()
                if proof_kind == "extension_only":
                    proof = {}
                elif proof_kind == "owner_sid_only":
                    proof = {"general/document.pdf": {"owner_sid": "synthetic-owner"}}
                else:
                    proof["general/document.pdf"]["metadata_sha256"] = "stale"
                # STEP 1-C: pinned noncore scope + addition-only is sufficient;
                # absence of creator evidence is not uncertainty about scope.
                self.record("INVESTIGATE_HOLD" if proof_kind == "stale_bound_evidence"
                            else "ALLOW_RECORDED", proof)
        self.fixture()
        self.initialize()
        self.record("INVESTIGATE_HOLD", self.add_document("not-a-document.exe.pdf"))
        self.fixture()
        self.initialize()
        proof = self.add_document()
        path = self.root / "data" / "protected" / "new-sensitive.pdf"
        path.write_bytes(b"synthetic sensitive addition")
        self.record("INVESTIGATE_HOLD", proof)

    def test_T13_originals_and_baselines_sha_unchanged(self):
        self.assertTrue(all(row["same"] for row in preserved()))
        self.initialize()
        before = file_hash(self.root / "audit" / "baseline.json")
        self.record("ALLOW_RECORDED", self.add_document())
        self.assertEqual(file_hash(self.root / "audit" / "baseline.json"), before)
        self.assertTrue(all(row["same"] for row in preserved()))

    def test_T14_historical_stop_never_reclassified(self):
        historical = self.root / "historical-stop.json"
        exclusive_json(historical, {"classification": "HARD_STOP", "run_id": "old-synthetic-run"})
        before = file_hash(historical)
        self.initialize()
        self.record("ALLOW_RECORDED", self.add_document())
        self.assertEqual(file_hash(historical), before)
        self.assertEqual(load(historical)["classification"], "HARD_STOP")

    def test_T15_source_freeze_originals_unchanged(self):
        self.assertTrue(all(row["same"] for row in preserved()))
        index = next(Path(row["path"]) for row in load(MANIFEST) if Path(row["path"]).name == "index")
        repository = index.parent.parent
        def git(*args):
            return subprocess.check_output(["git", "--no-optional-locks", "-C", str(repository), *args], text=True).strip()
        self.assertEqual(git("branch", "--show-current"), "integration/study-use-final-candidate")
        self.assertEqual(git("rev-parse", "HEAD"), BASE_HEAD)
        self.assertEqual(git("rev-parse", "HEAD^{tree}"), BASE_TREE)
        self.assertEqual(git("status", "--porcelain", "--untracked-files=no"), "")


class ReportResult(unittest.TextTestResult):
    rows = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.rows.append({"test": test._testMethodName, "result": "PASS"})

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.rows.append({"test": test._testMethodName, "result": "FAIL"})

    def addError(self, test, error):
        super().addError(test, error)
        self.rows.append({"test": test._testMethodName, "result": "ERROR"})


def main():
    global MANIFEST
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preservation-manifest", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    MANIFEST = Path(args.preservation_manifest)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Safety)
    result = unittest.TextTestRunner(verbosity=2, failfast=True, resultclass=ReportResult).run(suite)
    preservation = preserved()
    success = result.wasSuccessful() and all(row["same"] for row in preservation)
    report = {"fixture_only": True, "production_activated": False,
              "at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "python": sys.version, "os": os.name, "tests_run": result.testsRun,
              "success": success, "exit_code": 0 if success else 1,
              "failfast": True, "tests": result.rows, "fixtures": FIXTURES,
              "preservation": preservation,
              "failures": [text for _, text in result.failures + result.errors]}
    exclusive_json(Path(args.report), report)
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
