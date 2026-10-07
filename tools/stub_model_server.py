"""Recording stand-in for the scorer's OpenAI-compatible model server.

usage: python3 tools/stub_model_server.py --port 8000 --log results/stub_requests.jsonl [--script script.json]

Every POST to /v1/chat/completions is appended to the log exactly as received (headers that carry
credentials are not logged). Replies follow a script: a JSON list of steps, each either
  {"tool": "<name>", "args": {...}}   -> one tool call
  {"text": "<content>"}               -> a plain assistant message (ends the ADK turn)
The last step repeats once the script is exhausted. GET /v1/models lists the requested model name.
A script may instead be {"by_agent": {"<text in the system prompt>": [steps], ...}}: each agent, recognised by a
substring of its system prompt, then follows its own step list with its own counter (stage-keyed scripting).
"""

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_SCRIPT = [{"tool": "get_status", "args": {}}, {"text": "Done."}]


def make_handler(log_path: Path, script: list | dict, lock: threading.Lock, counter: list):
    agent_counters: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep stdout quiet
            pass

        def _send(self, code: int, payload: dict | str, content_type="application/json"):
            body = payload if isinstance(payload, str) else json.dumps(payload)
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.rstrip("/").endswith("/models"):
                self._send(200, {"object": "list", "data": [{"id": "gemma-4-31b-it-qat-w4a16-ct", "object": "model"}]})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            try:
                req = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                req = {"_unparsed": raw[:2000].decode("utf-8", "replace")}
            with lock:
                n = counter[0]
                counter[0] += 1
            if isinstance(script, dict):  # stage-keyed: one counter per agent
                msgs = req.get("messages") or []
                sys_text = next((m.get("content") for m in msgs if m.get("role") == "system"), "") or ""
                sys_text = sys_text if isinstance(sys_text, str) else json.dumps(sys_text)
                key = next((k for k in script["by_agent"] if k in sys_text[:400]), None)
                steps = script["by_agent"].get(key) or [{"text": "Done.", "unmatched": True}]
                with lock:
                    i = agent_counters.get(key, 0)
                    agent_counters[key] = i + 1
                step = steps[min(i, len(steps) - 1)]
            else:
                step = script[min(n, len(script) - 1)]
            with lock:
                with log_path.open("a") as fh:
                    fh.write(json.dumps({"n": n, "path": self.path, "t": time.time(), "body": req, "step": step}) + "\n")
            model = req.get("model", "stub")
            if "tool" in step:
                message = {"role": "assistant", "content": None, "tool_calls": [{
                    "id": f"call_{n}", "type": "function",
                    "function": {"name": step["tool"], "arguments": json.dumps(step.get("args", {}))}}]}
                finish = "tool_calls"
            else:
                message = {"role": "assistant", "content": step.get("text", "Done.")}
                finish = "stop"
            if "reasoning" in step:  # what vLLM's reasoning parser returns next to the answer
                message["reasoning_content"] = step["reasoning"]
            resp = {"id": f"chatcmpl-stub-{n}", "object": "chat.completion", "created": int(time.time()), "model": model,
                    "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
            if req.get("stream"):
                chunk = {"id": resp["id"], "object": "chat.completion.chunk", "created": resp["created"], "model": model,
                         "choices": [{"index": 0, "delta": message, "finish_reason": finish}]}
                self._send(200, f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n", "text/event-stream")
            else:
                self._send(200, resp)

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--log", required=True)
    ap.add_argument("--script", default="")
    args = ap.parse_args()
    script = json.loads(Path(args.script).read_text()) if args.script else DEFAULT_SCRIPT
    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(log_path, script, threading.Lock(), [0]))
    print(f"stub model server on 127.0.0.1:{args.port}, logging to {log_path}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
