---
name: scout
description: Fast read-only helpers for the repository in /workspace. locate.py ranks the functions and classes most related to the issue text; show.py prints one definition with line numbers; tests.py lists existing tests that mention a name; check.py compiles changed files and runs targeted pytest with the grader's flags.
---
# scout

Call these with `run_skill_script`, `skill_name` = `scout`, and `args` as a mapping of option name to value. Each finishes in seconds and prints a short result. None of them edits files.

- `scripts/locate.py` with `{"query": "<issue title, key sentences, identifiers and error text>"}` ranks the definitions most related to the issue and shows exact-text hits for quoted strings and error messages. Use it once, first.
- `scripts/show.py` with `{"name": "Class.method"}` (optionally `"path": "pkg/module.py"`) prints that definition with line numbers. Copy only the text after the tab into `edit_file`'s `old_string`.
- `scripts/tests.py` with `{"name": "<function, class or module name>"}` lists existing test files and test ids that mention it.
- `scripts/check.py` with `{"files": "<changed files, comma separated>", "tests": "<pytest targets, space separated>"}` compiles the files and runs those tests (stops at the first failure). Omit `files` to check every changed file. Add `"k": "<expr>"` to narrow tests.
