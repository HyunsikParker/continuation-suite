"""Write the continuation test-suite cases for the synthetic fixture (tinytable_0001).

usage: python3 tools/make_suite_cases.py --out probes/fx_suite_cases.json --overlay <dir with patched swegemma>

Groups (case name prefix):
  base_      the added test fails without the repair (a no-op edit reaches Phase 2) and passes with it
  route_     who receives the nudge, by topology, with submit_patch owned by the fixer only or by both agents
  state_     what the re-invoked fixer sees (include_contents none vs default), with sentinels
  deleg_     valid AgentTool delegation, skip_summarization true vs false, N analyzer calls
  render_    the same with thinking on and reasoning sentinels (rendered afterwards by tools/render_check.py)
  fix_       maintainer-side overlays (tool-error plugin, exception salvage) and their controls
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ("python3 -c \"p='tinytable/table.py'; s=open(p).read(); "
       "s=s.replace('column = Column()\\n', 'column = Column(highlight=self.highlight)\\n', 1); open(p,'w').write(s)\"")
GOLD = {"tool": "run_command", "args": {"command": FIX}}
NOOP = {"tool": "run_command", "args": {"command": "echo '# no-op' >> tinytable/__init__.py"}}
DONE = {"text": "Done."}
SUBMIT = {"tool": "submit_patch", "args": {}}
PLAN = {"text": "FILES: tinytable/table.py\nCHANGE: Table.add_row\nCHECK: tests/test_table.py"}
CUT = {"text": "I will now apply the edit. <|tool_call>call:edit_file{path:<|\"|>tinytable/table.py"}
EDIT_CALL = {"tool": "edit_file", "args": {"path": "tinytable/table.py", "old_string": "x", "new_string": "y"}}
BAD_SKILL = {"tool": "run_skill_script", "args": {"skill_name": "scout", "file_path": ["scripts/locate.py"], "args": []}}
TO = lambda a: {"tool": "transfer_to_agent", "args": {"agent_name": a}}  # noqa: E731
ROOT_KEY, AN_KEY = "You are a careful Python engineer", "You are a read-only code analyzer"
TRANSFER_ROOT = ("name: coordinator\nmodel: gemma-4-31b-it-qat-w4a16-ct\n"
                 "description: Routes the task to the locator, then to the fixer.\n"
                 "instruction: You coordinate two colleagues. First transfer to locator, then to fixer.\n"
                 "sub_agents:\n  - config_path: sub_agents/locator.yaml\n  - config_path: sub_agents/fixer.yaml\n")
LOOP_ROOT = ("agent_class: LoopAgent\nname: swe_loop\ndescription: locate then fix, twice\nmax_iterations: 2\n"
             "sub_agents:\n  - config_path: sub_agents/locator.yaml\n  - config_path: sub_agents/fixer.yaml\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--overlay", required=True)
    args = ap.parse_args()
    v4_agent = (ROOT / "bundles/v4/agent.yaml").read_text()
    v4_sampling = (ROOT / "bundles/v4/configs/sampling.yaml").read_text()
    v8_fixer = (ROOT / "bundles/v8/sub_agents/fixer.yaml").read_text()
    both = {"sub_agents/locator.yaml": ["submit_patch"]}
    c = []
    c += [{"name": "base_noop_edit", "bundle": "bundles/v5b", "script": [NOOP, SUBMIT, DONE]},
          {"name": "base_gold_submit", "bundle": "bundles/v5b", "script": [GOLD, SUBMIT, DONE]},
          {"name": "base_gold_text_end", "bundle": "bundles/v5b", "script": [GOLD, DONE]}]
    for own, extra in (("fixer_only", {}), ("both", both)):
        c.append({"name": f"route_seq_{own}", "bundle": "bundles/v8", "add_tools": extra,
                  "script": [PLAN, GOLD, DONE, SUBMIT, DONE]})
        c.append({"name": f"route_transfer_fixer_last_{own}", "bundle": "bundles/v8", "add_tools": extra,
                  "write_files": {"agent.yaml": TRANSFER_ROOT}, "script": [TO("locator"), TO("fixer"), GOLD, DONE, SUBMIT, DONE]})
        c.append({"name": f"route_transfer_locator_last_{own}", "bundle": "bundles/v8", "add_tools": extra,
                  "write_files": {"agent.yaml": TRANSFER_ROOT},
                  "script": [TO("locator"), TO("fixer"), GOLD, TO("locator"), DONE, SUBMIT, DONE]})
    c += [{"name": "route_seq_text_end", "bundle": "bundles/v8", "script": [PLAN, GOLD, DONE]},
          {"name": "route_loop2_text_end", "bundle": "bundles/v8", "write_files": {"agent.yaml": LOOP_ROOT},
           "script": [PLAN, GOLD, DONE]},
          {"name": "route_seq_cutoff", "bundle": "bundles/v8", "script": [PLAN, GOLD, CUT, EDIT_CALL, DONE]},
          {"name": "route_agenttool", "bundle": "bundles/v4",
           "script": {"by_agent": {ROOT_KEY: [{"tool": "code_analyzer", "args": {"request": "find add_row"}}, GOLD, DONE, SUBMIT, DONE],
                                   AN_KEY: [{"text": "ANALYZER-REPORT"}]}}}]
    sentinels = [{"text": "PLAN-SENTINEL-A: tinytable/table.py add_row"}, GOLD,
                 {"text": "FIXER-SENTINEL-B: edited add_row"}, {"text": "LOCATOR-AFTER-NUDGE-C"}, {"text": "FIXER-AFTER-NUDGE-D"}]
    c += [{"name": "state_fixer_none", "bundle": "bundles/v8", "keep_log": True, "script": sentinels},
          {"name": "state_fixer_default", "bundle": "bundles/v8", "keep_log": True, "script": sentinels,
           "write_files": {"sub_agents/fixer.yaml": v8_fixer.replace("include_contents: none\n", "")}}]
    for skip in (True, False):
        files = {} if skip else {"agent.yaml": v4_agent.replace("skip_summarization: true", "skip_summarization: false")}
        for n in (2, 3, 4, 6):
            root = [{"tool": "code_analyzer", "args": {"request": f"report {k}"}} for k in range(n)] + [GOLD, SUBMIT, DONE]
            c.append({"name": f"deleg_skip{str(skip).lower()}_n{n}", "bundle": "bundles/v4", "write_files": files,
                      "script": {"by_agent": {ROOT_KEY: root, AN_KEY: [{"text": "ANALYZER-REPORT"}]}}})
        root = [{"tool": "code_analyzer", "args": {"request": f"report {k}"}, "reasoning": f"ROOT-REASONING-{k}"} for k in range(3)]
        root += [dict(GOLD, reasoning="ROOT-REASONING-8"), dict(SUBMIT, reasoning="ROOT-REASONING-9"), DONE]
        rfiles = dict(files, **{"configs/sampling.yaml": v4_sampling.replace("include_thoughts: false", "include_thoughts: true")})
        c.append({"name": f"render_skip{str(skip).lower()}_n3", "bundle": "bundles/v4", "keep_log": True, "write_files": rfiles,
                  "script": {"by_agent": {ROOT_KEY: root, AN_KEY: [{"text": "ANALYZER-REPORT"}]}}})
    trap = [PLAN, GOLD, DONE, SUBMIT, DONE]
    throw = [PLAN, GOLD, BAD_SKILL, DONE]
    ov = {"PYTHONPATH": args.overlay}
    c += [{"name": "fix_overlay_off_trap", "bundle": "bundles/v8", "env": dict(ov, SWEGEMMA_PROBE_VARIANT=""), "script": trap},
          {"name": "fix_plugin_trap", "bundle": "bundles/v8", "env": dict(ov, SWEGEMMA_PROBE_VARIANT="cb"), "script": trap},
          {"name": "fix_salvage_trap", "bundle": "bundles/v8", "env": dict(ov, SWEGEMMA_PROBE_VARIANT="salvage"), "script": trap},
          {"name": "fix_official_skill_throw", "bundle": "bundles/v8", "script": throw},
          {"name": "fix_plugin_skill_throw", "bundle": "bundles/v8", "env": dict(ov, SWEGEMMA_PROBE_VARIANT="cb"), "script": throw}]
    for case in c:
        case["task_id"] = "tinytable_0001"
    Path(args.out).write_text(json.dumps(c, indent=1))
    print(len(c), "cases")


if __name__ == "__main__":
    main()
