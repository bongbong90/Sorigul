"""C01/C05 focused fixtures followed by the complete STEP 1-A regression, fail-fast."""
from __future__ import annotations

import argparse
import copy
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest import mock

import observer_v2 as observer
import runner_v2 as runner
import test_step1a as prior
from observer_v2 import ObservationError, encoded, exclusive_json, file_hash, load, snapshot


class Focused(prior.Safety):
    def configure(self, edit):
        baseline = {"run_id": self.run, "snapshot": snapshot(self.root),
                    "fixture_only": True, "scope": observer.fixture_scope()}
        edit(baseline)
        exclusive_json(self.root / "audit" / "baseline.json", baseline)
        self.instance = observer.Observer(self.root, self.run)

    @contextmanager
    def final_observation(self):
        errors = []
        def respond():
            try:
                self.wait_for(lambda: (self.root / "audit" / "FINAL_REQUEST.json").exists())
                request = load(self.root / "audit" / "FINAL_REQUEST.json")
                self.instance.record(final_nonce=request["nonce"])
            except Exception as error:
                errors.append(repr(error))
        worker = threading.Thread(target=respond)
        worker.start()
        try:
            yield
        finally:
            worker.join(timeout=6)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])

    def assert_no_completion(self, result):
        self.assertFalse(result["success"])
        self.assertFalse(result["permit"])
        self.assertEqual(result["runner_exit"], 1)
        self.assertTrue((self.root / "audit" / "STOP.json").exists())
        self.assertTrue((self.root / "audit" / "RUNNER_FAILURE.json").exists())
        gate = runner.Gate(self.root, self.run)
        with self.assertRaises(Exception):
            gate.validate()

    def test_C01_01_one_unknown_actor_extension_independent(self):
        self.initialize()
        # No positive PDF/name/SID rule: arbitrary ordinary noncore file works too.
        self.add_document("ordinary.unknown-format")
        result = self.record("ALLOW_RECORDED")
        self.assertEqual(result["events"][0]["actor"], "UNKNOWN")
        self.assertIn("admission", result["events"][0])
        self.assertEqual(len(load(self.root / "audit" / "state-00000001.json")["admissions"]), 1)
        self.assertEqual(load(self.root / "audit" / "raw-00000001.json")["canonical"]["classification"], "HARD_STOP")

    def test_C01_02_six_unknown_actor_additions(self):
        self.initialize()
        for number in range(6):
            self.add_document(f"ordinary-{number}.pdf")
        self.assertEqual(len(self.record("ALLOW_RECORDED")["events"]), 6)
        self.record("NO_CHANGE")
        self.assertEqual(len(load(self.root / "audit" / "state-00000002.json")["admissions"]), 6)

    def test_C01_03_mixed_mp3_and_normal_addition(self):
        self.initialize()
        self.add_document()
        (self.root / "data" / "protected" / "clip.mp3").write_bytes(b"changed")
        self.record("HARD_STOP")

    def test_C01_04_admitted_modify_and_delete(self):
        for action in ("modify", "delete"):
            with self.subTest(action=action):
                self.fixture()
                self.initialize()
                self.add_document()
                self.record("ALLOW_RECORDED")
                path = self.root / "data" / "general" / "document.pdf"
                if action == "delete":
                    path.unlink()
                else:
                    path.write_bytes(b"changed")
                self.record("HARD_STOP")

    def test_C01_05_sensitive_registered_audio_and_missing_contract(self):
        cases = ("sensitive", "registered", "audio", "missing_scope", "isolation", "incomplete")
        for case in cases:
            with self.subTest(case=case):
                self.fixture()
                def edit(b):
                    if case == "registered":
                        b["scope"]["registered_paths"] = ["general/document.pdf"]
                    elif case == "missing_scope":
                        b.pop("scope")
                    elif case == "isolation":
                        b["scope"]["isolation_intact"] = None
                    elif case == "incomplete":
                        b["scope"]["observation_complete"] = False
                self.configure(edit)
                self.add_document("new-audio.mp3" if case == "audio" else "document.pdf")
                if case == "sensitive":
                    (self.root / "data" / "protected" / "another.pdf").write_bytes(b"synthetic")
                self.record("INVESTIGATE_HOLD")

    def test_C01_06_collision_reparse_and_incomplete_snapshot(self):
        self.initialize()
        original = snapshot(self.root)
        collision = copy.deepcopy(original)
        collision[1]["entries"].append(copy.deepcopy(collision[1]["entries"][0]))
        with mock.patch.object(observer, "snapshot", return_value=collision):
            with self.assertRaisesRegex(ObservationError, "AMBIGUOUS_PATH_IDENTITY"):
                self.instance.record()
        self.assertFalse((self.root / "audit" / "heartbeat.json").exists())
        with mock.patch.object(observer, "snapshot", return_value=original[:-1]):
            with self.assertRaisesRegex(ObservationError, "ROOT_SET_CHANGED"):
                self.instance.record()
        self.add_document()
        reparse = snapshot(self.root)
        reparse[0]["entries"][0]["reparse"] = True
        with mock.patch.object(observer, "snapshot", return_value=reparse):
            self.record("INVESTIGATE_HOLD")

    def test_C05_01_positive_sealed_completion(self):
        self.initialize().record()
        with self.final_observation():
            result = runner.run_guarded(self.root, self.run, self.command())
        self.assertTrue(result["success"])
        self.assertEqual(result["runner_exit"], 0)
        gate = runner.Gate(self.root, self.run)
        with observer.journal_lock(gate.audit):
            self.assertTrue(runner.verify_completion(gate, gate._validate(None, None, None))["success"])

    def test_C05_02_stop_after_nonce_before_finalization(self):
        self.initialize().record()
        original = runner.finalize
        def inject(gate, *args):
            observer.latch_stop(gate.audit, self.run, "AFTER_FINAL_NONCE")
            return original(gate, *args)
        with self.final_observation(), mock.patch.object(runner, "finalize", side_effect=inject):
            result = self.denied()
        self.assert_no_completion(result)
        self.assertFalse((self.root / "audit" / "COMPLETION.json").exists())

    def test_C05_03_stop_during_candidate_and_completion_publication(self):
        for target in ("RUNNER_RESULT.json", "COMPLETION.json"):
            with self.subTest(target=target):
                self.fixture()
                self.initialize().record()
                original = runner.publish_json
                def inject(path, value):
                    original(path, value)
                    if path.name == target:
                        observer.latch_stop(path.parent, self.run, "DURING_PUBLICATION")
                with self.final_observation(), mock.patch.object(runner, "publish_json", side_effect=inject):
                    result = self.denied()
                self.assert_no_completion(result)

    def test_C05_04_result_save_failure_and_partial_stage(self):
        for mode in ("before_save", "partial_stage", "completion_save"):
            with self.subTest(mode=mode):
                self.fixture()
                self.initialize().record()
                original = runner.publish_json
                def inject(path, value):
                    target = "COMPLETION.json" if mode == "completion_save" else "RUNNER_RESULT.json"
                    if path.name == target:
                        if mode == "partial_stage":
                            (path.parent / "injected.partial").write_bytes(b'{"success":tr')
                        raise OSError("SYNTHETIC_STORAGE_FAILURE")
                    return original(path, value)
                with self.final_observation(), mock.patch.object(runner, "publish_json", side_effect=inject):
                    result = self.denied()
                self.assert_no_completion(result)
                self.assertFalse((self.root / "audit" / "COMPLETION.json").exists())

    def test_C05_05_post_nonce_mutation_and_stale_replay(self):
        for mode in ("mutation", "replay"):
            with self.subTest(mode=mode):
                self.fixture()
                self.initialize().record()
                old = load(self.root / "audit" / "heartbeat.json")
                original = runner.finalize
                def inject(gate, *args):
                    if mode == "mutation":
                        (self.root / "data" / "protected" / "clip.mp3").write_bytes(b"late modification")
                    else:
                        observer.atomic_pointer(gate.audit / "heartbeat.json", old)
                    return original(gate, *args)
                with self.final_observation(), mock.patch.object(runner, "finalize", side_effect=inject):
                    result = self.denied()
                self.assert_no_completion(result)

    def test_C05_06_cleanup_failure_is_nonzero(self):
        self.initialize().record()
        with self.final_observation(), mock.patch.object(runner, "stop_owned", side_effect=OSError("SYNTHETIC_CLEANUP_FAILURE")):
            result = self.denied()
        self.assert_no_completion(result)
        self.assertIn("CLEANUP_FAILED", result["reason"])

    def test_C05_07_watcher_rejects_result_existence_only(self):
        exclusive_json(self.root / "audit" / "baseline.json", {
            "run_id": self.run, "snapshot": snapshot(self.root), "fixture_only": True,
            "scope": observer.fixture_scope()})
        import subprocess
        watcher = subprocess.Popen([sys.executable, "-B", str(prior.TOOLS / "observer_v2.py"),
                                   "--fixture", str(self.root), "--run-id", self.run],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.processes.append(watcher)
        self.wait_for(lambda: (self.root / "audit" / "heartbeat.json").exists() or watcher.poll() is not None)
        self.assertIsNone(watcher.poll())
        observer.publish_json(self.root / "audit" / "FINAL_REQUEST.json", {
            "run_id": self.run, "nonce": "1" * 32, "at": time.time(), "after_sequence": 1})
        exclusive_json(self.root / "audit" / "RUNNER_RESULT.json", {"success": True})
        self.wait_for(lambda: load(self.root / "audit" / "heartbeat.json").get("final_nonce") == "1" * 32 or watcher.poll() is not None)
        self.assertIsNone(watcher.poll())
        observer.latch_stop(self.root / "audit", self.run, "RESULT_EXISTENCE_IS_NOT_COMPLETION")
        self.assertNotEqual(watcher.wait(timeout=4), 0)


def process_io():
    if os.name != "nt":
        return {"available": False}
    class Counters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "read_operations", "write_operations", "other_operations",
            "read_transfer_bytes", "write_transfer_bytes", "other_transfer_bytes")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessIoCounters.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters)]
    counters = Counters()
    if not kernel.GetProcessIoCounters(kernel.GetCurrentProcess(), ctypes.byref(counters)):
        raise OSError(ctypes.get_last_error(), "GetProcessIoCounters")
    return {name: getattr(counters, name) for name, _ in counters._fields_}


