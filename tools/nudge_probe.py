"""Termination-path probe: does an edit on disk reach Phase 2 under each way a run can end?

usage: python3 tools/nudge_probe.py --cases probes/nudge_cases.json --out results/nudge_probe.json [--port 8010]

Each case is {"name", "bundle", "script": [...stub steps...], "add_tools": {"sub_agents/x.yaml": ["tool"]}}.
For every case the script copies the bundle (applying add_tools), starts tools/stub_model_server.py with the
case's script on its own port, runs `swegemma eval` once with the subprocess sandbox on one task, stops that
server by its own process handle, and records: the harness result (agent_patch_size, error), the nudge count
from the trace, and per request which agent was called, how many messages it saw and what the stub replied.
The stub's step counter is per server, so every case gets a fresh server.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path



ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv-official" / "bin" / "python")


def prompt_prefixes(bundle: Path) -> dict:
    """Map the first 40 chars of each agent's instruction to its name (instruction: !include <file> or inline)."""
    out = {}
    for y in bundle.rglob("*.yaml"):
        name, instr = None, None
        for ln in y.read_text().splitlines():
            if ln.startswith("name:"):
                name = ln.split(":", 1)[1].strip()
            if ln.startswith("instruction:"):
                val = ln.split(":", 1)[1].strip()
                if val.startswith("!include"):
                    f = (y.parent / val.split(None, 1)[1]).resolve()
                    instr = f.read_text() if f.exists() else None
                else:
                    instr = val.strip('"\'')
        if name and instr:
            out[instr.strip()[:40]] = name
    return out


def agent_of(body: dict, prefixes: dict) -> str:
    sys_msg = next((m for m in body.get("messages", []) if m.get("role") == "system"), {})
    text = sys_msg.get("content") if isinstance(sys_msg.get("content"), str) else json.dumps(sys_msg.get("content"))
    for prefix, name in prefixes.items():
        if (text or "").strip().startswith(prefix):
            return name
    return "?"


def wait_ready(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=1).read()
            return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"stub on port {port} did not start")


TASKS = ROOT / "data" / "tasks.jsonl"
SNAPSHOTS = ROOT / "data" / "snapshots"


def run_case(case: dict, port: int, task_id: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        bundle = td / "bundle"
        shutil.copytree(ROOT / case["bundle"], bundle)
        for rel, content in case.get("write_files", {}).items():  # e.g. a different root agent.yaml
            (bundle / rel).write_text(content)
        for rel, tools in case.get("add_tools", {}).items():
            # text edit: the agent YAML uses the compiler's !include tag, which yaml.safe_load rejects
            p = bundle / rel
            lines = p.read_text().splitlines()
            at = next(i for i, ln in enumerate(lines) if ln.strip() == "tools:")
            lines[at + 1:at + 1] = [f"  - {t}" for t in tools]
            p.write_text("\n".join(lines) + "\n")
        script = td / "script.json"
        script.write_text(json.dumps(case["script"]))
        log = td / "requests.jsonl"
        stub = subprocess.Popen([sys.executable, str(ROOT / "tools" / "stub_model_server.py"), "--port", str(port),
                                 "--log", str(log), "--script", str(script)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wait_ready(port)
            env = {"OPENAI_BASE_URL": f"http://127.0.0.1:{port}/v1", "PATH": "/usr/bin:/bin:/opt/homebrew/bin",
                   "HOME": str(Path.home()), **case.get("env", {})}
            res = td / "res"
            proc = subprocess.run([PY, "-m", "swegemma", "eval", "--tasks", str(TASKS),
                                   "--snapshots-dir", str(SNAPSHOTS), "--results-dir", str(res),
                                   "--submission-dir", str(bundle), "--sandbox", "subprocess", "--task-id", task_id,
                                   "--max-time-minutes", "2", "--display", "quiet"],
                                  capture_output=True, text=True, env=env, timeout=600)
        finally:
            stub.terminate()
            stub.wait(timeout=10)
        if case.get("keep_log"):  # keep the captured requests for later replay against a real model
            shutil.copy(log, ROOT / "results" / f"requests_{case['name']}.jsonl")
        result = json.loads((res / "task_results.jsonl").read_text().splitlines()[0])
        trace_files = list((res / "traces").glob("*.json"))
        steps = json.loads(trace_files[0].read_text()).get("steps", []) if trace_files else []
        nudge_texts = [s.get("message", "") for s in steps if (s.get("extra") or {}).get("event_type") == "continuation_nudge"]
        nudges = len(nudge_texts)
        patch_files = list((res / "patches").glob("*")) if (res / "patches").exists() else []
        patch_text = patch_files[0].read_text(errors="replace") if patch_files else ""
        requests = []
        prefixes = prompt_prefixes(bundle)
        for i, line in enumerate(log.read_text().splitlines() if log.exists() else []):
            rec = json.loads(line)
            body = rec["body"]
            step = rec.get("step") or {}
            reply = f"call {step['tool']}" if "tool" in step else "text"
            requests.append({"n": i, "agent": agent_of(body, prefixes), "n_msgs": len(body.get("messages", [])),
                             "tools": len(body.get("tools", [])), "reply": reply, "unmatched": bool(step.get("unmatched"))})
        return {"name": case["name"], "bundle": case["bundle"], "add_tools": case.get("add_tools", {}), "env": case.get("env", {}),
                "agent_patch_size": result.get("agent_patch_size"), "patch_has_probe_edit": "# probe edit" in patch_text,
                "resolved": result.get("resolved"), "test_exit_code": result.get("test_exit_code"),
                "unmatched_requests": sum(1 for q in requests if q.get("unmatched")),
                "patch_sha8": hashlib.sha256(patch_text.encode()).hexdigest()[:8] if patch_text else "",
                "error": (result.get("error") or "")[:160], "nudges": nudges, "nudge_heads": [n[:90] for n in nudge_texts], "llm_calls": result.get("total_llm_calls"),
                "eval_exit": proc.returncode, "requests": requests}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--task-id", default="rich_3518")
    ap.add_argument("--tasks-file", default=str(TASKS))
    ap.add_argument("--snapshots-dir", default=str(SNAPSHOTS))
    args = ap.parse_args()
    globals()["TASKS"], globals()["SNAPSHOTS"] = Path(args.tasks_file).resolve(), Path(args.snapshots_dir).resolve()
    out = []
    for case in json.loads(Path(args.cases).read_text()):
        r = run_case(case, args.port, case.get("task_id", args.task_id))
        out.append(r)
        seq = " ".join(f"{q['agent']}:{q['reply'].replace('call ', '')}" for q in r["requests"])
        print(f"{r['name']:<22} patch={r['agent_patch_size']:<4} resolved={r['resolved']!s:<5} sha={r['patch_sha8'] or '-':<8} "
              f"nudges={r['nudges']} exit={r['eval_exit']} err={r['error'][:60]!r}\n    {seq}", flush=True)
    Path(args.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
