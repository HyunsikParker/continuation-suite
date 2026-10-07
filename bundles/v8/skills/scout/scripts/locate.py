"""Rank the source functions and classes most related to an issue text.

Usage: locate.py --query "<issue text>" [--top 8]
Prints ranked definitions (path:start-end, kind, qualified name) and exact-text hits.
Read-only; prints at most about 3,500 characters.
"""

import argparse
import ast
import math
import os
import re
from collections import Counter

SKIP_DIRS = {
    ".git", ".hg", ".venv", "venv", "env", "build", "dist", "node_modules", "__pycache__",
    ".tox", ".nox", ".eggs", "site-packages", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}
STOP = set(
    """a an and are as at be been but by can could do does did for from has have how i if in into
    is it its may might must no not of on or our should so than that the then there these this those
    to too use used uses using was we were what when where which while who will with would you your
    issue bug fix fixes fixed feature request add adds added support allow allows expected actual
    behavior behaviour return returns returned none true false self cls def class import from print
    error exception example code version python following like also only just get set new now see
    want need please thanks thank currently would should work works working""".split()
)
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CAMEL = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")


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
    return bool(re.search(r"(^|/)(tests?|testing)(/|$)", rel)) or name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def is_aux(rel):
    rel = rel.replace(os.sep, "/").lower()
    return bool(re.search(r"(^|/)(docs?|docs_src|examples?|benchmarks?)(/|$)", rel))


def split_ident(word):
    out = []
    low = word.lower()
    if low not in STOP and len(low) > 1:
        out.append(low)
    parts = []
    for chunk in word.split("_"):
        parts.extend(p.lower() for p in CAMEL.findall(chunk))
    if len(parts) > 1:
        out.extend(p for p in parts if len(p) > 2 and p not in STOP)
    return out


def tokens(text):
    out = []
    for word in IDENT.findall(text):
        out.extend(split_ident(word))
    return out


def iter_files(root):
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info") and not os.path.islink(os.path.join(dirpath, d)))
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            if os.path.islink(full) or is_test(rel):
                continue
            try:
                if os.path.getsize(full) > 400_000:
                    continue
            except OSError:
                continue
            n += 1
            if n > 5000:
                return
            yield full, rel


def definitions(source, rel):
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    lines = source.splitlines()
    found = []
    # Module-level code (constants, regexes, registries) as one pseudo-definition.
    top = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expr, ast.If, ast.Try)):
            s, e = node.lineno, getattr(node, "end_lineno", node.lineno) or node.lineno
            top.append("\n".join(lines[s - 1:min(e, s + 30)]))
    if top:
        mod = rel[:-3].replace(os.sep, "/").replace("/", ".")
        found.append((mod + " (module level)", mod.rsplit(".", 1)[-1], "module", 1, len(lines), "\n".join(top)[:20000]))

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = f"{prefix}.{child.name}" if prefix else child.name
                start = getattr(child, "lineno", 1)
                if getattr(child, "decorator_list", None):
                    start = min([start] + [d.lineno for d in child.decorator_list])
                end = getattr(child, "end_lineno", start) or start
                body = "\n".join(lines[start - 1:end]) if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else "\n".join(lines[start - 1:min(end, start + 40)])
                kind = "class" if isinstance(child, ast.ClassDef) else "def"
                found.append((qual, child.name, kind, start, end, body))
                visit(child, qual)

    visit(tree, "")
    return found


