#!/bin/zsh
# Rebuild every table of the paper on a CPU. Needs .venv-official (official harness wheels) for the ADK part,
# .venv-autogen (autogen-agentchat 0.7.5) for the AutoGen part, and TOKENIZER_DIR / TEMPLATE for rendering.
set -euo pipefail
cd "$(dirname "$0")"
PY_OFFICIAL=${PY_OFFICIAL:-.venv-official/bin/python}
PY_AUTOGEN=${PY_AUTOGEN:-.venv-autogen/bin/python}
SITE=$($PY_OFFICIAL -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')

python3 tools/make_fixture.py --out fixtures
python3 tools/make_overlay.py --site-packages "$SITE" --out overlay
python3 tools/make_suite_cases.py --out probes/fx_suite_cases.json --overlay "$PWD/overlay"
python3 tools/nudge_probe.py --cases probes/fx_suite_cases.json --out results/fx_suite.json --port 8011 \
  --tasks-file fixtures/tasks.jsonl --snapshots-dir fixtures/snapshots

if [[ -n "${TOKENIZER_DIR:-}" && -n "${TEMPLATE:-}" ]]; then
  : > results/render_31b_vs_12b.jsonl
  for log in results/requests_render_skiptrue_n3.jsonl results/requests_render_skipfalse_n3.jsonl; do
    for idx in 3 -1; do
      for opt in "" "--drop-nudges" "--preserve-thinking"; do
        python3 tools/render_check.py --template-dir "$TOKENIZER_DIR" --chat-template-file "$TEMPLATE" --log "$log" \
          --agent-text "You are a careful Python engineer" --request-index $idx ${=opt} >> results/render_31b_vs_12b.jsonl
      done
    done
  done
  # the tokenizer directory's own template (the paper used Gemma 4 12B) for the comparison rows
  for log in results/requests_render_skiptrue_n3.jsonl results/requests_render_skipfalse_n3.jsonl; do
    for idx in 3 -1; do
      for opt in "" "--drop-nudges"; do
        python3 tools/render_check.py --template-dir "$TOKENIZER_DIR" --log "$log" \
          --agent-text "You are a careful Python engineer" --request-index $idx ${=opt} >> results/render_31b_vs_12b.jsonl
      done
    done
  done
  # thinking-off control: a worker history without reasoning has nothing to exclude
  python3 tools/render_check.py --template-dir "$TOKENIZER_DIR" --chat-template-file "$TEMPLATE" \
    --log results/requests_state_fixer_none.jsonl --agent-text "You fix one issue" --request-index -1 >> results/render_31b_vs_12b.jsonl
fi

$PY_AUTOGEN tools/autogen_adapter.py --out results/autogen_rr.json --port 8030
python3 tools/make_report.py --out paper/TABLES.md
python3 tools/check_expectations.py --expect expected/expectations.json
