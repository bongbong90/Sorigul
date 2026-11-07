"""QA-only fault injection. Copies sources, never modifies the reviewed tree.

Runs local compile/model/disposable-filesystem tests only. No worker launch,
GitHub access, installer, product or user installation access.
"""
import os
from pathlib import Path
import shutil
import subprocess
import uuid

HERE = Path(__file__).resolve().parent
MUTANTS = [
    ("production-deny", "Contract.cs", "MISSING", "MISSING"),  # replaced below
    ("schema-mutation", "ResultContract.cs", "return (EvidenceSpec[])evidence.Clone();", "return evidence;"),
    ("reparse-ignored", "runtime/Containment.cs", "(info.Attributes & Reparse) != 0", "false"),
    ("existing-root-adopted", "runtime/Containment.cs", "IntPtr.Zero, 16, 1, 2, 0x00200021", "IntPtr.Zero, 16, 1, 3, 0x00200021"),
    ("late-pass", "ResultContract.cs", "if (frozen) { late++; return false; }", "if (frozen && id == null) { late++; return false; }"),
    ("blocking-cleanup", "runtime/BoundedSupervisor.cs", "ThreadPool.QueueUserWorkItem(delegate { try { worker.ForceCleanup(); } catch { } });", "worker.ForceCleanup();"),
    ("endpoint-failure-zero", "runtime/Endpoints.cs", "new EndpointCounts(Verdict.NOT_VERIFIED, null, null)", "new EndpointCounts(Verdict.PASS, 0, 0)"),
    ("missed-child", "runtime/ProcessOwnership.cs", "total == known", "total >= known"),
]
MUTANTS[0] = ("production-deny", "ContextGate.cs", 'outcome.Add("EXTERNAL_CONTROL_NOT_IMPLEMENTED");', "// mutation removes production denial")


def main():
    shell = Path(os.environ["WINDIR"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    failures = 0
    for name, relative, before, after in MUTANTS:
        work = HERE / ("qa59-mutation-" + uuid.uuid4().hex)
        try:
            shutil.copytree(HERE, work, ignore=shutil.ignore_patterns("qa59-build-*", "qa59-mutation-*", "__pycache__"))
            target = work / relative
            source = target.read_text(encoding="utf-8-sig")
            if before not in source:
                raise RuntimeError("MUTATION_TARGET_MISSING")
            target.write_text(source.replace(before, after), encoding="utf-8")
            result = subprocess.run([str(shell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                     str(work / "Invoke-RuntimeTests.ps1"), "-Containment"],
                                    cwd=work, capture_output=True, timeout=45)
            caught = result.returncode != 0 and b"RUNTIME checks=" in result.stdout
            # A compile error is not counted as a killed behavioral mutation.
            print("MUTATION", name, "CAUGHT" if caught else "FAIL")
            if not caught:
                failures += 1
        finally:
            # Checked absolute QA-only target. Refuse reparse content; no shell
            # path interpolation or cross-shell filesystem deletion.
            if work.exists():
                if work.parent.resolve() != HERE or not work.name.startswith("qa59-mutation-"):
                    raise RuntimeError("MUTATION_CLEANUP_DENIED")
                for entry in work.rglob("*"):
                    if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
                        raise RuntimeError("MUTATION_REPARSE_CLEANUP_DENIED")
                shutil.rmtree(work)
    print("MUTATIONS", len(MUTANTS), "failed=" + str(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
