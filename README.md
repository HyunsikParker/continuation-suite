# continuation-suite

Release: **v1.2.0**

CPU tests for what a harness's "continue" message does inside a multi-agent coding agent: which agent receives it,
which tools that agent offers, and what history and reasoning the model then reads. Built for the Gemma 4 Developer
Agent harness (Google ADK) and checked against a second framework (AutoGen AgentChat). Companion to the paper-track
writeup "Continuation Is a Context Operation: A CPU Test Suite for Multi-Agent Harnesses".

No GPU and no model account are needed for the core suite. A scripted stub model stands in for the inference server,
records every request, and answers from per-agent scripts. It never chooses which agent runs next.

## What is here

| path | purpose |
|---|---|
| `tools/stub_model_server.py` | recording OpenAI-compatible stub; scripts can be keyed by agent (system-prompt substring) |
| `tools/make_fixture.py` | builds the synthetic task `tinytable_0001` (reproducible base commit `abc65ab1`) |
| `tools/make_suite_cases.py` | writes the 31 suite cases (routing, history, delegation, rendering, regressions, overlays) |
| `tools/nudge_probe.py` | runs cases through the official `swegemma eval` CLI with the subprocess sandbox |
| `tools/render_check.py` | renders captured requests with a Gemma 4 chat template and reports which reasoning markers survive |
| `tools/make_overlay.py` | optional harness-side diagnostics built from your own installed swegemma (nothing of it is shipped) |
| `tools/autogen_adapter.py` | AutoGen RoundRobinGroupChat scenarios RR0-RR5 driven by the same stub |
| `tools/replay_nudge.py` | replays captured post-continuation requests against a real OpenAI-compatible model server |
| `tools/make_report.py` | regenerates every table from saved results; `tools/make_figure1.py` draws Figure 1 |
| `tools/compare_builds.py` | compares two runs case by case, e.g. the suite on two harness builds |
| `tools/notebook_survey.py` | counts agent-configuration settings in pulled public competition notebooks (text only, nothing executed) |
| `tools/continuation_triggers.py` | counts continuation messages by trigger in recorded official-harness runs (see Continuation triggers) |
| `tools/undeclared_calls.py` | counts tool calls that name a tool the request did not offer, in the same recordings |
| `bundles/v4`, `v5b`, `v8` | the agent bundles used (AgentTool root, single agent, SequentialAgent pipeline) |
| `results/` | saved outputs behind the paper's tables (no prompts, no competition data) |

## Requirements and provenance

- Python 3.13 and `git`.
- The official harness wheels, which come with the competition and are not redistributed here. Tested with
  (SHA-256):
  - `google_adk-1.36.1-py3-none-any.whl` `1a2f6868c509e3151fb0de3575a7d18b45c338be86f420924dad74e7193631a0`
  - `swegemma-0.2.7-py3-none-any.whl` `27a2f60f8db46c8fef5defc16df722dac0402446c9a6252e7e6b4c280e843c81`
  - `adk_submission-0.2.12-py3-none-any.whl` `077c438c426e625b9f722081694e1d32856e6f7e932ef625002fc4a11aabdc10`
  installed into `.venv-official`.
- Rendering: `transformers` 5.6.2, `jinja2` 3.1.6, a Gemma 4 tokenizer directory (`TOKENIZER_DIR`), and the chat
  template of `google/gemma-4-31B-it-qat-w4a16-ct` (`TEMPLATE`, SHA-256
  `ae53464bf3be25802b3a5b37def7fd89667067d7577049b3b2d74c4d8de4c6d4`). The 12B comparison rows use the template that
  ships in the tokenizer directory (paper: `mlx-community/gemma-4-12B-it-qat-4bit`, SHA-256
  `36e3a42e5cf14cd0020e72d92e1fdd9970f59b82170e421f0cbe1bb42bead3f0`). The renderer deserializes tool-call arguments
  because the 31B template rejects JSON strings; the captured requests are kept unchanged.
