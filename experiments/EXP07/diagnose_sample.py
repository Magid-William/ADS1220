#!/usr/bin/env python3
"""EXP07 - why sample.txt looks 'noisy with a steady-rate peak', and how to clean it.

Reads the console capture, then emits a three-panel diagnosis SVG:
  A) 0.4 s zoom: the 5-sample (40 ms) repeat that makes the peaks recur
  B) amplitude spectrum: the 50 Hz mains component that drives it
  C) full record: raw vs a 40 ms boxcar average (= two 50 Hz cycles) - the fix

Usage:
    python experiments/EXP07/diagnose_sample.py experiments/EXP07/exp07-sample.log
"""

import argparse
import importlib.util
import math
import os
import re
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "plot_sample", os.path.join(HERE, "plot_sample.py"))
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)

LINE_RE = re.compile(
    r"^\[(\d+):(\d+):(\d+)\.(\d+),(\d+)\]\s+<(\w+)>\s+([\w:]+):\s+(.*)$")
XY_RE = re.compile(r"XY\s+(\d+)\s+(-?\d+)\s+(-?\d+)")


def load(path):
    t, xs, ys = [], [], []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = LINE_RE.match(line.rstrip("\n"))
            if not m:
                continue
            q = XY_RE.search(m.group(8))
            if q:
                t.append(int(q.group(1)))
                xs.append(int(q.group(2)))
                ys.append(int(q.group(3)))
    return t, xs, ys


def boxcar(v, w):
    return [sum(v[i:i + w]) / w for i in range(0, len(v) - w + 1)]


def movavg(v, w):
    h = w // 2
    return [sum(v[max(0, i - h):min(len(v), i + h + 1)])
            / (min(len(v), i + h + 1) - max(0, i - h)) for i in range(len(v))]


