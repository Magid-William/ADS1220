#!/usr/bin/env python3
"""EXP08 - time-series plot of the read-fixed X/Y captures.

Plots the paired `XY <ms> <x> <y>` lines plus the `### phase:` markers from one
or more console captures into a single SVG. Reuses the panel renderer from
experiments/EXP07/plot_sample.py (stdlib only - no matplotlib here).

Usage:
    python experiments/EXP08/plot_captures.py \
        experiments/EXP08/exp08-gain1-rest.log \
        experiments/EXP08/exp08-gain1-circle.log
"""

import argparse
import importlib.util
import os
import re
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "plot_sample", os.path.join(HERE, "..", "EXP07", "plot_sample.py"))
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)

XY_RE = re.compile(r"XY\s+(\d+)\s+(-?\d+)\s+(-?\d+)")
PHASE_RE = re.compile(r"### phase:\s*(cue|stop)\s*'([^']*)'")


def load(path):
    """-> (samples[(t,x,y)], markers[(n_samples_so_far, kind, text)])"""
    samples, markers = [], []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            q = XY_RE.search(line)
            if q:
                samples.append((int(q.group(1)), int(q.group(2)), int(q.group(3))))
                continue
            p = PHASE_RE.search(line)
            if p:
                markers.append((len(samples), p.group(1), p.group(2)))
    return samples, markers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--out", default=os.path.join(HERE, "exp08-timeseries.svg"))
    args = ap.parse_args()

    captures = []
    for path in args.logs:
        s, m = load(path)
        if not s:
            print(f"WARNING: no XY samples in {path}")
            continue
        captures.append((os.path.basename(path), s, m))
    if not captures:
        print("ERROR: nothing to plot")
        return 1

    allv = [v for _, s, _ in captures for r in s for v in (r[1], r[2])]
    y_lo, y_hi = min(allv), max(allv)
    pad = (y_hi - y_lo) * 0.06
    y_lo, y_hi = y_lo - pad, y_hi + pad

    W = 1040
    pad_l, pad_r, pad_t = 84, 24, 136
    plot_w = W - pad_l - pad_r
    ph, gap = 232, 88
    H = pad_t + len(captures) * (ph + gap) + 24

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}">',
        f'<rect width="{W}" height="{H}" fill="#fff"/>',
        f'<text x="{pad_l}" y="24" font-family="sans-serif" font-size="15" '
        f'font-weight="700" fill="#111">EXP08 - read-fixed raw X/Y time series '
        f'(gain 1, 4-byte RDATA, hi==mid ~0.3%)</text>',
        f'<text x="{pad_l}" y="42" font-family="sans-serif" font-size="11" '
        f'fill="#666">paired XY logger at ~125 Hz; y-scale shared across panels '
        f'so amplitudes are comparable</text>',
        f'<text x="{pad_l}" y="58" font-family="sans-serif" font-size="11" '
        f'fill="#666">orange dashed lines = phase markers (cue / stop)</text>',
    ]

    for i, (name, s, markers) in enumerate(captures):
        t = [r[0] for r in s]
        X = [r[1] for r in s]
        Y = [r[2] for r in s]
        t0, t1 = t[0], t[-1]
        title = (f"{name}   -   {len(s)} samples, {(t1-t0)/1000:.1f} s   "
                 f"x sd {st.pstdev(X):.0f}  y sd {st.pstdev(Y):.0f}   "
                 f"x mean {st.mean(X):.0f}  y mean {st.mean(Y):.0f}")
        pm = [(s[idx][0], f"{kind}") for idx, kind, _ in markers if idx < len(s)]
        ps.line_panel(
            parts, t0, t1, pad_t + i * (ph + gap), ph, pad_l, plot_w, title,
            [("#1565c0", "raw x", list(zip(t, X)), 1.0, 1.0),
             ("#c62828", "raw y", list(zip(t, Y)), 1.0, 1.0)],
            "raw counts", y_lo=y_lo, y_hi=y_hi, draw_zero=False, markers=pm)
    parts.append('</svg>')

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))

    print(f"{'capture':<24}{'n':>6}{'dur_s':>8}   "
          f"{'x min':>10}{'x max':>11}{'x mean':>10}{'x sd':>9}   "
          f"{'y min':>10}{'y max':>11}{'y mean':>10}{'y sd':>9}")
    for name, s, _ in captures:
        t = [r[0] for r in s]
        X = [r[1] for r in s]
        Y = [r[2] for r in s]
        print(f"{name:<24}{len(s):>6}{(t[-1]-t[0])/1000:>8.1f}   "
              f"{min(X):>10}{max(X):>11}{st.mean(X):>10.0f}{st.pstdev(X):>9.0f}   "
              f"{min(Y):>10}{max(Y):>11}{st.mean(Y):>10.0f}{st.pstdev(Y):>9.0f}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
