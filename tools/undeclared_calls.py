"""Count tool calls that name a tool the request did not offer, in recorded runs of the official harness.

usage: python3 tools/undeclared_calls.py RUN_DIR [RUN_DIR ...] --out results/<name>.csv

RUN_DIR has the layout described in tools/continuation_triggers.py (llm_calls.jsonl.gz, and optionally
results_<pass>/traces/trace_<task>.json). Inputs contain competition task text and are not shipped; the CSV holds
counts only.

Per run:
  agent_requests    logged requests that start with the system instruction (compaction-summary requests, which
                    offer no tools and return no tool call, are skipped)
  tool_calls        tool calls in the logged responses; undeclared = calls whose name is not among the tools of
                    that request
  text_calls        tool calls the server's parser left in the visible text ("call:<name>{" markup); the harness
                    never executes these, so they are checked separately; text_undeclared = their names not offered
  trace_calls       tool calls in the harness trace, which also holds calls the recorder missed (it keeps successful
                    calls only); trace_undeclared = names outside the tools offered anywhere in the run's logged
                    requests (the trace stores no per-request tool list)
Totals are printed, with the finish_reason counts of the agent responses.
"""

import argparse
import csv
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

TEXT_CALL = re.compile(r"call:([A-Za-z_][A-Za-z0-9_]*)\{")


def read_dir(run_dir: Path, finish: Counter, names: Counter) -> list:
    per = defaultdict(Counter)
    offered_any = defaultdict(set)
    with gzip.open(run_dir / "llm_calls.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            run = rec.get("run")
            msgs = rec.get("messages") or []
            if not msgs or msgs[0].get("role") != "system":
                per[run]["skipped"] += 1
                if any((ch.get("message") or {}).get("tool_calls") for ch in (rec.get("response") or {}).get("choices") or []):
                    sys.exit(f"{run_dir}: {run}: a request without a system message returned a tool call")
                continue
            offered = {(t.get("function") or {}).get("name") for t in rec.get("tools") or []}
            offered_any[run] |= offered
            per[run]["agent_requests"] += 1
            for ch in (rec.get("response") or {}).get("choices") or []:
                finish[ch.get("finish_reason")] += 1
                msg = ch.get("message") or {}
                for tc in msg.get("tool_calls") or []:
                    name = (tc.get("function") or {}).get("name")
                    names[name] += 1
                    per[run]["tool_calls"] += 1
                    per[run]["undeclared"] += name not in offered
                for name in TEXT_CALL.findall(msg.get("content") or ""):
                    per[run]["text_calls"] += 1
                    per[run]["text_undeclared"] += name not in offered
    rows = []
    for run in sorted(per):
        task, label = run.rsplit("__", 1)
        trace = run_dir / f"results_{label}" / "traces" / f"trace_{task}.json"
        row = {"source": run_dir.name, "run": run, "agent_requests": per[run]["agent_requests"],
               "tool_calls": per[run]["tool_calls"], "undeclared": per[run]["undeclared"],
               "text_calls": per[run]["text_calls"], "text_undeclared": per[run]["text_undeclared"],
               "trace_calls": "", "trace_undeclared": ""}
        if trace.exists():
            calls = [tc.get("function_name") for step in json.loads(trace.read_text()).get("steps", [])
                     for tc in step.get("tool_calls") or []]
            row["trace_calls"] = len(calls)
            row["trace_undeclared"] = sum(1 for n in calls if n not in offered_any[run])
        rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dirs", nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    finish, names = Counter(), Counter()
    rows = [row for d in args.run_dirs for row in read_dir(d, finish, names)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    s = {k: sum(r[k] for r in rows) for k in ("agent_requests", "tool_calls", "undeclared", "text_calls", "text_undeclared")}
    traced = [r for r in rows if r["trace_calls"] != ""]
    print(f"runs {len(rows)}; agent requests {s['agent_requests']}; finish_reason {dict(finish)}")
    print(f"logged tool calls {s['tool_calls']}, undeclared {s['undeclared']}; names {dict(names.most_common())}")
    print(f"tool calls left in the text {s['text_calls']} in {sum(1 for r in rows if r['text_calls'])} runs, "
          f"undeclared {s['text_undeclared']}")
    print(f"trace tool calls {sum(r['trace_calls'] for r in traced)} in {len(traced)} traced runs, "
          f"undeclared {sum(r['trace_undeclared'] for r in traced)}")


if __name__ == "__main__":
    main()
