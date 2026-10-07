"""Replay one captured request to a real model with the last user message swapped, and tally what the model does.

usage: python3 tools/replay_nudge.py --log results/stub_requests_trap.jsonl --n-request 3 \
           --base-url http://127.0.0.1:8020/v1 --samples 20 --out results/replay_nudge_12b.json

The captured request (from tools/stub_model_server.py) is what the harness sent to the agent that received the
continuation nudge. Variants replace its last user message:
  harness  - the harness's own nudge (names submit_patch)
  neutral  - the same sentence without the submit_patch clause
Every sample keeps the captured tools, sampling fields and chat_template_kwargs, adds seed=i, and is classified as
a structured call to a declared tool, a structured call to an undeclared tool, a call written as text
(e.g. "call:submit_patch" in the content), or plain text.
"""

import argparse
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VARIANTS = {
    "harness": "Please continue your work using the available tools, or call submit_patch when you have completed "
               "and verified your changes.",
    "neutral": "Please continue your work using the available tools.",
    "cutoff": "Your previous response reached the token limit before the tool call finished closing (<|tool_call|> was "
              "cut off). Do NOT repeat your prior reasoning in thought\u2014emit your next tool call immediately, and if "
              "calling edit_file or write_file, split the change into smaller incremental edits.",
    "cutoff_neutral": "Your previous response reached the token limit before the tool call finished closing "
                      "(<|tool_call|> was cut off). Do NOT repeat your prior reasoning in thought\u2014emit your next "
                      "tool call immediately.",
}


def post(url: str, body: dict, timeout: float = 900) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def classify(msg: dict, declared: set) -> tuple[str, list]:
    calls = [c["function"]["name"] for c in (msg.get("tool_calls") or [])]
    if calls:
        return ("undeclared_call" if any(c not in declared for c in calls) else "declared_call"), calls
    text = (msg.get("content") or "") + (msg.get("reasoning_content") or "")
    written = re.findall(r"call:\s*([A-Za-z_][\w]*)", text)
    if written:
        return ("text_call_undeclared" if any(w not in declared for w in written) else "text_call_declared"), written
    return "text", []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--n-request", type=int, required=True)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--samples", type=int, default=20)
    ap.add_argument("--variants", default="harness,neutral")
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--thinking", action="store_true")
    args = ap.parse_args()
    bases = {}
    for log in args.log.split(","):
        b = json.loads(Path(log).read_text().splitlines()[args.n_request])["body"]
        assert b["messages"][-1]["role"] == "user", f"last message must be the nudge: {log}"
        bases[Path(log).stem] = b

    def one(hist: str, vname: str, i: int) -> dict:
        base = bases[hist]
        declared = {t["function"]["name"] for t in base.get("tools", [])}
        body = json.loads(json.dumps(base))
        if vname != "orig":  # "orig" keeps the harness's own captured message byte for byte
            body["messages"][-1] = {"role": "user", "content": VARIANTS[vname]}
        body["seed"] = i
        body["max_completion_tokens"] = min(int(body.get("max_completion_tokens") or args.max_tokens), args.max_tokens)
        if args.thinking:  # same request with the template's thinking switch on
            body.setdefault("chat_template_kwargs", {})["enable_thinking"] = True
        t0 = time.time()
        msg = post(args.base_url.rstrip("/") + "/chat/completions", body)["choices"][0]["message"]
        kind, names = classify(msg, declared)
        r = {"history": hist, "variant": vname, "seed": i, "kind": kind, "names": names, "secs": round(time.time() - t0, 1),
             "content_head": (msg.get("content") or "")[:160]}
        print(f"{hist[:28]:<28} {vname:<14} seed={i:<2} {kind:<22} {names} {r['secs']}s", flush=True)
        return r

    jobs = [(h, v, i) for i in range(args.samples) for h in bases for v in args.variants.split(",")]
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(lambda hvi: one(*hvi), jobs))
    summary = {}
    for r in results:
        summary.setdefault(r["variant"], {}).setdefault(r["kind"], 0)
        summary[r["variant"]][r["kind"]] += 1
    Path(args.out).write_text(json.dumps({"histories": sorted(bases), "summary": summary, "samples": results}, indent=1))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
