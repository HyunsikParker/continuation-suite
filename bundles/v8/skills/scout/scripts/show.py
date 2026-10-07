"""Print the source of a function, method or class with line numbers.

Usage: show.py --name NAME [--path FILE]
NAME may be `func`, `Class` or `Class.method`. Line numbers match read_file, so the
text after the tab can be copied into edit_file's old_string. Read-only.
"""

import argparse
import ast
import os
import re

SKIP_DIRS = {
    ".git", ".hg", ".venv", "venv", "env", "build", "dist", "node_modules", "__pycache__",
    ".tox", ".nox", ".eggs", "site-packages", ".mypy_cache", ".pytest_cache",
}


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
    return bool(re.search(r"(^|/)(tests?|testing)(/|$)", rel)) or name.startswith("test_") or name == "conftest.py"


def candidates(root, path):
    if path:
        p = path[len("/workspace/"):] if path.startswith("/workspace/") else path.lstrip("/")
        full = os.path.join(root, p)
        if os.path.isfile(full):
            yield full, p
            return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                full = os.path.join(dirpath, fn)
                yield full, os.path.relpath(full, root)


def find(root, name, path):
    want = name.strip().strip("`").replace("()", "")
    parts = want.split(".")
    hits = []
    for full, rel in candidates(root, path):
        try:
            with open(full, encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError:
            continue
        if parts[-1] not in src:
            continue
        try:
            tree = ast.parse(src)
        except (SyntaxError, ValueError):
            continue

        def visit(node, prefix):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    qual = f"{prefix}.{child.name}" if prefix else child.name
                    if qual == want or qual.endswith("." + want) or (len(parts) == 1 and child.name == want):
                        start = child.lineno
                        if child.decorator_list:
                            start = min([start] + [d.lineno for d in child.decorator_list])
                        hits.append((rel, qual, start, child.end_lineno or start, src))
                    visit(child, qual)

        visit(tree, "")
    hits.sort(key=lambda h: (is_test(h[0]), "docs" in h[0], len(h[0])))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--path", default="")
    args = ap.parse_args()
    root = workspace()
    hits = find(root, args.name, args.path)
    if not hits:
        print(f"No definition named {args.name!r} found. Try locate.py, or grep -rn \"def {args.name.split('.')[-1]}\" --include=*.py .")
        return
    rel, qual, start, end, src = hits[0]
    lines = src.splitlines()
    total = end - start + 1
    print(f"{rel}:{start}-{end}  {qual}  ({total} lines)")
    if total <= 140:
        rng = list(range(start, end + 1))
    else:
        rng = list(range(start, start + 100)) + [None] + list(range(end - 29, end + 1))
    out = []
    for ln in rng:
        if ln is None:
            out.append(f"   ... lines {start + 100}-{end - 30} omitted; use read_file with a line range ...")
        else:
            out.append(f"{ln:6d}\t{lines[ln - 1]}")
    text = "\n".join(out)
    print(text if len(text) <= 9000 else text[:8980] + "\n...[truncated]")
    if len(hits) > 1:
        print("Other matches: " + "; ".join(f"{r}:{s} {q}" for r, q, s, _, _ in hits[1:8]))


if __name__ == "__main__":
    main()
