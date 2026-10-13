"""Compare two suite runs case by case, e.g. the same suite on two harness builds.

usage: python3 tools/compare_builds.py <results dir A> <results dir B>

Each directory must hold the fx_suite.json written by tools/nudge_probe.py. For every case present in A, prints the
fields that differ in B (receiver sequence, continuation count, verification result, patch hash, unmatched stub
requests, model requests and the first line of the harness error), then the number of identical cases.
"""

import json
import sys
from pathlib import Path


def load(d: str) -> dict:
    rows = json.loads((Path(d) / "fx_suite.json").read_text())
    out = {}
    for r in rows:
        out[r["name"]] = {"receivers": [q["agent"] for q in r["requests"]], "nudges": r["nudges"],
                          "resolved": r["resolved"], "patch_sha8": r["patch_sha8"] or "-",
                          "unmatched_requests": r.get("unmatched_requests", 0), "llm_calls": r.get("llm_calls"),
                          "error": (r.get("error") or "").splitlines()[0][:100] if r.get("error") else ""}
    return out


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    a, b = load(sys.argv[1]), load(sys.argv[2])
    same = 0
    for name, ra in a.items():
        rb = b.get(name)
        if rb is None:
            print(f"{name}: missing from {sys.argv[2]}")
            continue
        keys = [k for k in ra if ra[k] != rb[k]]
        if not keys:
            same += 1
            continue
        print(name)
        for k in keys:
            print(f"  {k}: {ra[k]} -> {rb[k]}")
    print(f"\n{same} of {len(a)} cases identical")


if __name__ == "__main__":
    main()
