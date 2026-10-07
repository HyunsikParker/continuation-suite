"""Native-resumption scenarios for AutoGen AgentChat RoundRobinGroupChat, driven by the same recording stub model.

usage: .venv-autogen/bin/python tools/autogen_adapter.py --out results/autogen_rr.json [--port 8030]

Two participants in fixed order: L (tool inspect_fixture) and F (tools inspect_fixture, finish_fixture). Each
scenario starts its own stub server (tools/stub_model_server.py, stage-keyed by the agent's system prompt), so the
stub answers only after AutoGen has sent a request for a given agent; it never picks the next speaker. The wrapper
only calls team.run(task=...) / team.run() on one team instance and stops through a native termination condition
(SourceMatchTermination over both participants = stop after any one participant's final response).

Recorded per scenario: the order of model requests by agent identity, each request's message roles, the
sentinels visible in it, its tool names, and the team's saved state after every run (read only).
"""

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination, SourceMatchTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient

ROOT = Path(__file__).resolve().parents[1]
L_ID, F_ID = "You are agent L, a read-only locator.", "You are agent F, a fixer that may finish the task."
NUDGE = ("Please continue your work using the available tools, or call finish_fixture when you have completed "
         "and verified your changes.")
SENTINELS = ("TASK-0", "L-OUT-1", "L-OUT-2", "L-OUT-3", "F-OUT-1", "F-OUT-2", "CONT-1", "CONT-2", "Please continue")


def inspect_fixture() -> str:
    """Return a short description of the fixture repository."""
    return "INSPECT-RESULT: tinytable/table.py defines Table.add_row"


def finish_fixture() -> str:
    """Declare the work finished."""
    return "FINISH-RESULT: finished"


def wait_ready(port: int) -> None:
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=1).read()
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("stub did not start")


def client(port: int) -> OpenAIChatCompletionClient:
    return OpenAIChatCompletionClient(
        model="stub-model", base_url=f"http://127.0.0.1:{port}/v1", api_key="not-a-key",
        model_info={"vision": False, "function_calling": True, "json_output": False, "family": "unknown",
                    "structured_output": False})


def make_team(port: int, termination) -> RoundRobinGroupChat:
    l_agent = AssistantAgent("L", model_client=client(port), tools=[inspect_fixture], system_message=L_ID,
                             reflect_on_tool_use=False)
    f_agent = AssistantAgent("F", model_client=client(port), tools=[inspect_fixture, finish_fixture],
                             system_message=F_ID, reflect_on_tool_use=False)
    return RoundRobinGroupChat([l_agent, f_agent], termination_condition=termination)


def one_response() -> SourceMatchTermination:
    return SourceMatchTermination(sources=["L", "F"])