class Result(prior.ReportResult):
    rows = []
    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err:
            self.rows.append({"test": str(subtest), "result": "FAIL"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preservation-manifest", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    prior.MANIFEST = Path(args.preservation_manifest)
    io_before, times_before, wall_before = process_io(), os.times(), time.perf_counter()
    focused = unittest.TestSuite(Focused(name) for name in sorted(Focused.__dict__) if name.startswith("test_"))
    regression = unittest.defaultTestLoader.loadTestsFromTestCase(prior.Safety)
    result = unittest.TextTestRunner(verbosity=2, failfast=True, resultclass=Result).run(
        unittest.TestSuite([focused, regression]))
    wall, times_after, io_after = time.perf_counter() - wall_before, os.times(), process_io()
    preservation = prior.preserved()
    success = result.wasSuccessful() and all(row["same"] for row in preservation)
    report = {"fixture_only": True, "production_activated": False, "tests_run": result.testsRun,
              "success": success, "exit_code": 0 if success else 1, "failfast": True,
              "tests": result.rows, "fixtures": prior.FIXTURES, "preservation": preservation,
              "failures": [text for _, text in result.failures + result.errors],
              "python": sys.version, "metrics": {
                  "suite_wall_seconds": wall,
                  "host_user_cpu_seconds": times_after.user - times_before.user,
                  "host_kernel_cpu_seconds": times_after.system - times_before.system,
                  "host_io_delta": {key: io_after[key] - io_before[key] for key in io_before},
                  "scope": "Test host only; children excluded. Windows process I/O includes cached/file/device I/O, not physical disk. Includes preservation read hashes. Small fixtures only; NOT operational performance PASS."}}
    exclusive_json(Path(args.report), report)
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
