"""Build the distributable synthetic task used by the continuation test suite (no competition data).

usage: python3 tools/make_fixture.py --out fixtures

Creates fixtures/snapshots/tinytable_0001.tgz (a git repository at its base commit) and fixtures/tasks.jsonl with
one task in the harness's task format: the base test passes, the added test fails until the one-line repair is
applied, mirroring a public-task bug shape (a column created by add_row ignores the table-level highlight flag).
Commits use a fixed author and date, so the base commit hash is reproducible.
"""

import argparse
import json
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

PYPROJECT = """[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "tinytable"
version = "0.1.0"
requires-python = ">=3.9"

[tool.setuptools]
packages = ["tinytable"]
"""

INIT = '''from .table import Column, Table

__all__ = ["Column", "Table"]
'''

TABLE = '''class Column:
    """One column of a table: a header, a highlight flag and its cells."""

    def __init__(self, header: str = "", highlight: bool = False) -> None:
        self.header = header
        self.highlight = highlight
        self.cells: list[str] = []


class Table:
    """A minimal text table. Rows may be longer than the header; extra cells create new columns."""

    def __init__(self, *headers: str, highlight: bool = False) -> None:
        self.highlight = highlight
        self.columns = [Column(header, highlight=highlight) for header in headers]
        self.row_count = 0

    def add_row(self, *cells: str) -> None:
        for index, cell in enumerate(cells):
            if index == len(self.columns):
                column = Column()
                for _ in range(self.row_count):
                    column.cells.append("")
                self.columns.append(column)
            self.columns[index].cells.append(cell)
        for column in self.columns[len(cells):]:
            column.cells.append("")
        self.row_count += 1

    def render(self) -> str:
        lines = []
        for row in range(self.row_count):
            parts = []
            for column in self.columns:
                text = column.cells[row]
                parts.append(f"*{text}*" if column.highlight and text else text)
            lines.append(" | ".join(parts))
        return "\\n".join(lines)
'''

BASE_TEST = '''from tinytable import Table


def test_render_basic():
    table = Table("a", "b")
    table.add_row("1", "2")
    assert table.render() == "1 | 2"
'''

ADDED_TEST = '''

def test_add_row_new_column_inherits_highlight():
    table = Table("a", highlight=True)
    table.add_row("1", "2")
    assert [column.highlight for column in table.columns] == [True, True]
    assert table.render() == "*1* | *2*"
'''

PROBLEM = """Columns created by add_row ignore the table's highlight setting

When a row has more cells than the table has columns, Table.add_row creates the missing columns. Those new
columns are never highlighted, even when the table was created with highlight=True, so render() highlights only
the original columns. New columns should follow the table's highlight setting.
"""

ENV = {**os.environ, "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
       "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
       "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, env=ENV, check=True, capture_output=True, text=True).stdout


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="fixtures")
    args = ap.parse_args()
    out = Path(args.out)
    (out / "snapshots").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "tinytable"
        (repo / "tinytable").mkdir(parents=True)
        (repo / "tests").mkdir()
        (repo / "pyproject.toml").write_text(PYPROJECT)
        (repo / "tinytable" / "__init__.py").write_text(INIT)
        (repo / "tinytable" / "table.py").write_text(TABLE)
        (repo / "tests" / "test_table.py").write_text(BASE_TEST)
        git(repo, "init", "-q", "-b", "main")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "tinytable base")
        base = git(repo, "rev-parse", "HEAD").strip()
        # gold patch and test patch as unified diffs against the base commit
        table = repo / "tinytable" / "table.py"
        table.write_text(TABLE.replace("column = Column()\n", "column = Column(highlight=self.highlight)\n"))
        patch = git(repo, "diff")
        git(repo, "checkout", "-q", "--", ".")
        test = repo / "tests" / "test_table.py"
        test.write_text(BASE_TEST + ADDED_TEST)
        test_patch = git(repo, "diff")
        git(repo, "checkout", "-q", "--", ".")
        with tarfile.open(out / "snapshots" / "tinytable_0001.tgz", "w:gz") as tar:
            tar.add(repo, arcname=".")
    task = {"instance_id": "tinytable_0001", "repo": "fixture/tinytable", "base_commit": base,
            "problem_statement": PROBLEM, "patch": patch, "test_patch": test_patch, "hints_text": "",
            "created_at": "2026-01-01T00:00:00Z"}
    (out / "tasks.jsonl").write_text(json.dumps(task) + "\n")
    print(base, len(patch), len(test_patch))


if __name__ == "__main__":
    main()