def spectrum(v, fs):
    N = len(v)
    m = sum(v) / N
    win = [0.5 - 0.5 * math.cos(2 * math.pi * i / (N - 1)) for i in range(N)]
    x = [(v[i] - m) * win[i] for i in range(N)]
    out = []
    for k in range(1, N // 2 + 1):
        re_ = sum(x[i] * math.cos(2 * math.pi * k * i / N) for i in range(N))
        im_ = sum(x[i] * math.sin(2 * math.pi * k * i / N) for i in range(N))
        out.append((k * fs / N, 2 * math.hypot(re_, im_) / N))
    return out


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("logfile")
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()
    outdir = args.outdir or os.path.dirname(os.path.abspath(args.logfile))
    stem = os.path.splitext(os.path.basename(args.logfile))[0]

    t, xs, ys = load(args.logfile)
    n = len(t)
    dt = st.median(b - a for a, b in zip(t, t[1:]))
    fs = 1000.0 / dt
    t0 = t[0]

    # zoom window: the 50-sample stretch with the widest swing
    W50 = 50
    best, bs = -1, 0
    for s in range(0, n - W50):
        rng = max(xs[s:s + W50]) - min(xs[s:s + W50])
        if rng > best:
            best, bs = rng, s

    sx = spectrum(xs, fs)
    sy = spectrum(ys, fs)
    bw = 5
    ax, ay = boxcar(xs, bw), boxcar(ys, bw)
    at = t[bw // 2: bw // 2 + len(ax)]

    rep = []
    rep.append(f"# EXP07 diagnosis - {os.path.basename(args.logfile)}")
    rep.append(f"samples {n}, {dt:.0f} ms poll -> fs={fs:.0f} Hz, "
               f"span {(t[-1]-t[0])/1000:.2f} s")
    for nm, sp in (("x", sx), ("y", sy)):
        top = sorted(sp, key=lambda kv: -kv[1])[:3]
        rep.append(f"  {nm} strongest components: "
                   + ", ".join(f"{f:.2f} Hz (amp {a:.0f})" for f, a in top))
    rep.append("  -> 50.0 Hz = mains hum; at fs=125 Hz it repeats exactly every "
               "5 samples (2 cycles per 5 samples = 40 ms)")
    for nm, v in (("x", xs), ("y", ys)):
        sam = sum(1 for i in range(n - 5) if abs(v[i] - v[i + 5]) < 200000)
        rep.append(f"  {nm}: |v[i]-v[i+5]| < 200k in {sam}/{n-5} samples "
                   f"({100*sam/(n-5):.0f}%) -> the 40 ms repeat")
    r = ps.pearson(list(zip(ax, ay)))
    rep.append(f"  after the 40 ms boxcar: r(x,y) = {r:+.2f} "
               f"(the two axes move together at low frequency)")
    report = "\n".join(rep)
    print(report)
    with open(os.path.join(outdir, f"{stem}-diagnosis.txt"), "w",
              encoding="utf-8") as fh:
        fh.write(report + "\n")

    # ---- SVG ---------------------------------------------------------------
    W = 1040
    pad_l, pad_r, pad_t = 76, 24, 92
    plot_w = W - pad_l - pad_r
    ph = 196
    A, B, C = pad_t, pad_t + ph + 78, pad_t + 2 * (ph + 78)
    H = C + ph + 64

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}">',
             f'<rect width="{W}" height="{H}" fill="#fff"/>',
             f'<text x="{pad_l}" y="22" font-family="sans-serif" font-size="15" '
             f'font-weight="700" fill="#111">EXP07 - why the trace is noisy and '
             f'what the steady-rate peaks are</text>',
             f'<text x="{pad_l}" y="38" font-family="sans-serif" font-size="11" '
             f'fill="#666">{n} raw samples at {dt:.0f} ms ({fs:.0f} Hz), '
             f'{os.path.basename(args.logfile)}</text>']

    zooms = [(t[i], xs[i]) for i in range(bs, bs + W50)]
    zoome = [(t[i], ys[i]) for i in range(bs, bs + W50)]
    grid = [t[i] for i in range(bs, bs + W50, 5)]
    ps.line_panel(parts, zooms[0][0], zooms[-1][0], A, ph, pad_l, plot_w,
                  "A  Zoom of 0.40 s: the pattern repeats every 5 samples "
                  "(dashed lines = 40 ms)",
                  [("#1565c0", "raw x", zooms), ("#c62828", "raw y", zoome)],
                  "raw counts", vgrid=grid,
                  x_label="t (s from start of capture)")

    ps.line_panel(parts, 0.0, fs / 2, B, ph, pad_l, plot_w,
                  "B  Amplitude spectrum: the energy is at ~50 Hz mains "
                  "(and its 25 Hz half)",
                  [("#1565c0", "x", sx), ("#c62828", "y", sy)],
                  "amplitude (counts)", y_lo=0, draw_zero=False,
                  xticks=[0, 10, 20, 30, 40, 50, 60],
                  xfmt=lambda f: f"{f:.0f}", x_label="frequency (Hz)",
                  markers=[(50.0, ""), (25.0, "")])

    ps.line_panel(parts, t0, t[-1], C, ph, pad_l, plot_w,
                  "C  Same record after a 40 ms boxcar average (= 2 mains "
                  "cycles): the 50/25 Hz peaks are gone, the slow motion remains",
                  [("#9e9e9e", "raw x", [(a, b) for a, b in zip(t, xs)], 0.7, 0.45),
                   ("#1565c0", "avg x (40 ms)", [(a, b) for a, b in zip(at, ax)], 1.8, 1.0),
                   ("#f0a0a0", "raw y", [(a, b) for a, b in zip(t, ys)], 0.7, 0.45),
                   ("#c62828", "avg y (40 ms)", [(a, b) for a, b in zip(at, ay)], 1.8, 1.0)],
                  "raw counts")
    parts.append('</svg>')

    svg = os.path.join(outdir, f"{stem}-diagnosis.svg")
    with open(svg, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    print(f"\nwrote {os.path.join(outdir, stem + '-diagnosis.txt')}")
    print(f"wrote {svg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
