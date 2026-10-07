"""Generate the paper's tables from saved suite outputs (no model calls, no network).

usage: python3 tools/make_report.py --out paper/TABLES.md

Inputs (all produced by the suite's own scripts):
  results/fx_suite.json            tools/nudge_probe.py on probes/fx_suite_cases.json (synthetic fixture)
  results/render_31b_vs_12b.jsonl  tools/render_check.py runs on the render_* request logs
  results/autogen_rr.json          tools/autogen_adapter.py
  results/replay_*12b*.json        tools/replay_nudge.py against a local Gemma 4 12B server
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def suite_rows(path: Path) -> dict:
    return {r["name"]: r for r in json.loads(path.read_text())}


def outcome(r: dict) -> str:
    if r["agent_patch_size"]:
        return "resolved" if r["resolved"] else f"patch kept, tests fail ({r['agent_patch_size']} B)"
    err = r["error"].split(":", 1)[-1].strip().split("\n")[0][:40] if r["error"] else "no patch"
    return f"lost ({err})"


def receivers(r: dict) -> str:
    seq = [q["agent"] for q in r["requests"]]
    return " ".join(seq)


def table_routing(s: dict) -> list[str]:
    rows = [("SequentialAgent, fixer owns submit_patch", "route_seq_fixer_only"),
            ("SequentialAgent, both own submit_patch", "route_seq_both"),
            ("LlmAgent + transfer, fixer answered last, fixer owns", "route_transfer_fixer_last_fixer_only"),
            ("LlmAgent + transfer, locator answered last, fixer owns", "route_transfer_locator_last_fixer_only"),
            ("LlmAgent + transfer, locator answered last, both own", "route_transfer_locator_last_both"),
            ("SequentialAgent, cut-off nudge names edit_file", "route_seq_cutoff"),
            ("LoopAgent (2 iterations), text end", "route_loop2_text_end"),
            ("LlmAgent root + AgentTool analyzer", "route_agenttool")]
    out = ["| configuration | request order (agent per model call) | nudges | outcome |", "|---|---|---|---|"]
    for label, key in rows:
        r = s[key]
        out.append(f"| {label} | {receivers(r)} | {r['nudges']} | {outcome(r)} |")
    return out


def table_delegation(s: dict) -> list[str]:
    out = ["| skip_summarization | analyzer calls N | nudges | outcome |", "|---|---|---|---|"]
    for skip in ("true", "false"):
        for n in (2, 3, 4, 6):
            r = s[f"deleg_skip{skip}_n{n}"]
            out.append(f"| {skip} | {n} | {r['nudges']} | {outcome(r)} |")
    return out


def table_render(path: Path) -> list[str]:
    out = ["| template | run | request | condition | reasoning in raw history | reasoning rendered | analyzer reports rendered |",
           "|---|---|---|---|---|---|---|"]
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows = [d for d in rows if "render_skip" in d["log"]]
    order = lambda d: ("31B" not in d["template"], "skipfalse" in d["log"], d["request_index"] != 3,  # noqa: E731
                       (d["drop_nudges"], d["preserve_thinking"]))
    for d in sorted(rows, key=order):
        cond = "nudges removed" if d["drop_nudges"] else ("preserve_thinking" if d["preserve_thinking"] else "default")
        tmpl = "31B (official)" if "31B" in d["template"] else "12B"
        run = "skip true" if "skiptrue" in d["log"] else "skip false"
        req = "pre-action" if d["request_index"] == 3 else "last"
        raw = ",".join(s.rsplit("-", 1)[-1] for s in d["raw_sentinels"]) or "-"
        shown = ",".join(s.rsplit("-", 1)[-1] for s in d["rendered_sentinels"]) or "none"
        out.append(f"| {tmpl} | {run} | {req} | {cond} | {raw} | {shown} | {d['plain_rendered']}/{d['plain_raw']} |")
    return out


def table_autogen(path: Path) -> list[str]:
    out = ["| scenario | model-request order | receiver of the continuation | its tools |", "|---|---|---|---|"]
    for r in json.loads(path.read_text()):
        reqs = r["requests"]
        cont = next((q for q in reqs if "CONT-1" in q["sees"] or "Please continue" in q["sees"]), None)
        out.append(f"| {r['name']} | {' '.join(q['agent'] for q in reqs)} | {cont['agent'] if cont else '-'} | "
                   f"{', '.join(cont['tools']) if cont else '-'} |")
    return out


def table_replays() -> list[str]:
    out = ["| replay set | histories | wording | generations | undeclared-tool calls |", "|---|---|---|---|---|"]
    for f, label in (("replay_nudge_12b_trap.json", "trap context"), ("replay_reach_normal_12b.json", "normal nudge"),
                     ("replay_reach_cutoff_12b.json", "cut-off nudge"),
                     ("replay_reach_normal_12b_thinking.json", "normal nudge, thinking on")):
        d = json.loads((ROOT / "results" / f).read_text())
        for variant, counts in d["summary"].items():
            total = sum(counts.values())
            bad = sum(v for k, v in counts.items() if "undeclared" in k)
            out.append(f"| {label} | {len(d.get('histories', [])) or 1} | {variant} | {total} | {bad} |")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    s = suite_rows(ROOT / "results" / "fx_suite.json")
    base = s["base_noop_edit"], s["base_gold_submit"]
    parts = ["# Tables generated from saved traces", "",
             f"Fixture check: no-op edit -> {outcome(base[0])}; repair -> {outcome(base[1])} (patch sha {base[1]['patch_sha8']}).", "",
             "## Who receives the continuation", "", *table_routing(s), "",
             "## Valid delegation across the nudge limit", "", *table_delegation(s), "",
             "## Reasoning visibility at the template", "", *table_render(ROOT / "results" / "render_31b_vs_12b.jsonl"), "",
             "## AutoGen RoundRobin native resumption", "", *table_autogen(ROOT / "results" / "autogen_rr.json"), "",
             "## Gemma 4 12B replays of captured post-nudge requests", "", *table_replays(), ""]
    Path(args.out).write_text("\n".join(parts))
    print("\n".join(parts))


if __name__ == "__main__":
    main()