def query_parts(query):
    quoted = set()
    for pat in (r"`([^`\n]{3,80})`", r"'([^'\n]{4,80})'", r"\"([^\"\n]{4,80})\""):
        for m in re.findall(pat, query):
            quoted.add(m.strip())
    idents = set()
    for w in IDENT.findall(query):
        if len(w) > 3 and ("_" in w or any(c.isupper() for c in w[1:])):
            idents.add(w)
    for m in re.findall(r"\b([A-Za-z_][\w]*(?:\.[A-Za-z_]\w*)+)\b", query):
        for part in m.split("."):
            if len(part) > 2:
                idents.add(part)
    paths = set(re.findall(r"[\w./-]+\.py\b", query))
    errors = set(m.strip() for m in re.findall(r"(?:Error|Exception|Warning)[:]\s*([^\n]{6,120})", query))
    return quoted, idents, paths, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--top", default="12")
    args = ap.parse_args()
    top = max(3, min(15, int(args.top))) if str(args.top).isdigit() else 12
    root = workspace()
    query = args.query[:8000]
    q_tokens = tokens(query)
    q_count = Counter(q_tokens)
    quoted, idents, paths, errors = query_parts(query)
    ident_low = {i.lower() for i in idents}

    docs = []  # (rel, qual, name, kind, start, end, tf, length, body)
    df = Counter()
    file_text = {}
    for full, rel in iter_files(root):
        try:
            with open(full, encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError:
            continue
        file_text[rel] = src
        path_toks = tokens(rel[:-3].replace(os.sep, " ").replace("/", " "))
        for qual, name, kind, start, end, body in definitions(src, rel):
            toks = tokens(qual) * 3 + path_toks * 2 + tokens(body)
            tf = Counter(toks)
            for t in set(toks) & set(q_count):
                df[t] += 1
            docs.append((rel, qual, name, kind, start, end, tf, max(1, len(toks)), body))

    if not docs:
        print(f"No Python definitions found under {root}.")
        return
    n_docs = len(docs)
    avg_len = sum(d[7] for d in docs) / n_docs
    scored = []
    for rel, qual, name, kind, start, end, tf, length, body in docs:
        s = 0.0
        for t, qn in q_count.items():
            f = tf.get(t, 0)
            if not f:
                continue
            idf = math.log(1 + (n_docs - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * (f * 2.2) / (f + 1.2 * (0.25 + 0.75 * length / avg_len)) * min(qn, 3)
        nl = name.lower()
        if nl in ident_low:
            s += 12.0
        if qual.lower() in ident_low:
            s += 6.0
        for q in quoted:
            if len(q) >= 4 and q in body:
                s += 4.0
        for e in errors:
            if e[:40] and e[:40] in body:
                s += 8.0
        if any(rel.endswith(p.lstrip("./")) for p in paths):
            s += 5.0
        if is_aux(rel):
            s *= 0.45
        if name.startswith("__") and name.endswith("__") and nl not in ident_low:
            s *= 0.8
        if s > 0:
            scored.append((s, rel, qual, kind, start, end))

    scored.sort(key=lambda x: -x[0])
    out = [f"workspace: {root}  ({len(file_text)} source files, {n_docs} definitions)"]
    out.append("Top definitions (score  path:start-end  kind name):")
    for s, rel, qual, kind, start, end in scored[:top]:
        out.append(f"  {s:6.1f}  {rel}:{start}-{end}  {kind} {qual}")
    files = Counter()
    for s, rel, *_ in scored[:40]:
        files[rel] += s
    if files:
        out.append("Top files: " + ", ".join(f"{r} ({v:.0f})" for r, v in files.most_common(8)))

    needles = [q for q in quoted if len(q) >= 5][:8] + [e[:60] for e in errors][:4]
    if needles:
        out.append("Exact-text hits in source (not tests):")
        shown = 0
        ordered = sorted(file_text.items(), key=lambda kv: (is_aux(kv[0]), kv[0]))
        for needle in needles:
            per_needle = 0
            for rel, src in ordered:
                if per_needle >= 3:
                    break
                if needle not in src:
                    continue
                for i, line in enumerate(src.splitlines(), 1):
                    if needle in line:
                        out.append(f"  {rel}:{i}: {line.strip()[:120]}   <- {needle[:40]!r}")
                        shown += 1
                        per_needle += 1
                        break
                if shown >= 12:
                    break
            if shown >= 12:
                break
        if shown == 0:
            out.append("  none")
    out.append("Next: show.py --name <qualified name> to read one definition with line numbers.")
    text = "\n".join(out)
    print(text if len(text) <= 3500 else text[:3480] + "\n...[truncated]")


if __name__ == "__main__":
    main()
