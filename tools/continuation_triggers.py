"""Count the harness's continuation messages by trigger in recorded runs of the official harness.

usage: python3 tools/continuation_triggers.py RUN_DIR [RUN_DIR ...] --out results/<name>.csv

RUN_DIR is the output folder of a sampler that ran the official Evaluator on competition tasks and recorded every
successful model call (the folders behind results/p1_continuations_20261025.csv are described in the README):
  llm_calls.jsonl.gz                     one record per successful model call: run tag "<task>__<pass>", request
                                         messages and tools, response (finish_reason, message, tool_calls)
  runs.jsonl                             one row per run: id, pass, resolved, error (harness error text)
  results_<pass>/traces/trace_<task>.json  the harness trace of that run (ATIF format)
These inputs contain competition task text and are not shipped; the CSV holds counts only.

The harness (swegemma 0.2.7 to 0.2.11, harness/agent_runner.py) sends a user-role continuation after a turn that ends
without submit_patch, at most three in a row, and picks its wording from that turn's last model response:
  tool_cut  the visible text contains "<|tool_call>": "... reached the token limit before the tool call finished ..."
  length    finish_reason length (MAX_TOKENS): "... reached the token limit while thinking before a tool call ..."
  generic   anything else: "Please continue your work using the available tools, or call submit_patch ..."

Two sources are counted for every run:
  trace_*   continuation_nudge events in the harness trace: every continuation the harness sent
  log_*     agent requests in the call log whose last message is a continuation: the continuations that reached a
            model call the recorder kept. Compaction-summary requests (one user message that quotes the
            conversation, no system message) are skipped, because they repeat earlier continuation texts.
The recorder keeps successful calls only, so a continuation sent just before the time limit (the run ends before the
next call returns) appears in the trace and not in the log. The script prints both totals and exits non-zero if a
run has a logged continuation that its trace lacks.

Other columns: agent requests and finish_reason=length responses in the log, and the run's end as the harness
reported it (time_limit, tool_budget, or none).
"""

import argparse
import csv
import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

WORDING = {  # stable substrings of the three texts in swegemma's agent_runner.py
    "tool_cut": "reached the token limit before the tool call finished closing",
    "length": "reached the token limit while thinking before a tool call",
    "generic": "Please continue your work using the available tools, or call submit_patch",
}
KINDS = list(WORDING)


def text_of(content) -> str:
    if isinstance(content, list):
        return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


def kind_of(text: str):
    return next((k for k, needle in WORDING.items() if needle in text), None)


def end_of(error: str) -> str:
    if not error:
        return "none"
    if "session timeout" in error:
        return "time_limit"
    if "tool call budget" in error:
        return "tool_budget"
    return error[:40]


def is_agent_request(rec: dict) -> bool:
    """Agent requests start with the system instruction; compaction-summary requests are one user message."""
    msgs = rec.get("messages") or []
    return bool(msgs) and msgs[0].get("role") == "system"


def read_dir(run_dir: Path) -> list:
    runs = {}
    for line in (run_dir / "runs.jsonl").read_text().splitlines():
        r = json.loads(line)
        runs[f"{r['id']}__{r['pass']}"] = {"task": r["id"], "pass": r["pass"], "resolved": bool(r.get("resolved")),
                                            "end": end_of(r.get("error") or "")}
    log_counts = defaultdict(Counter)
    with gzip.open(run_dir / "llm_calls.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            run = rec.get("run")
            if run not in runs:
                sys.exit(f"{run_dir}: call record with unknown run tag {run!r}")
            if not is_agent_request(rec):
                log_counts[run]["compaction"] += 1
                continue
            log_counts[run]["requests"] += 1
            choice = ((rec.get("response") or {}).get("choices") or [{}])[0]
            if choice.get("finish_reason") == "length":
                log_counts[run]["length_responses"] += 1
            last = rec["messages"][-1]
            if last.get("role") == "user":
                kind = kind_of(text_of(last.get("content")))
                if kind:
                    log_counts[run][f"log_{kind}"] += 1
                elif len(rec["messages"]) > 2:  # a later user message that is not a harness continuation
                    log_counts[run]["log_other_user"] += 1
    rows = []
    for run, info in sorted(runs.items()):
        trace = run_dir / f"results_{info['pass']}" / "traces" / f"trace_{info['task']}.json"
        tcount = Counter()
        if trace.exists():
            for step in json.loads(trace.read_text()).get("steps", []):
                if (step.get("extra") or {}).get("event_type") == "continuation_nudge":
                    tcount[f"trace_{kind_of(step.get('message') or '') or 'other'}"] += 1
        c = log_counts[run]
        row = {"source": run_dir.name, "run": run, "task": info["task"], "pass": info["pass"],
               "resolved": int(info["resolved"]), "end": info["end"], "agent_requests": c["requests"],
               "length_responses": c["length_responses"], "trace_found": int(trace.exists())}
        row.update({f"trace_{k}": tcount[f"trace_{k}"] for k in KINDS})
        row["trace_other"] = tcount["trace_other"]
        row.update({f"log_{k}": c[f"log_{k}"] for k in KINDS})
        row["log_other_user"] = c["log_other_user"]
        rows.append(row)
    return rows


def summarize(rows: list) -> int:
    def total(prefix):
        return sum(r[f"{prefix}_{k}"] for r in rows for k in KINDS)

    print(f"runs {len(rows)} (resolved {sum(r['resolved'] for r in rows)}); "
          f"traces found {sum(r['trace_found'] for r in rows)}")
    for prefix in ("trace", "log"):
        per_run = [sum(r[f"{prefix}_{k}"] for k in KINDS) for r in rows]
        by_kind = {k: sum(r[f"{prefix}_{k}"] for r in rows) for k in KINDS}
        runs_by_kind = {k: sum(1 for r in rows if r[f"{prefix}_{k}"]) for k in KINDS}
        print(f"{prefix}: {total(prefix)} continuations in {sum(1 for n in per_run if n)} runs, at most "
              f"{max(per_run, default=0)} per run; messages by trigger {by_kind}; runs by trigger {runs_by_kind}")
    print(f"agent requests logged {sum(r['agent_requests'] for r in rows)}; finish_reason=length responses "
          f"{sum(r['length_responses'] for r in rows)} in {sum(1 for r in rows if r['length_responses'])} runs")
    print("run ends", dict(Counter(r["end"] for r in rows)))
    other = sum(r["trace_other"] for r in rows)
    if sum(r["log_other_user"] for r in rows):
        print(f"later user messages that are not continuations: {sum(r['log_other_user'] for r in rows)}")
    missing = [r["run"] for r in rows if any(r[f"log_{k}"] > r[f"trace_{k}"] for k in KINDS)]
    only_trace = [r["run"] for r in rows if any(r[f"trace_{k}"] > r[f"log_{k}"] for k in KINDS)]
    print(f"continuations in the trace but not in the log: {only_trace or 'none'}")
    if other:
        print(f"trace continuations with unrecognised wording: {other}")
    if missing:
        print(f"logged continuations missing from the trace: {missing}")
    return 1 if (missing or other) else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dirs", nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    rows = [row for d in args.run_dirs for row in read_dir(d)]
    keys = [(r["source"], r["run"]) for r in rows]
    if len(set(keys)) != len(keys):
        sys.exit("duplicate run tags")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    sys.exit(summarize(rows))


if __name__ == "__main__":
    main()
