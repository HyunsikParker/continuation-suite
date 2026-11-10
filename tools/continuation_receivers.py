"""List which agent receives each harness continuation in recorded multi-agent runs of the official harness.

usage: python3 tools/continuation_receivers.py RUN_DIR [RUN_DIR ...] --out results/<name>.csv

RUN_DIR has the layout described in tools/continuation_triggers.py (llm_calls.jsonl.gz and runs.jsonl). Inputs
contain competition task text and are not shipped; the CSV holds agent labels, tool names and counts only.

Agents are told apart by the request itself: the first 80 characters of the system instruction plus the sorted
names of the offered tools. They are labelled agent1, agent2, ... in the order of their first request across the
given folders, so in a SequentialAgent bundle agent1 is the first sub-agent. Compaction-summary requests (no system
message) are skipped.

One CSV row per continuation that reached a logged model call:
  trigger                   tool_cut, length or generic (the three wordings, see continuation_triggers.py)
  stopped_agent             the agent whose response ended the previous harness turn
  receiver                  the agent whose request ends with the continuation
  receiver_has_submit       1 if that request offers submit_patch
  receiver_requests         consecutive requests by the receiver, from the continuation until another agent asks
  receiver_tool_calls       tool calls in those responses
  receiver_first_action     name of the first tool called after the continuation, or "text" for a plain reply
  receiver_undeclared       names of called tools the request did not offer, joined by ";"
  submit_after              1 if a later request that offers submit_patch calls it
  resolved                  the run's verification result
Totals per agent are printed: requests, tool calls, and undeclared calls before and after the run's first
continuation. The script exits non-zero if a continuation has no earlier agent request in its run.
"""

import argparse
import csv
import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from continuation_triggers import is_agent_request, kind_of, text_of

FIELDS = ["source", "run", "task", "pass", "resolved", "trigger", "stopped_agent", "receiver", "receiver_has_submit",
          "receiver_requests", "receiver_tool_calls", "receiver_first_action", "receiver_undeclared", "submit_after"]


def offered(rec: dict) -> set:
    return {t["function"]["name"] for t in (rec.get("tools") or [])}


def called(rec: dict) -> list:
    choice = ((rec.get("response") or {}).get("choices") or [{}])[0]
    return [t["function"]["name"] for t in ((choice.get("message") or {}).get("tool_calls") or [])]


def agent_key(rec: dict) -> tuple:
    return text_of(rec["messages"][0].get("content"))[:80], tuple(sorted(offered(rec)))


def continuation_kind(rec: dict):
    last = rec["messages"][-1]
    return kind_of(text_of(last.get("content"))) if last.get("role") == "user" else None


def read_dir(run_dir: Path, labels: dict, totals: dict) -> tuple:
    runs = {}
    for line in (run_dir / "runs.jsonl").read_text().splitlines():
        r = json.loads(line)
        runs[f"{r['id']}__{r['pass']}"] = r
    by_run = defaultdict(list)
    with gzip.open(run_dir / "llm_calls.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            if rec.get("run") not in runs:
                sys.exit(f"{run_dir}: call record with unknown run tag {rec.get('run')!r}")
            if is_agent_request(rec):
                by_run[rec["run"]].append(rec)
    rows, orphan = [], []
    for run, recs in sorted(by_run.items()):
        recs.sort(key=lambda rec: rec["t"])
        who = [labels.setdefault(agent_key(rec), f"agent{len(labels) + 1}") for rec in recs]
        seen = False
        for i, rec in enumerate(recs):
            kind = continuation_kind(rec)
            seen = seen or bool(kind)
            phase = "after" if seen else "before"
            names = called(rec)
            totals[who[i]]["requests"] += 1
            totals[who[i]]["tool_calls"] += len(names)
            totals[who[i]][f"undeclared_{phase}"] += sum(1 for n in names if n not in offered(rec))
            if not kind:
                continue
            if i == 0:
                orphan.append(run)
                continue
            j = i
            while j < len(recs) and who[j] == who[i]:
                j += 1
            stretch = recs[i:j]
            calls = [n for r in stretch for n in called(r)]
            undeclared = [n for r in stretch for n in called(r) if n not in offered(r)]
            info = runs[run]
            rows.append({
                "source": run_dir.parent.name if run_dir.name == "p1" else run_dir.name,
                "run": run, "task": info["id"], "pass": info["pass"], "resolved": int(bool(info.get("resolved"))),
                "trigger": kind, "stopped_agent": who[i - 1], "receiver": who[i],
                "receiver_has_submit": int("submit_patch" in offered(rec)),
                "receiver_requests": len(stretch), "receiver_tool_calls": len(calls),
                "receiver_first_action": (called(rec) or ["text"])[0],
                "receiver_undeclared": ";".join(undeclared),
                "submit_after": int(any("submit_patch" in offered(r) and "submit_patch" in called(r) for r in recs[i:])),
            })
    return rows, len(runs), orphan


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dirs", nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    labels, totals, rows, n_runs, orphans = {}, defaultdict(Counter), [], 0, []
    for d in args.run_dirs:
        r, n, o = read_dir(d, labels, totals)
        rows += r
        n_runs += n
        orphans += o
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"runs {n_runs}; continuations {len(rows)} in {len({(r['source'], r['run']) for r in rows})} runs")
    for (_, tools), label in sorted(labels.items(), key=lambda kv: kv[1]):
        t = totals[label]
        print(f"{label}: offers {', '.join(tools)}; requests {t['requests']}, tool calls {t['tool_calls']}, "
              f"undeclared before a continuation {t['undeclared_before']}, after {t['undeclared_after']}")
    print("stopped agent -> receiver:", dict(Counter(f"{r['stopped_agent']}->{r['receiver']}" for r in rows)))
    print("receivers without submit_patch:", sum(1 for r in rows if not r["receiver_has_submit"]),
          "| with an undeclared call:", sum(1 for r in rows if r["receiver_undeclared"]),
          "| undeclared names:", dict(Counter(n for r in rows for n in r["receiver_undeclared"].split(";") if n)))
    print("first action:", dict(Counter(r["receiver_first_action"] for r in rows)),
          "| submit_patch called later:", sum(r["submit_after"] for r in rows),
          "| resolved:", sum(r["resolved"] for r in rows))
    if orphans:
        print(f"continuations with no earlier agent request: {orphans}")
    sys.exit(1 if orphans else 0)


if __name__ == "__main__":
    main()
