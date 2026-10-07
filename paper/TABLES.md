# Tables generated from saved traces

Fixture check: no-op edit -> patch kept, tests fail (237 B); repair -> resolved (patch sha 53b22d19).

## Who receives the continuation

| configuration | request order (agent per model call) | nudges | outcome |
|---|---|---|---|
| SequentialAgent, fixer owns submit_patch | locator fixer fixer locator | 1 | lost (Tool 'submit_patch' not found.) |
| SequentialAgent, both own submit_patch | locator fixer fixer locator locator | 1 | resolved |
| LlmAgent + transfer, fixer answered last, fixer owns | coordinator locator fixer fixer fixer fixer | 1 | resolved |
| LlmAgent + transfer, locator answered last, fixer owns | coordinator locator fixer fixer locator locator | 1 | lost (Tool 'submit_patch' not found.) |
| LlmAgent + transfer, locator answered last, both own | coordinator locator fixer fixer locator locator locator | 1 | resolved |
| SequentialAgent, cut-off nudge names edit_file | locator fixer fixer locator | 1 | lost (Tool 'edit_file' not found.) |
| LoopAgent (2 iterations), text end | locator fixer fixer locator fixer locator fixer locator fixer locator fixer locator fixer locator fixer locator fixer | 3 | resolved |
| LlmAgent root + AgentTool analyzer | swe_fixer code_analyzer swe_fixer swe_fixer swe_fixer swe_fixer | 2 | resolved |

## Valid delegation across the nudge limit

| skip_summarization | analyzer calls N | nudges | outcome |
|---|---|---|---|
| true | 2 | 2 | resolved |
| true | 3 | 3 | resolved |
| true | 4 | 4 | resolved |
| true | 6 | 6 | resolved |
| false | 2 | 0 | resolved |
| false | 3 | 0 | resolved |
| false | 4 | 0 | resolved |
| false | 6 | 0 | resolved |

## Reasoning visibility at the template

| template | run | request | condition | reasoning in raw history | reasoning rendered | analyzer reports rendered |
|---|---|---|---|---|---|---|
| 31B (official) | skip true | pre-action | default | 0,1,2 | none | 3/3 |
| 31B (official) | skip true | pre-action | preserve_thinking | 0,1,2 | 0,1,2 | 3/3 |
| 31B (official) | skip true | pre-action | nudges removed | 0,1,2 | 0,1,2 | 3/3 |
| 31B (official) | skip true | last | default | 0,1,2,8,9 | 8,9 | 3/3 |
| 31B (official) | skip true | last | preserve_thinking | 0,1,2,8,9 | 0,1,2,8,9 | 3/3 |
| 31B (official) | skip true | last | nudges removed | 0,1,2,8,9 | 0,1,2,8,9 | 3/3 |
| 31B (official) | skip false | pre-action | default | 0,1,2 | 0,1,2 | 3/3 |
| 31B (official) | skip false | pre-action | preserve_thinking | 0,1,2 | 0,1,2 | 3/3 |
| 31B (official) | skip false | pre-action | nudges removed | 0,1,2 | 0,1,2 | 3/3 |
| 31B (official) | skip false | last | default | 0,1,2,8,9 | 0,1,2,8,9 | 3/3 |
| 31B (official) | skip false | last | preserve_thinking | 0,1,2,8,9 | 0,1,2,8,9 | 3/3 |
| 31B (official) | skip false | last | nudges removed | 0,1,2,8,9 | 0,1,2,8,9 | 3/3 |
| 12B | skip true | pre-action | default | 0,1,2 | none | 3/3 |
| 12B | skip true | pre-action | nudges removed | 0,1,2 | 0,1,2 | 3/3 |
| 12B | skip true | last | default | 0,1,2,8,9 | 8,9 | 3/3 |
| 12B | skip true | last | nudges removed | 0,1,2,8,9 | 0,1,2,8,9 | 3/3 |
| 12B | skip false | pre-action | default | 0,1,2 | 0,1,2 | 3/3 |
| 12B | skip false | pre-action | nudges removed | 0,1,2 | 0,1,2 | 3/3 |
| 12B | skip false | last | default | 0,1,2,8,9 | 0,1,2,8,9 | 3/3 |
| 12B | skip false | last | nudges removed | 0,1,2,8,9 | 0,1,2,8,9 | 3/3 |

## AutoGen RoundRobin native resumption

| scenario | model-request order | receiver of the continuation | its tools |
|---|---|---|---|
| RR0_baseline | L F L | - | - |
| RR1_resume_after_L | L F | F | inspect_fixture, finish_fixture |
| RR2_resume_after_F | L F L | L | inspect_fixture |
| RR3_fresh_team | L | L | inspect_fixture |
| RR4_repeated | L F L F L | - | - |
| RR5_nudge_after_L | L F | F | inspect_fixture, finish_fixture |
| RR5_nudge_after_F | L F L | L | inspect_fixture |

## Gemma 4 12B replays of captured post-nudge requests

| replay set | histories | wording | generations | undeclared-tool calls |
|---|---|---|---|---|
| trap context | 1 | harness | 20 | 0 |
| trap context | 1 | neutral | 20 | 0 |
| normal nudge | 10 | orig | 20 | 0 |
| normal nudge | 10 | neutral | 20 | 0 |
| cut-off nudge | 10 | orig | 20 | 0 |
| cut-off nudge | 10 | cutoff_neutral | 20 | 0 |
| normal nudge, thinking on | 10 | orig | 10 | 0 |
| normal nudge, thinking on | 10 | neutral | 10 | 0 |