async def scenario(name: str, script: dict, plan, port: int) -> dict:
    """plan(port) -> list of (label, team, task) steps run in order; returns the trace."""
    with tempfile.TemporaryDirectory() as td:
        sp = Path(td) / "script.json"
        sp.write_text(json.dumps({"by_agent": script}))
        log = Path(td) / "requests.jsonl"
        stub = subprocess.Popen([sys.executable, str(ROOT / "tools" / "stub_model_server.py"), "--port", str(port),
                                 "--log", str(log), "--script", str(sp)], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        runs = []
        try:
            wait_ready(port)
            for label, team, task in plan(port):
                before = len(log.read_text().splitlines()) if log.exists() else 0
                result = await (team.run(task=task) if task is not None else team.run())
                after = len(log.read_text().splitlines()) if log.exists() else 0
                state = await team.save_state()
                mgr = next((v for k, v in (state.get("agent_states") or {}).items() if "manager" in k.lower()
                            or "RoundRobin" in k), {})
                runs.append({"label": label, "task": task, "requests": [before, after],
                             "stop_reason": str(result.stop_reason)[:120],
                             "sources": [getattr(m, "source", "?") for m in result.messages],
                             "next_speaker_index": mgr.get("next_speaker_index") if isinstance(mgr, dict) else None})
        finally:
            stub.terminate()
            stub.wait(timeout=10)
        requests = []
        for line in (log.read_text().splitlines() if log.exists() else []):
            rec = json.loads(line)
            body = rec["body"]
            msgs = body.get("messages", [])
            sys_text = next((m.get("content") for m in msgs if m.get("role") == "system"), "") or ""
            agent = "L" if L_ID in sys_text else ("F" if F_ID in sys_text else "?")
            flat = json.dumps(msgs)
            step = rec.get("step") or {}
            requests.append({"agent": agent, "roles": [m.get("role") for m in msgs],
                             "sees": [s for s in SENTINELS if s in flat],
                             "tools": [t["function"]["name"] for t in body.get("tools", [])],
                             "reply": f"call {step['tool']}" if "tool" in step else step.get("text", "")})
        return {"name": name, "runs": runs, "requests": requests,
                "first_request_agents": [r["agent"] for r in requests]}


def text(t: str) -> dict:
    return {"text": t}


async def main_async(out: Path, port: int) -> None:
    results = []
    plain = {L_ID: [text("L-OUT-1"), text("L-OUT-2"), text("L-OUT-3")], F_ID: [text("F-OUT-1"), text("F-OUT-2")]}

    # RR0: uninterrupted baseline, three participant responses, native MaxMessageTermination (task + 3)
    results.append(await scenario("RR0_baseline", plain,
                                  lambda p: [("run", make_team(p, MaxMessageTermination(4)), "TASK-0 fix add_row")], port))

    # RR1: stop after L, resume the same team with CONT-1
    def rr1(p):
        team = make_team(p, one_response())
        return [("run", team, "TASK-0 fix add_row"), ("resume", team, "CONT-1 continue")]
    results.append(await scenario("RR1_resume_after_L", plain, rr1, port))

    # RR2: stop after L, resume without a task (F replies), then resume with CONT-1
    def rr2(p):
        team = make_team(p, one_response())
        return [("run", team, "TASK-0 fix add_row"), ("resume", team, None), ("resume", team, "CONT-1 continue")]
    results.append(await scenario("RR2_resume_after_F", plain, rr2, port))

    # RR3: fresh-team control with the same continuation text as a fresh task
    results.append(await scenario("RR3_fresh_team", plain,
                                  lambda p: [("run", make_team(p, one_response()), "CONT-1 continue")], port))

    # RR4: four native resumptions, one participant response each
    def rr4(p):
        team = make_team(p, one_response())
        return [("run", team, "TASK-0 fix add_row")] + [("resume", team, None) for _ in range(4)]
    results.append(await scenario("RR4_repeated", plain, rr4, port))

    # RR5: the same harness-style continuation text reaches whoever is scheduled next
    tools_script = {L_ID: [text("L-OUT-1"), {"tool": "inspect_fixture", "args": {}}, text("L-OUT-3")],
                    F_ID: [{"tool": "finish_fixture", "args": {}}, {"tool": "finish_fixture", "args": {}}]}

    def rr5_after_l(p):
        team = make_team(p, one_response())
        return [("run", team, "TASK-0 fix add_row"), ("resume", team, NUDGE)]
    results.append(await scenario("RR5_nudge_after_L", tools_script, rr5_after_l, port))

    tools_script_f = {L_ID: [text("L-OUT-1"), {"tool": "inspect_fixture", "args": {}}],
                      F_ID: [text("F-OUT-1"), {"tool": "finish_fixture", "args": {}}]}

    def rr5_after_f(p):
        team = make_team(p, one_response())
        return [("run", team, "TASK-0 fix add_row"), ("resume", team, None), ("resume", team, NUDGE)]
    results.append(await scenario("RR5_nudge_after_F", tools_script_f, rr5_after_f, port))

    out.write_text(json.dumps(results, indent=1))
    for r in results:
        print(r["name"], "requests:", " ".join(r["first_request_agents"]),
              "| per run:", [(x["label"], x["requests"], x["sources"][1:] if x["sources"] else []) for x in r["runs"]])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=8030)
    args = ap.parse_args()
    asyncio.run(main_async(Path(args.out), args.port))


if __name__ == "__main__":
    main()
