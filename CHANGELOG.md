# Changelog

## 1.2.0 - 2026-10-25

- Add `tools/continuation_triggers.py` and `tools/undeclared_calls.py`, which count continuation messages by trigger
  and tool calls that name undeclared tools in recorded official-harness runs, and their per-run counts for 525 Kaggle
  runs of Gemma 4 12B in two jobs (14 and 25 October 2026), `results/p1_continuations_20261025.csv` and
  `results/p1_tool_calls_20261025.csv` (README, "Continuation triggers in official-harness runs").
- Add the case `route_seq_length`, in which the fixer's turn ends at the output-token limit: text steps of
  `tools/stub_model_server.py` accept `"finish": "length"`, `tools/check_expectations.py` also compares the opening of
  each continuation message when an expectation lists `nudge_heads`, and both expectation files and
  `tools/make_report.py` include the case. The suite now has 31 cases and 62 checks.
- `results/builds/swegemma-0.2.10/` and `results/builds/swegemma-0.2.11/` now hold release 1.2.0 runs: 56 of 62 pinned
  checks (the same six failures as 1.1.0) and 62 of 62 with `expected/expectations_swegemma-0.2.10.json`.

The 30 earlier cases, history checks, renders, AutoGen scenarios and replay results are unchanged from v1.1.0.

## 1.1.0 - 2026-10-13

- Add `expected/expectations_swegemma-0.2.10.json`, the oracle for the official wheelhouse of 8 October 2026
  (adk_submission 0.2.13, swegemma 0.2.10), and let `run_all.sh` select an oracle with `EXPECT`.
- Add `tools/compare_builds.py`, which compares two runs case by case.
- Fix a fresh clone stopping at its first step: `tools/make_suite_cases.py` now creates the untracked `probes/`
  directory. Releases 1.0.0 to 1.0.2 ran only from a working copy that already had it.
- Add `results/builds/swegemma-0.2.10/`: case results of that build and the oracle output against the pinned and the
  new expectations (55 of 61 and 61 of 61).
- Add `results/builds/swegemma-0.2.11/` for the wheelhouse of 12 October 2026 (swegemma 0.2.11): all 30 case results
  equal those of 0.2.10, so the 0.2.10 expectations apply (55 of 61 pinned, 61 of 61).

The pinned expectations, cases, renders and replay results are unchanged from v1.0.2.

## 1.0.2 - 2026-10-11

- Add `tools/notebook_survey.py`, which counts agent-configuration settings in a directory of pulled Kaggle
  notebooks, and `results/notebook_survey_20261011.csv`, the per-notebook flags behind the counts in the writeup.

Suite cases, renders and replay results are unchanged from v1.0.1.

## 1.0.1 - 2026-10-08

- Fail `run_all.sh` when `TOKENIZER_DIR` or `TEMPLATE` is missing instead of silently omitting template renders.
- Count missing oracle inputs reported as `SKIP` as failures.
- Record the effective chat-template SHA-256 in every render row.
- Add known model, server, sampling and history provenance to the archived Gemma 4 12B replay results.

Measured case outcomes, marker sets and replay counts are unchanged from v1.0.0.

## 1.0.0 - 2026-10-07

- Initial release of the continuation test suite and saved paper results.
