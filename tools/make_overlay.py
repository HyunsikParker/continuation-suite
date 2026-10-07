"""Build the optional maintainer-side overlay from YOUR installed swegemma (nothing of swegemma is shipped here).

usage: python3 tools/make_overlay.py --site-packages <venv>/lib/python3.X/site-packages --out <overlay dir>

Copies the installed swegemma package into <overlay dir>/swegemma and inserts two switches into
harness/agent_runner.py, both off unless SWEGEMMA_PROBE_VARIANT is set when the harness runs with
PYTHONPATH=<overlay dir>:
  cb       an ADK plugin whose on_tool_error_callback returns any tool error to the model as a tool result
  salvage  in the generic exception handler, capture the working-tree diff as the patch
These are diagnostics of where the failure chain can be cut. Submissions cannot enable either.
"""

import argparse
import shutil
from pathlib import Path

HELPER = '''
# --- probe overlay (not part of the official wheel) ---
import os as _probe_os
from google.adk.plugins.base_plugin import BasePlugin as _ProbeBasePlugin


class _ToolErrorAsResult(_ProbeBasePlugin):
    def __init__(self):
        super().__init__(name='probe_tool_error_as_result')

    async def on_tool_error_callback(self, *, tool, tool_args, tool_context, error):
        return {'status': 'error', 'error': f'{type(error).__name__}: {str(error)[:300]}'}


def _probe_plugins():
    return [_ToolErrorAsResult()] if 'cb' in _probe_os.environ.get('SWEGEMMA_PROBE_VARIANT', '') else []


'''

SALVAGE = (
    "        if 'salvage' in _probe_os.environ.get('SWEGEMMA_PROBE_VARIANT', '') and not agent_patch:\n"
    "            try:\n"
    "                await sandbox_exec(docker, sandbox_id, 'cd /workspace && git add -N .')\n"
    "                _d = await sandbox_exec(docker, sandbox_id, 'cd /workspace && (git diff --binary _swegemma_baseline 2>/dev/null || git diff --binary HEAD)')\n"
    "                if (_d.stdout or '').strip():\n"
    "                    agent_patch = _d.stdout\n"
    "            except Exception:\n"
    "                pass\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-packages", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    shutil.rmtree(out / "swegemma", ignore_errors=True)
    shutil.copytree(Path(args.site_packages) / "swegemma", out / "swegemma")
    runner = out / "swegemma" / "harness" / "agent_runner.py"
    lines = runner.read_text().splitlines(keepends=True)
    # 1) plugin list: append our plugins to the list literal that holds the display and retry plugins
    i_plugins = next(i for i, ln in enumerate(lines) if ln.strip().startswith("'plugins': [") and "retry_plugin" in ln)
    lines[i_plugins] = lines[i_plugins].rstrip().rstrip(",") + " + _probe_plugins(),\n"
    # 2) salvage: after the line that records a generic sandbox execution error
    i_err = next(i for i, ln in enumerate(lines) if "Sandbox execution error" in ln and "agent_error" in ln)
    lines.insert(i_err + 1, SALVAGE)
    # 3) helper definitions before the sandbox runner function
    i_def = next(i for i, ln in enumerate(lines) if ln.startswith("async def run_agent_sandbox("))
    lines.insert(i_def, HELPER)
    runner.write_text("".join(lines))
    print("overlay written to", out)


if __name__ == "__main__":
    main()
