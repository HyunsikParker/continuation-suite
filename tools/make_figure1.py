"""Draw Figure 1 (matched AgentTool runs, skip_summarization true vs false) as SVG; render PNG with rsvg-convert.

usage: python3 tools/make_figure1.py --out paper/figure1.svg [--png paper/figure1.png]

All content mirrors measured results (results/fx_suite.json, results/render_31b_vs_12b.jsonl): three analyzer
calls, one harness continuation per delegation when skip_summarization is true, none when false; in the request that
returns the edit, reasoning r0-r2 is in the HTTP history in both runs and in the default rendering only when false.
"""

import argparse
import subprocess
from pathlib import Path

INK, MUTED, LINE, ACCENT, ACCENT_BG, PAPER = "#1a1a1a", "#5f5f5f", "#9a9a9a", "#b4442b", "#f6e3dc", "#ffffff"
FONT = "Helvetica, Arial, sans-serif"
BW, BH, GAP = 74, 48, 9


def box(x, y, kind, lines, tag=""):
    style = {"user": (PAPER, LINE, "0"), "root": (PAPER, INK, "0"), "tool": (PAPER, MUTED, "4 3"),
             "harness": (ACCENT_BG, ACCENT, "0"), "pass": (INK, INK, "0")}[kind]
    fill, stroke, dash = style
    color = PAPER if kind == "pass" else (ACCENT if kind == "harness" else INK)
    out = [f'<rect x="{x}" y="{y}" width="{BW}" height="{BH}" rx="4" fill="{fill}" stroke="{stroke}" '
           f'stroke-width="1.4" stroke-dasharray="{dash}"/>']
    for i, ln in enumerate(lines):
        ty = y + BH / 2 + (i - (len(lines) - 1) / 2) * 13 + 4
        out.append(f'<text x="{x + BW / 2}" y="{ty}" text-anchor="middle" font-size="11.5" fill="{color}">{ln}</text>')
    if tag:
        out.append(f'<rect x="{x + BW - 22}" y="{y - 9}" width="22" height="15" rx="3" fill="{PAPER}" stroke="{INK}" stroke-width="1"/>'
                   f'<text x="{x + BW - 11}" y="{y + 2}" text-anchor="middle" font-size="10" fill="{INK}">{tag}</text>')
    return "".join(out)


def lane(y, skip):
    steps = [("user", ["task"], "")]
    for k in range(3):
        steps.append(("root", ["root calls", "analyzer"], f"r{k}"))
        steps.append(("tool", ["analyzer", "reply"], ""))
        if skip:
            steps.append(("harness", ["harness", "“continue”"], ""))
    steps += [("root", ["root", "edits"], "r8"), ("root", ["root", "submits"], "r9"), ("pass", ["tests", "pass"], "")]
    x0 = 20
    parts, xs = [], []
    for i, (kind, lines, tag) in enumerate(steps):
        x = x0 + i * (BW + GAP)
        xs.append((x, kind))
        parts.append(box(x, y, kind, lines, tag))
        if i:
            parts.append(f'<line x1="{x - GAP}" y1="{y + BH / 2}" x2="{x}" y2="{y + BH / 2}" stroke="{LINE}" stroke-width="1.2"/>')
    if skip:  # counter annotations: each continuation sets the count to 1, the next tool-bearing turn resets it
        for i, (x, kind) in enumerate(xs):
            if kind == "harness":
                parts.append(f'<text x="{x + BW / 2}" y="{y + BH + 17}" text-anchor="middle" font-size="10.5" fill="{ACCENT}">count 1</text>')
                nx = xs[i + 1][0]
                parts.append(f'<text x="{nx + BW / 2}" y="{y + BH + 17}" text-anchor="middle" font-size="10.5" fill="{MUTED}">reset 0</text>')
            if kind == "tool":
                parts.append(f'<line x1="{x + BW + GAP / 2}" y1="{y - 6}" x2="{x + BW + GAP / 2}" y2="{y + BH + 6}" stroke="{INK}" stroke-width="1.6"/>')
    label = "skip_summarization: true" if skip else "skip_summarization: false"
    note = ("each analyzer reply ends the root turn, so the harness adds a user turn" if skip
            else "the root keeps its turn after each reply; the harness sends nothing")
    parts.append(f'<text x="20" y="{y - 22}" font-size="13" font-weight="bold" fill="{INK}">{label}'
                 f'<tspan dx="14" font-weight="normal" font-size="11" fill="{MUTED}">{note}</tspan></text>')
    return "".join(parts), xs[-1][0] + BW


