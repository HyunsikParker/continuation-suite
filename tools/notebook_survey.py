"""Count agent-configuration settings in the public notebooks of a Kaggle competition.

The survey reads text only; no notebook is executed. Pull the notebooks first, one directory per notebook:

    kaggle kernels list --competition gemma-4-developer-agent --page-size 100 --page 1 --csv > page1.csv   # and so on
    kaggle kernels pull <owner>/<slug> -p notebooks/<owner>/<slug>

Then:

    python3 tools/notebook_survey.py notebooks results/notebook_survey_<date>.csv

For every notebook the script joins the code cells (or the .py script) and records 0/1 flags:

    builds_submission  mentions root_agent.yaml, agent.yaml or submission.zip (writes an agent configuration)
    agent_tool         declares an AgentTool (`AgentTool` or a YAML `agent_tool:` entry)
    skip_true/false    sets skip_summarization to true / false
    sequential, loop   uses a SequentialAgent / LoopAgent
    include_none/default  sets include_contents to none / default
    sub_agents         declares a sub_agents list

Text matching is approximate: settings kept in attached datasets are not seen, and copies of one notebook are counted
separately.
"""
import csv
import json
import os
import re
import sys

PAT = {
    "builds_submission": re.compile(r"root_agent\.ya?ml|submission\.zip|agent\.ya?ml"),
    "agent_tool": re.compile(r"\bAgentTool\b|agent_tool\s*:"),
    "skip_true": re.compile(r"skip_summarization\W{0,4}(true|True)\b"),
    "skip_false": re.compile(r"skip_summarization\W{0,4}(false|False)\b"),
    "sequential": re.compile(r"\bSequentialAgent\b"),
    "loop": re.compile(r"\bLoopAgent\b"),
    "include_none": re.compile(r"include_contents\W{0,4}['\"]?none\b"),
    "include_default": re.compile(r"include_contents\W{0,4}['\"]?default\b"),
    "sub_agents": re.compile(r"(?m)(^|\\n|\")\s*sub_agents\s*:|sub_agents\s*=\s*\["),
}


def code_text(path):
    if path.endswith(".ipynb"):
        try:
            nb = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            return ""
        parts = []
        for cell in nb.get("cells") or []:
            if cell.get("cell_type") == "code":
                src = cell.get("source") or ""
                parts.append("".join(src) if isinstance(src, list) else src)
        return "\n".join(parts)
    return open(path, encoding="utf-8", errors="replace").read()


def main():
    root, out = sys.argv[1], sys.argv[2]
    rows = []
    for owner in sorted(os.listdir(root)):
        if not os.path.isdir(os.path.join(root, owner)):
            continue
        for slug in sorted(os.listdir(os.path.join(root, owner))):
            folder = os.path.join(root, owner, slug)
            files = [f for f in os.listdir(folder) if f.endswith((".ipynb", ".py"))] if os.path.isdir(folder) else []
            if not files:
                continue
            text = "\n".join(code_text(os.path.join(folder, f)) for f in files)
            rows.append([f"{owner}/{slug}"] + [int(bool(p.search(text))) for p in PAT.values()])
    with open(out, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["notebook"] + list(PAT))
        writer.writerows(rows)
    built = [r for r in rows if r[1]]
    col = {k: i + 1 for i, k in enumerate(PAT)}
    print(f"notebooks {len(rows)}, writing an agent configuration {len(built)}")
    for key in list(PAT)[1:]:
        print(f"{key:16s} {sum(r[col[key]] for r in built)}")
    both = sum(1 for r in built if r[col['agent_tool']] and r[col['skip_true']])
    print(f"agent_tool with skip_true {both}")


if __name__ == "__main__":
    main()
