"""Compile changed files, then run targeted tests with the grader's pytest flags.

Usage: check.py [--files "a.py,b.py"] [--tests "tests/test_x.py tests/test_y.py::test_z"] [--k EXPR]
Without --files it compiles every Python file changed against git HEAD.
Prints a short verdict, failing test ids and the end of the output. Never edits files.
"""

import argparse
import os
import py_compile
import re
import subprocess


def workspace():
    import sys
    cands = [os.environ.get("SWE_WORKSPACE"), "/workspace"]
    argv = getattr(sys, "orig_argv", [])
    if len(argv) > 1 and argv[1].endswith(".py"):
        cands.append(os.path.dirname(os.path.abspath(argv[1])))
    cands += [os.environ.get("PWD"), os.getcwd()]
    for cand in cands:
        if cand and os.path.isdir(os.path.join(cand, ".git")):
            return cand
    return "/workspace"


def changed_files(root):
    try:
        out = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=root, capture_output=True, text=True, timeout=30).stdout
        new = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=root, capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return []
    return [f for f in (out + new).split() if f.endswith(".py")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", default="")
    ap.add_argument("--tests", default="")
    ap.add_argument("--k", default="")
    ap.add_argument("--timeout", default="200")
    args = ap.parse_args()
    root = workspace()
    files = [f.strip() for f in re.split(r"[,\s]+", args.files) if f.strip()] or changed_files(root)
    report = []
    ok = True
    for f in files[:20]:
        rel = f[len("/workspace/"):] if f.startswith("/workspace/") else f.lstrip("/")
        full = os.path.join(root, rel)
        if not os.path.isfile(full):
            report.append(f"compile {rel}: MISSING")
            ok = False
            continue
        try:
            py_compile.compile(full, doraise=True)
            report.append(f"compile {rel}: ok")
        except py_compile.PyCompileError as exc:
            ok = False
            report.append(f"compile {rel}: FAILED\n{str(exc)[-600:]}")
    if not files:
        report.append("compile: no changed Python files (did the edit apply?)")

    targets = [t for t in re.split(r"\s+", args.tests.strip()) if t]
    if targets:
        cmd = ["python3", "-m", "pytest", *targets, "-p", "no:anyio", "-o", "timeout=0",
               "-o", "norecursedirs=.* build dist venv", "-o", "python_classes=Test* *Test",
               "-q", "-x", "--no-header", "-rf", "-p", "no:cacheprovider"]
        if args.k:
            cmd += ["-k", args.k]
        env = dict(os.environ, PYTHONSAFEPATH="1", PYTHONDONTWRITEBYTECODE="1")
        try:
            limit = max(20, min(280, int(args.timeout)))
        except ValueError:
            limit = 200
        try:
            proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=limit, env=env)
            text = (proc.stdout or "") + (proc.stderr or "")
            code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            text = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            code = -1
            report.append(f"pytest: TIMEOUT after {limit}s; run fewer tests (one file or -k).")
        summary = [ln for ln in text.splitlines() if re.search(r"\b(passed|failed|error|errors|no tests ran)\b", ln)]
        failed = [ln.split(" ", 1)[1] for ln in text.splitlines() if ln.startswith(("FAILED ", "ERROR "))]
        verdict = "PASS" if code == 0 else ("NO TESTS" if code == 5 else "FAIL")
        if code not in (0, 5):
            ok = False
        report.append(f"pytest {' '.join(targets)}: {verdict} (exit {code}) {summary[-1].strip() if summary else ''}")
        if failed:
            report.append("failing: " + "; ".join(f[:150] for f in failed[:8]))
        if code not in (0, 5) and re.search(r"ERROR at setup|fixture '[^']+' not found|ModuleNotFoundError: No module named '(pytest_|httpbin|trustme)", text):
            report.append("note: setup/fixture errors usually come from the offline test environment, not from your change; prefer other tests or a /tmp reproduction.")
        if code not in (0, 5):
            tail = "\n".join(text.splitlines()[-30:])
            report.append("--- output tail ---\n" + tail[-2500:])
    report.append("VERDICT: " + ("OK" if ok else "PROBLEMS FOUND"))
    out = "\n".join(report)
    print(out if len(out) <= 4000 else out[:3980] + "\n...[truncated]")


if __name__ == "__main__":
    main()
