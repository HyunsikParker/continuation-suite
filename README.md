# continuation-suite

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
| `tools/make_suite_cases.py` | writes the 30 suite cases (routing, history, delegation, rendering, regressions, overlays) |
| `tools/nudge_probe.py` | runs cases through the official `swegemma eval` CLI with the subprocess sandbox |
| `tools/render_check.py` | renders captured requests with a Gemma 4 chat template and reports which reasoning markers survive |
| `tools/make_overlay.py` | optional harness-side diagnostics built from your own installed swegemma (nothing of it is shipped) |
| `tools/autogen_adapter.py` | AutoGen RoundRobinGroupChat scenarios RR0-RR5 driven by the same stub |
| `tools/replay_nudge.py` | replays captured post-continuation requests against a real OpenAI-compatible model server |
| `tools/make_report.py` | regenerates every table from saved results; `tools/make_figure1.py` draws Figure 1 |
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
On an Apple M4 Mac mini two clean runs took 250 and 319 seconds: about three minutes for the 30 ADK cases (roughly six seconds
each, including sandbox setup), the rest for 21 template renders and the AutoGen scenarios, ending with 0 failing
checks out of 61.

## Oracles

`tools/check_expectations.py` compares the observed results with `expected/expectations.json` and exits non-zero on
any mismatch: per case, the model-request order by agent, the number of continuation messages, the verification
result, the patch hash, and that no request reached an agent the stage-keyed script does not name (30 checks); the
markers in the fixer's request after a continuation message under `include_contents: none` and the default (2); every
saved render, 31B and 12B templates, diagnostics and the thinking-off control (21), plus a completeness check that
all expected renders are present (1); and the AutoGen request order with the saved `next_speaker_index` (7).
A stub request from an unnamed agent is answered "Done." and flagged, so it fails its case.

## Adding a case or a framework

A case is one entry in the list written by `tools/make_suite_cases.py`: a bundle, optional file overrides, the task
id, and a script. Scripts keyed by agent (`{"by_agent": {"<text in that agent's system prompt>": [steps]}}`) let each
agent follow its own steps, so the framework, not the script, decides who runs next. Add the expected outcome under
`cases` in `expected/expectations.json`. A new framework needs an adapter that drives its native resume or continue
API against the stub and records the same fields as `tools/autogen_adapter.py`: stop point, receiver, offered tools,
request history and outcome.

## Reading the results

A case is one scripted execution on one task; the stub decides every action, so the suite shows how the harness,
the framework and the template handle messages, not how often a real model takes a given path. Real-model replays
(`results/replay_*`) are separate samples: 140 generations of Gemma 4 12B QAT produced no call to an undeclared tool.
The overlays (`cb`, `salvage`) are diagnostics of where a failure chain can be cut; submissions cannot enable them.

Known harness reports this suite reproduces as credited regression cases: an undeclared tool call ends the task
(https://www.kaggle.com/competitions/gemma-4-developer-agent/discussion/745028) and generic exceptions skip the
working-tree fallback (https://www.kaggle.com/competitions/gemma-4-developer-agent/discussion/744692).

## License

Apache License 2.0.
