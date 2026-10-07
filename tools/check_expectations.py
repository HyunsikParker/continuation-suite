"""Executable oracles for the continuation suite: compare observed results with the expected outcomes.

usage: python3 tools/check_expectations.py [--expect probes/expectations.json]

Checks, each printed as PASS/FAIL (exit status 1 if any check fails):
  cases     per case in results/fx_suite.json: receiver sequence, number of continuation messages, verification
            result and patch hash, against probes/expectations.json
  history   results/requests_state_fixer_{none,default}.jsonl (if present): markers in the fixer's request after the
            continuation message
  render    results/render_31b_vs_12b.jsonl (if present): reasoning markers rendered for every saved render (31B and 12B
            templates, all diagnostics, and the thinking-off control)
  stub      no request may reach an agent the stage-keyed script does not name (counted per case)
  autogen   results/autogen_rr.json (if present): model-request order and saved next_speaker_index per scenario
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"


def check(name: str, ok: bool, detail: str, failures: list) -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        failures.append(name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", default=str(ROOT / "probes" / "expectations.json"))
    args = ap.parse_args()
    exp = json.loads(Path(args.expect).read_text())
    failures: list = []

    observed = {r["name"]: r for r in json.loads((RES / "fx_suite.json").read_text())}
    for name, e in exp["cases"].items():
        r = observed.get(name)
        if r is None:
            check(f"cases/{name}", False, "missing from results", failures)
            continue
        got = {"receivers": [q["agent"] for q in r["requests"]], "nudges": r["nudges"], "resolved": r["resolved"],
               "patch_sha8": r["patch_sha8"], "unmatched_requests": r.get("unmatched_requests", 0)}
        diffs = [k for k in e if got.get(k) != e[k]]
        check(f"cases/{name}", not diffs, f"mismatch in {diffs}" if diffs else "", failures)

    markers = {"A": "PLAN-SENTINEL-A", "B": "FIXER-SENTINEL-B", "C": "LOCATOR-AFTER-NUDGE-C",
               "edit": "run_command", "nudge": "Please continue"}
    for setting, want in exp["history"].items():
        log = RES / f"requests_state_fixer_{setting}.jsonl"
        if not log.exists():
            print(f"SKIP  history/{setting}  (no request log; run the suite first)")
            continue
        rows = [json.loads(l) for l in log.read_text().splitlines()]
        fixer = [r for r in rows if r["body"]["messages"][0]["content"].startswith("You fix one issue")]
        after = json.dumps(fixer[2]["body"]["messages"])  # the fixer's first request after the continuation message
        seen = sorted(k for k, v in markers.items() if v in after)
        check(f"history/{setting}", seen == sorted(want), f"seen {seen}", failures)

    rpath = RES / "render_31b_vs_12b.jsonl"
    seen_keys: set = set()
    if rpath.exists():
        for line in rpath.read_text().splitlines():
            d = json.loads(line)
            tmpl = "31B" if "31B" in d["template"] else "12B"
            if "render_skip" in d["log"]:
                run = "true" if "skiptrue" in d["log"] else "false"
                req = "pre_edit" if d["request_index"] == 3 else "final"
                cond = "drop_nudges" if d["drop_nudges"] else ("preserve" if d["preserve_thinking"] else "default")
                key = f"{tmpl}/{run}/{req}/{cond}"
            else:
                key = f"{tmpl}/thinking_off"
            want = exp["render"].get(key)
            got = [s.rsplit("-", 1)[-1] for s in d["rendered_sentinels"]]
            check(f"render/{key}", want is not None and got == want, f"rendered {got}", failures)
            seen_keys.add(key)
        missing = sorted(set(exp["render"]) - seen_keys)
        check("render/complete", not missing, f"missing {missing}" if missing else f"{len(seen_keys)} renders", failures)

    apath = RES / "autogen_rr.json"
    if apath.exists():
        for s in json.loads(apath.read_text()):
            want = exp["autogen"][s["name"]]
            got = {"order": [q["agent"] for q in s["requests"]], "next_speaker_index": [x["next_speaker_index"] for x in s["runs"]]}
            check(f"autogen/{s['name']}", got == want, f"{got}", failures)

    print(f"\n{len(failures)} failing check(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
