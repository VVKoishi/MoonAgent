"""
Test runner for moon-task examples.
Usage:  python test_examples.py
"""
import subprocess
import sys
import os
import pathlib

ROOT     = pathlib.Path(__file__).parent.parent
RUNNER   = pathlib.Path(__file__).parent / "task_runner.py"
EXAMPLES = ROOT / "examples"

# ─── Example file tests ───────────────────────────────────────────────────────

FILE_TESTS = [
    {
        "name": "hello-world",
        "file": EXAMPLES / "hello-world.TASK.md",
        "expect": ["stop", "Hello！你在", "BRANCH_MSG", "LAST_* 验证通过"],
        "reject": ["TASK_FAIL", "fail: "],
    },
    {
        "name": "lunar-mission",
        "file": EXAMPLES / "lunar-mission.TASK.md",
        # TASK_STOP always fires (void / final-report); BAD-END path triggers TASK_FAIL
        # so allow_fail=True: exit code 1 is valid when structural failure occurs
        "expect": ["stop"],
        "reject": ["此格不应执行"],
        "allow_fail": True,
    },
]


# ─── Test executor ────────────────────────────────────────────────────────────

def run_test(t: dict) -> bool:
    cmd = [sys.executable, str(RUNNER), str(t["file"])]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", env={**os.environ})
    combined = result.stdout + result.stderr
    errors = []

    for s in t.get("expect", []):
        if s not in combined:
            errors.append(f"  ✗ MISSING: {s!r}")
    for s in t.get("reject", []):
        if s in combined:
            errors.append(f"  ✗ FOUND:   {s!r}")
    if result.returncode != 0 and not errors and not t.get("allow_fail"):
        errors.append(f"  ✗ exit code {result.returncode}")

    print(combined.rstrip())
    ok = not errors
    rc_hint = f"  (rc={result.returncode})" if result.returncode != 0 else ""
    print(f"\n  {'PASS ✓' if ok else 'FAIL ✗'}  {t['name']}{rc_hint}")
    for e in errors:
        print(e)
    return ok


def main():
    results = [run_test(t) for t in FILE_TESTS]
    passed, total = sum(results), len(results)
    print(f"\n  {passed}/{total} passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
