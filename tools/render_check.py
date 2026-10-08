"""Render captured requests with a local Gemma 4 chat template and count which reasoning sentinels survive.

usage: python3 tools/render_check.py --template-dir <hf snapshot with tokenizer + chat_template.jinja> \
           --log results/requests_<case>.jsonl --agent-text "You are a careful Python engineer" --sentinel ROOT-REASONING

For the last request whose system prompt contains --agent-text, the script reports how many distinct sentinels
appear in the raw HTTP messages (reasoning / reasoning_content fields) and how many appear in the rendered prompt
(enable_thinking=True, add_generation_prompt=True), plus the number of user messages after the first one.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from transformers import AutoTokenizer


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template-dir", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--agent-text", required=True)
    ap.add_argument("--sentinel", default="ROOT-REASONING")
    ap.add_argument("--plain", default="ANALYZER-REPORT", help="ordinary-content marker counted in raw and rendered text")
    ap.add_argument("--request-index", type=int, default=-1, help="which of this agent's requests to render")
    ap.add_argument("--drop-nudges", action="store_true", help="diagnostic: remove harness continuation messages")
    ap.add_argument("--chat-template-file", default="", help="render with this template instead of the tokenizer's")
    ap.add_argument("--preserve-thinking", action="store_true", help="diagnostic: pass preserve_thinking=True")
    args = ap.parse_args()
    tok = AutoTokenizer.from_pretrained(args.template_dir)
    rows = [json.loads(l) for l in Path(args.log).read_text().splitlines()]
    mine = [r for r in rows if args.agent_text in (r["body"]["messages"][0].get("content") or "")[:400]]
    body = mine[args.request_index]["body"]
    msgs = body["messages"]
    if args.drop_nudges:
        msgs = [m for m in msgs if not (m.get("role") == "user" and isinstance(m.get("content"), str)
                                        and m["content"].startswith(("Please continue", "Your previous response")))]
    # the 31B template requires tool-call arguments as mappings, so deserialize the JSON strings sent over HTTP
    msgs = json.loads(json.dumps(msgs))
    for m in msgs:
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function") or {}
            if isinstance(fn.get("arguments"), str):
                try:
                    fn["arguments"] = json.loads(fn["arguments"] or "{}")
                except json.JSONDecodeError:
                    pass
    pat = re.compile(re.escape(args.sentinel) + r"-\d+")
    raw = set()
    for m in msgs:
        for k in ("reasoning", "reasoning_content"):
            if isinstance(m.get(k), str):
                raw |= set(pat.findall(m[k]))
    extra = {"preserve_thinking": True} if args.preserve_thinking else {}
    if args.chat_template_file:
        template_path = Path(args.chat_template_file)
        template_bytes = template_path.read_bytes()
        extra["chat_template"] = template_bytes.decode()
        template_source = template_path.parent.name
    else:
        template_path = Path(args.template_dir) / "chat_template.jinja"
        if template_path.is_file():
            template_bytes = template_path.read_bytes()
            template_source = "tokenizer-dir"
        else:
            template_bytes = tok.get_chat_template().encode()
            template_source = "tokenizer-config"
    template_sha256 = hashlib.sha256(template_bytes).hexdigest()
    rendered = tok.apply_chat_template(msgs, tools=body.get("tools"), tokenize=False, add_generation_prompt=True,
                                       enable_thinking=True, **extra)
    shown = set(pat.findall(rendered))
    users = sum(1 for m in msgs if m.get("role") == "user")
    plain_raw = json.dumps(msgs).count(args.plain)
    plain_shown = rendered.count(args.plain)
    print(json.dumps({"log": Path(args.log).name, "template": template_source,
                      "chat_template_sha256": template_sha256,
                      "preserve_thinking": args.preserve_thinking,
                      "request_index": args.request_index, "drop_nudges": args.drop_nudges,
                      "plain_raw": plain_raw, "plain_rendered": plain_shown,
                      "requests_by_agent": len(mine), "messages": len(msgs),
                      "user_messages": users, "raw_sentinels": sorted(raw), "rendered_sentinels": sorted(shown),
                      "rendered_tokens": len(tok(rendered)["input_ids"])}))


if __name__ == "__main__":
    main()