def panel(y):
    cols = [(20, ""), (250, "HTTP request history"), (430, "rendered prompt, default"),
            (630, "rendered, continuation messages removed"), (900, "rendered, preserve_thinking")]
    out = [f'<line x1="20" y1="{y - 34}" x2="1080" y2="{y - 34}" stroke="{LINE}" stroke-width="1"/>',
           f'<text x="20" y="{y - 8}" font-size="13" font-weight="bold" fill="{INK}">Locally rendered pre-edit root prompt'
           f'<tspan dx="14" font-weight="normal" font-size="11" fill="{MUTED}">official 31B template, enable_thinking on, synthetic markers r0-r2</tspan></text>']
    for x, head in cols[1:]:
        out.append(f'<text x="{x}" y="{y + 18}" font-size="11" fill="{MUTED}">{head}</text>')
    rows = [("skip_summarization: true", ["r0 r1 r2", "none", "r0 r1 r2", "r0 r1 r2"]),
            ("skip_summarization: false", ["r0 r1 r2", "r0 r1 r2", "r0 r1 r2", "r0 r1 r2"])]
    for j, (lab, vals) in enumerate(rows):
        ry = y + 46 + j * 28
        out.append(f'<text x="20" y="{ry}" font-size="12" fill="{INK}">{lab}</text>')
        for (x, _), v in zip(cols[1:], vals):
            col = ACCENT if v == "none" else INK
            weight = "bold" if v == "none" else "normal"
            out.append(f'<text x="{x}" y="{ry}" font-size="12" font-weight="{weight}" fill="{col}">{v}</text>')
    out.append(f'<text x="20" y="{y + 110}" font-size="10.5" fill="{MUTED}">The three analyzer replies (ordinary content) render in every cell. '
               f'Both runs return the same patch, which passes verification.</text>')
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--png", default="")
    args = ap.parse_args()
    top, right1 = lane(100, True)
    bottom, right2 = lane(235, False)
    width = max(right1, right2) + 20
    lx, ly = 20, 322  # legend
    legend_items = (f'<rect x="{lx}" y="{ly - 11}" width="16" height="14" rx="2" fill="{ACCENT_BG}" stroke="{ACCENT}"/>'
                    f'<text x="{lx + 22}" y="{ly}" font-size="10.5" fill="{MUTED}">harness user turn</text>'
                    f'<line x1="{lx + 140}" y1="{ly - 12}" x2="{lx + 140}" y2="{ly + 3}" stroke="{INK}" stroke-width="1.6"/>'
                    f'<text x="{lx + 148}" y="{ly}" font-size="10.5" fill="{MUTED}">root turn ends</text>'
                    f'<rect x="{lx + 250}" y="{ly - 11}" width="22" height="14" rx="3" fill="{PAPER}" stroke="{INK}"/>'
                    f'<text x="{lx + 261}" y="{ly}" text-anchor="middle" font-size="9.5" fill="{INK}">r0</text>'
                    f'<text x="{lx + 280}" y="{ly}" font-size="10.5" fill="{MUTED}">reasoning written at that step</text>'
                    f'<text x="{lx + 470}" y="{ly}" font-size="10.5" fill="{MUTED}">count: consecutive continuation messages (limit 3); a tool-bearing turn resets it</text>')
    body = top + bottom + legend_items + panel(392)
    legend = (f'<text x="20" y="34" font-size="15" font-weight="bold" fill="{INK}">Figure 1. A valid delegation pattern changes which reasoning survives local rendering</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="525" viewBox="0 0 {width} 525" '
           f'font-family="{FONT}"><rect width="100%" height="100%" fill="{PAPER}"/>{legend}{body}</svg>')
    Path(args.out).write_text(svg)
    if args.png:
        subprocess.run(["rsvg-convert", "-z", "2", "-o", args.png, args.out], check=True)
    print(width, "px wide")


if __name__ == "__main__":
    main()
