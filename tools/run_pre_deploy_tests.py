#!/usr/bin/env python3
"""Pre-deploy test gate.

Runs the per-image parser/solver unit tests.  On any failure it writes a
record to ``test-results/`` (a machine-readable JSON and a human-readable
Markdown summary) and prints a summary to the console.  Exit status is
non-zero when anything failed, so callers (the ``pre-push`` git hook,
``tools/deploy.py``) can abort the deployment.

    python tools/run_pre_deploy_tests.py
"""
import datetime as _dt
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "test-results")


def _run_pytest(junit_path: str) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q",
         "--junit-xml", junit_path, "--tb=short"],
        cwd=ROOT,
    )
    return proc.returncode


def _parse_junit(junit_path: str):
    """Return ``(passed, failures)`` from a JUnit XML report."""
    tree = ET.parse(junit_path)
    passed, failures = 0, []
    for case in tree.iter("testcase"):
        name = f"{case.get('classname')}::{case.get('name')}"
        bad = case.find("failure")
        if bad is None:
            bad = case.find("error")
        if bad is None:
            passed += 1
        else:
            failures.append({
                "test": name,
                "message": (bad.get("message") or "").strip(),
                "detail": (bad.text or "").strip(),
            })
    return passed, failures


def _write_record(passed: int, failures: list, stamp: str) -> str:
    os.makedirs(RESULTS, exist_ok=True)
    total = passed + len(failures)

    record = {
        "timestamp": stamp,
        "total": total,
        "passed": passed,
        "failed": len(failures),
        "failures": failures,
    }
    with open(os.path.join(RESULTS, "latest.json"), "w") as fh:
        json.dump(record, fh, indent=2)

    lines = [
        f"# Pre-deploy test report — {stamp}",
        "",
        f"- total: **{total}**",
        f"- passed: **{passed}**",
        f"- failed: **{len(failures)}**",
        "",
    ]
    if failures:
        lines.append("## Failures")
        lines.append("")
        for f in failures:
            lines.append(f"### `{f['test']}`")
            lines.append("")
            if f["message"]:
                lines.append(f"- {f['message']}")
            if f["detail"]:
                lines.append("")
                lines.append("```")
                lines.append(f["detail"])
                lines.append("```")
            lines.append("")
    else:
        lines.append("All tests passed. ✅")
        lines.append("")
    md_path = os.path.join(RESULTS, "latest.md")
    with open(md_path, "w") as fh:
        fh.write("\n".join(lines))

    # also keep a timestamped copy of any failing run for the audit trail
    if failures:
        safe = stamp.replace(":", "").replace(" ", "_")
        with open(os.path.join(RESULTS, f"failures-{safe}.md"), "w") as fh:
            fh.write("\n".join(lines))
    return md_path


def main() -> int:
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    junit = os.path.join(RESULTS, "junit.xml")
    os.makedirs(RESULTS, exist_ok=True)

    print("[pre-deploy] running parser + solver unit tests …")
    _run_pytest(junit)

    if not os.path.exists(junit):
        print("[pre-deploy] ERROR: pytest produced no report — aborting.")
        return 1

    passed, failures = _parse_junit(junit)
    md_path = _write_record(passed, failures, stamp)

    print("\n" + "=" * 60)
    if failures:
        print(f"[pre-deploy] {len(failures)} TEST(S) FAILED "
              f"({passed} passed) — deployment should not proceed.")
        for f in failures:
            print(f"  ✗ {f['test']}")
            if f["message"]:
                print(f"      {f['message'].splitlines()[0][:90]}")
        print(f"\n  failure record saved to: {md_path}")
        print("=" * 60)
        return 1

    print(f"[pre-deploy] all {passed} tests passed — safe to deploy.")
    print(f"  report saved to: {md_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
