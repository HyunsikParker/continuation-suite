"""List existing test files and test functions that mention a name.

Usage: tests.py --name NAME
Prints up to 12 test files ranked by mentions, with up to 4 matching test functions each,
as ready-to-run pytest targets. Read-only.
"""

import argparse
import os
import re

SKIP_DIRS = {".git", ".venv", "venv", "env", "build", "dist", "node_modules", "__pycache__", ".tox", ".nox", "site-packages"}


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


def is_test(rel):
    rel = rel.replace(os.sep, "/").lower()
    name = rel.rsplit("/", 1)[-1]
    return bool(re.search(r"(^|/)(tests?|testing)(/|$)", rel)) or name.startswith("test_") or name.endswith("_test.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    args = ap.parse_args()
    root = workspace()
    name = args.name.strip().strip("`").replace("()", "").split(".")[-1]
    if len(name) < 2:
        print("Give a longer name.")
        return
    pat = re.compile(r"\b" + re.escape(name) + r"\b")
    results = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            if not is_test(rel):
                continue
            try:
                with open(full, encoding="utf-8", errors="replace") as fh:
                    src = fh.read()
            except OSError:
                continue
            hits = len(pat.findall(src))
            if not hits:
                continue
            funcs = []
            current = None
            klass = None
            for line in src.splitlines():
                m = re.match(r"^class (Test\w*)", line)
                if m:
                    klass = m.group(1)
                m = re.match(r"^(\s*)(?:async\s+)?def (test\w*)", line)
                if m:
                    current = (f"{klass}::{m.group(2)}" if (m.group(1) and klass) else m.group(2))
                    if not m.group(1):
                        klass = None
                if current and pat.search(line) and current not in funcs:
                    funcs.append(current)
            results.append((hits, rel, funcs))
    if not results:
        print(f"No test file mentions {name!r}. Look for tests of the module instead: ls tests | head")
        return
    results.sort(key=lambda r: -r[0])
    print(f"Test files mentioning {name!r} (mentions, file, tests):")
    for hits, rel, funcs in results[:12]:
        shown = ", ".join(f"{rel}::{f}" for f in funcs[:4])
        more = f" (+{len(funcs) - 4} more)" if len(funcs) > 4 else ""
        print(f"  {hits:3d}  {rel}" + (f"\n       {shown}{more}" if shown else ""))
    print("Run a file or test id with check.py --tests '<target>' (space-separate several).")


if __name__ == "__main__":
    main()