- AutoGen part: `autogen-agentchat` 0.7.5 and `autogen-ext[openai]` 0.7.5 (`openai` 3.24.0) in `.venv-autogen`.
- The Gemma 4 12B replays (`results/replay_*`) used captured requests from public competition tasks and a local
  llama.cpp server (Gemma 4 12B QAT Q4_0, temperature 0.2, first action only). Their inputs are competition material
  and are not shipped, so these replays cannot be rerun from this release alone; the saved files list every
  generation's condition and the tool names it called.

## Run

```bash
./run_all.sh
```

The script builds the fixture, writes the cases, builds the optional overlay from your installed swegemma, runs the
suite, renders the reasoning checks, runs the AutoGen scenarios, regenerates `paper/TABLES.md`, and runs the oracles.
On an Apple M4 Mac mini two clean runs of release 1.0.0 took 250 and 319 seconds: about three minutes for the 30 ADK
cases (roughly six seconds each, including sandbox setup), the rest for 21 template renders and the AutoGen scenarios,
ending with 0 failing checks out of 61. Release 1.2.0 has 31 cases and 62 checks; its run on 25 October took 310
seconds on the same machine, with 0 failing checks.

## Oracles

`tools/check_expectations.py` compares the observed results with `expected/expectations.json` and exits non-zero on
any mismatch: per case, the model-request order by agent, the number of continuation messages, the verification
result, the patch hash, and that no request reached an agent the stage-keyed script does not name (31 checks; for
`route_seq_length` also the opening of each continuation message); the markers in the fixer's request after a
continuation message under `include_contents: none` and the default (2); every saved render, 31B and 12B templates,
diagnostics and the thinking-off control (21), plus a completeness check that all expected renders are present (1);
and the AutoGen request order with the saved `next_speaker_index` (7). A stub request from an unnamed agent is
answered "Done." and flagged, so it fails its case. Missing history, render or AutoGen artifacts are printed as `SKIP`
and count as failures. `run_all.sh` also exits before running any case unless both `TOKENIZER_DIR` and `TEMPLATE` are
set to existing local inputs. Every saved render row records the SHA-256 of the effective chat template.

## Other harness builds

`expected/expectations.json` describes the pinned build (adk_submission 0.2.12, swegemma 0.2.7). To test a later
official build, install its wheels into another virtual environment, point `.venv-official` at it, run
`./run_all.sh`, and compare the case results with `python3 tools/compare_builds.py <reference results dir> results`.

The official wheelhouse of 8 October 2026 changed two wheels (google-adk 1.36.1 is unchanged):
  - `adk_submission-0.2.13-py3-none-any.whl` `8a19afc752aa6cec4e98e25b09aa1fe4b020ad902af8f014d294c85d70247d5d`
  - `swegemma-0.2.10-py3-none-any.whl` `13261f9d5581840f7600d0d66aea10d6a3e4b53661409e072e55f253436c1252`

On that build 56 of the 62 pinned checks pass (55 of 61 with release 1.1.0, before `route_seq_length` was added). The
six failures are the cases whose pinned run ended on an undeclared or failing tool call (`submit_patch` or `edit_file`
not offered to the receiver, or a list-valued skill argument). The new build returns such errors to the model, so
these runs continue through more continuation messages and finish with the passing patch. The new build's source also
catches generic exceptions before the working-tree fallback; returned tool errors and that handler are the changes the
`cb` and `salvage` overlays made. Receivers after continuation, worker history, the reasoning markers of every render
and the AutoGen checks are unchanged; some rendered prompts are 15 tokens shorter.
`expected/expectations_swegemma-0.2.10.json` records that build's outcomes
(`EXPECT=expected/expectations_swegemma-0.2.10.json ./run_all.sh` passes all 62 checks), and
`results/builds/swegemma-0.2.10/` holds its case results and the oracle output against both files. A rerun of the
pinned build on the same day still passed all 61 pinned checks. The case added in 1.2.0, `route_seq_length`, has the
same outcome on the pinned and both October builds.

The wheelhouse of 12 October 2026 changed only swegemma (`swegemma-0.2.11-py3-none-any.whl`
`9ad876581f3acde8ec3c369858f0834e2b9f41a3cffce3ca42f09cb090aea9d3`; it adds LoRA adapter discovery and a separate
verification timeout). All 31 case results equal those of 0.2.10, so the same expectation file applies (56 of 62
pinned checks, 62 of 62 with `expected/expectations_swegemma-0.2.10.json`); see `results/builds/swegemma-0.2.11/`.

## Adding a case or a framework

A case is one entry in the list written by `tools/make_suite_cases.py`: a bundle, optional file overrides, the task
id, and a script. Scripts keyed by agent (`{"by_agent": {"<text in that agent's system prompt>": [steps]}}`) let each
agent follow its own steps, so the framework, not the script, decides who runs next. A text step with `"finish":
"length"` ends the turn as if the output-token limit had been reached (`route_seq_length`). Add the expected outcome
under `cases` in `expected/expectations.json`. A new framework needs an adapter that drives its native resume or
continue API against the stub and records the same fields as `tools/autogen_adapter.py`: stop point, receiver, offered
tools, request history and outcome.

## Reading the results

A case is one scripted execution on one task; the stub decides every action, so the suite shows how the harness,
the framework and the template handle messages, not how often a real model takes a given path. Real-model replays
(`results/replay_*`) are separate samples: 140 generations of Gemma 4 12B QAT produced no call to an undeclared tool.
The overlays (`cb`, `salvage`) are diagnostics of where a failure chain can be cut; submissions cannot enable them.

Known harness reports this suite reproduces as credited regression cases: an undeclared tool call ends the task
(https://www.kaggle.com/competitions/gemma-4-developer-agent/discussion/745028) and generic exceptions skip the
working-tree fallback (https://www.kaggle.com/competitions/gemma-4-developer-agent/discussion/744692). On the
8 October build the first no longer ends the task (see Other harness builds).

## Notebook survey

`results/notebook_survey_20261011.csv` holds one row per public notebook of the competition on 11 October 2026
(154 notebooks) with 0/1 flags for the settings the suite tests; no notebook code is included. Of the 98 notebooks
that write an agent configuration, 36 declare an AgentTool and 33 of these keep `skip_summarization: true`, the
configuration of the competition's sample submission; three use a SequentialAgent or LoopAgent root and four set
`include_contents: none`. To recount, pull the notebooks as described in `tools/notebook_survey.py` and run it.
Text matching misses settings kept in attached datasets, and copies of a notebook are counted separately.

## Continuation triggers in official-harness runs

`results/p1_continuations_20261025.csv` and `results/p1_tool_calls_20261025.csv` hold one row per run of two sampling
jobs with the official Evaluator (12 October wheelhouse) on Kaggle's 4 x L4 serving `gemma-4-12b-it-qat-w4a16-ct`: a
single-agent bundle that declares all nine harness tools (8 minutes, 28 tool calls, thinking budget 4,096, 8,192
output tokens) ran each of the 105 public tasks marked sound without a dependency repair in
`dmitriigluzdov/gemma-4-task-soundness-and-local-results` (CC BY 4.0) once per temperature. Column `source` names the
job: `kaggle_p1_full` ran on 14 October 2026 at temperatures 0.2 and 0.7 (210 runs) and `kaggle_p1_sampler_b` on
25 October at 0.4, 0.5 and 0.9 (315 runs); column `pass` gives the temperature (`t02` is 0.2). A LiteLLM callback
recorded every successful model call and the harness wrote its traces; both contain the competition tasks and are not
shipped, and the CSVs hold run ids and counts only. `tools/continuation_triggers.py` and `tools/undeclared_calls.py`
recount them from such run folders; their docstrings give the layout.

The traces record 69 continuation messages in 61 of the 525 runs, never more than two per run: 44 with the "token
limit while thinking" wording after a response stopped at the 8,192-token output limit (`finish_reason` length), 7
with the cut-off tool-call wording and 18 generic ones (14 October: 21, 1 and 6 in 23 of its 210 runs). The call log,
which keeps successful calls only, shows 61: seven of the eight it lacks were sent in runs that then ended at the
8-minute limit. 182 runs ended at the time limit, 140 at the tool-call budget and 203 without a harness error. None of
the 12,774 tool calls in the traces (12,688 in the call log, plus 20 left in the text) names an undeclared tool. With
one agent the continuation always returns to the agent that stopped, so these runs show how often and why it fires,
not where multi-agent routing sends it.

## License

Apache License 2.0.
