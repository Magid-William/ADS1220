#!/usr/bin/env python3
"""EXP07 - analyse + time-series plot of a raw ZMK 'XY' serial capture.

Unlike the EXP04 analyzer this reads a *console* capture: each line carries the
ZMK log timestamp '[HH:MM:SS.mmm,uuu]' and an '<inf> exp02_logging: XY <t> <x>
<y>' payload. Both the log clock and the firmware uptime field are kept.

Stdlib only (matplotlib/numpy are not installed here). Emits a text report and a
two-panel SVG time-series diagram:
  panel 1: raw x(t) and y(t) as recorded
  panel 2: the three bytes of each 24-bit word, to visualise the hi==mid fault

Usage:
    python experiments/EXP07/plot_sample.py experiments/EXP07/exp07-sample.log
"""

import argparse
import math
import os
import re
import statistics as st
import sys

# [00:00:06.490,509] <inf> exp02_logging: XY 6490 -4868847 -4868646
LINE_RE = re.compile(
    r"^\[(\d+):(\d+):(\d+)\.(\d+),(\d+)\]\s+<(\w+)>\s+([\w:]+):\s+(.*)$"
)
XY_RE = re.compile(r"XY\s+(\d+)\s+(-?\d+)\s+(-?\d+)")


def load(path):
    """-> list of (log_ms, level, tag, uptime_ms, x, y) for XY lines."""
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = LINE_RE.match(line.rstrip("\n"))
            if not m:
                continue
            hh, mm, ss, ms, us, level, tag, msg = m.groups()
            q = XY_RE.search(msg)
            if not q:
                continue
            log_ms = (((int(hh) * 60 + int(mm)) * 60 + int(ss)) * 1000
                      + int(ms) + int(us) / 1000.0)
            rows.append((log_ms, level, tag, int(q.group(1)),
                         int(q.group(2)), int(q.group(3))))
    return rows


def bytes_of(v):
    """24-bit two's-complement word -> (hi, mid, lo)."""
    return ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)


def hi_eq_mid(v):
    return ((v >> 16) & 0xFF) == ((v >> 8) & 0xFF)


def pearson(pairs):
    n = len(pairs)
    if n < 2:
        return 0.0
    mx = st.mean(a for a, _ in pairs)
    my = st.mean(b for _, b in pairs)
    sx = math.sqrt(sum((a - mx) ** 2 for a, _ in pairs))
    sy = math.sqrt(sum((b - my) ** 2 for _, b in pairs))
    if sx == 0 or sy == 0:
        return 0.0
    return sum((a - mx) * (b - my) for a, b in pairs) / (sx * sy)


# --------------------------------------------------------------------------- plot

def _ticks(lo, hi, n=5):
    if hi == lo:
        return [lo]
    step = (hi - lo) / n
    return [lo + i * step for i in range(n + 1)]


def _fmt(v):
    if abs(v) >= 1e6:
        return f"{v/1e6:.1f}M" if abs(v) >= 1e5 else f"{v:.0f}"
    if abs(v) >= 1e3:
        return f"{v/1e3:.0f}k"
    return f"{v:.0f}"


def line_panel(parts, x0, x1, top, height, pad_l, plot_w, title,
               series, y_label, y_lo=None, y_hi=None, markers=None,
               draw_zero=True, legend_note=None, xticks=None, xfmt=None,
               x_label="t (s from first sample)", vgrid=None):
    """Append SVG for one line-chart panel.

    series = [(color, label, pts, width, opacity)].
    xticks/xfmt/vgrid let a caller relabel the x axis (e.g. a spectrum).
    """
    pts_all = [p for _, _, data, *_ in series for p in data]
    ys = [p[1] for p in pts_all]
    if y_lo is None:
        y_lo = min(ys)
    if y_hi is None:
        y_hi = max(ys)
    if y_hi == y_lo:
        y_hi = y_lo + 1

    def px(t):
        return pad_l + (t - x0) / (x1 - x0) * plot_w

    def py(v):
        return top + height - (v - y_lo) / (y_hi - y_lo) * height

    parts.append(f'<text x="{pad_l}" y="{top-32}" font-family="sans-serif" '
                 f'font-size="13" font-weight="600" fill="#222">{title}</text>')
    # legend strip sits between the title and the plot frame
    for i, item in enumerate(series):
        color, label = item[0], item[1]
        lx = pad_l + i * 150
        parts.append(f'<line x1="{lx}" y1="{top-11}" x2="{lx+18}" '
                     f'y2="{top-11}" stroke="{color}" stroke-width="2.5"/>')
        parts.append(f'<text x="{lx+23}" y="{top-7}" font-family="sans-serif" '
                     f'font-size="11" fill="#444">{label}</text>')
    if legend_note:
        parts.append(f'<text x="{pad_l}" y="{top-42}" font-family="sans-serif" '
                     f'font-size="11" fill="#666">{legend_note}</text>')
    # gridlines + y labels
    for v in _ticks(y_lo, y_hi):
        g = py(v)
        parts.append(f'<line x1="{pad_l}" y1="{g:.1f}" x2="{pad_l+plot_w}" '
                     f'y2="{g:.1f}" stroke="#e6e6e6" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l-6}" y="{g+3:.1f}" text-anchor="end" '
                     f'font-family="sans-serif" font-size="10" fill="#888">'
                     f'{_fmt(v)}</text>')
    if draw_zero and y_lo < 0 < y_hi:
        parts.append(f'<line x1="{pad_l}" y1="{py(0):.1f}" x2="{pad_l+plot_w}" '
                     f'y2="{py(0):.1f}" stroke="#bbb" stroke-width="1"/>')
    # x gridlines
    if xticks is None:
        xticks = _ticks(x0, x1)
    for t in xticks:
        g = px(t)
        parts.append(f'<line x1="{g:.1f}" y1="{top}" x2="{g:.1f}" '
                     f'y2="{top+height}" stroke="#f2f2f2" stroke-width="1"/>')
        lab = xfmt(t) if xfmt else f"{(t-x0)/1000:.2f}"
        parts.append(f'<text x="{g:.1f}" y="{top+height+14}" text-anchor="middle" '
                     f'font-family="sans-serif" font-size="10" fill="#888">'
                     f'{lab}</text>')
    if vgrid:
        for t in vgrid:
            if x0 <= t <= x1:
                g = px(t)
                parts.append(f'<line x1="{g:.1f}" y1="{top}" x2="{g:.1f}" '
                             f'y2="{top+height}" stroke="#ffca28" '
                             f'stroke-width="1" stroke-dasharray="2 3"/>')
    parts.append(f'<rect x="{pad_l}" y="{top}" width="{plot_w}" height="{height}" '
                 f'fill="none" stroke="#ccc"/>')
    parts.append(f'<text x="{pad_l+plot_w}" y="{top+height+28}" text-anchor="end" '
                 f'font-family="sans-serif" font-size="10" fill="#666">'
                 f'{x_label}</text>')
    parts.append(f'<text x="{pad_l-32}" y="{top+height/2}" font-family="sans-serif" '
                 f'font-size="10" fill="#666" transform="rotate(-90 {pad_l-32} '
                 f'{top+height/2})" text-anchor="middle">{y_label}</text>')
    # data
    for item in series:
        color, label, data = item[0], item[1], item[2]
        width = item[3] if len(item) > 3 else 1.2
        opacity = item[4] if len(item) > 4 else 1.0
        if len(data) < 2:
            continue
        pts = " ".join(f"{px(t):.1f},{py(v):.1f}" for t, v in data)
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" '
                     f'stroke-width="{width}" stroke-opacity="{opacity}"/>')
    if markers:
        for t, label in markers:
            if x0 <= t <= x1:
                parts.append(f'<line x1="{px(t):.1f}" y1="{top}" '
                             f'x2="{px(t):.1f}" y2="{top+height}" '
                             f'stroke="#ff9800" stroke-width="1" '
                             f'stroke-dasharray="3 3"/>')


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

    rows = load(args.logfile)
    if len(rows) < 20:
        print(f"ERROR: only {len(rows)} XY samples parsed from {args.logfile}")
        return 1

    log_ms = [r[0] for r in rows]
    t = [r[3] for r in rows]
    xs = [r[4] for r in rows]
    ys = [r[5] for r in rows]
    n = len(rows)
    t0 = t[0]
    dur = (t[-1] - t[0]) / 1000.0
    log_dur = (log_ms[-1] - log_ms[0]) / 1000.0
    dts = [b - a for a, b in zip(t, t[1:])]
    dt_ln = [b - a for a, b in zip(log_ms, log_ms[1:]) if b > a]

    out = []
    out.append(f"# EXP07 sample capture report - {os.path.basename(args.logfile)}")
    out.append(f"samples: {n}")
    out.append(f"firmware uptime window: {t0} .. {t[-1]} ms "
               f"({dur:.2f} s), log clock window {log_dur:.2f} s")
    out.append(f"interval: median {st.median(dts):.0f} ms, min {min(dts)}, "
               f"max {max(dts)} ms  (~{n/max(dur,1e-9):.0f} Hz); "
               f"log dt median {st.median(dt_ln):.0f} ms")
    dup = sum(1 for d in dts if d == 0)
    out.append(f"non-increasing uptime steps: {dup}")

    out.append("")
    out.append("## per-channel range")
    for nm, v in (("x", xs), ("y", ys)):
        out.append(f"  {nm}: min={min(v)}  max={max(v)}  range={max(v)-min(v)}  "
                   f"mean={st.mean(v):.0f}  sd={st.pstdev(v):.0f}  "
                   f"distinct={len(set(v))}")

    out.append("")
    out.append("## sample-format smoke test  (24-bit word written as hi,mid,lo)")
    out.append("   a real conversion has hi==mid ~0.4% of the time")
    for nm, v in (("x", xs), ("y", ys)):
        same = sum(1 for q in v if hi_eq_mid(q))
        out.append(f"  {nm}: hi==mid in {same}/{n} = {100*same/n:.1f}%")
    out.append("  examples (value -> hi,mid,lo):")
    for q in xs[:3]:
        h, m, l = bytes_of(q)
        out.append(f"    {q:>10} -> {h:02X} {m:02X} {l:02X}")
    out.append("  hi==mid means the word only ever encodes 256 coarse levels; the")
    out.append("  low byte merely subdivides them, so the 24-bit range is not real.")
    topx = {}
    for q in xs:
        topx[q] = topx.get(q, 0) + 1
    out.append("  most common x values: "
               + ", ".join(f"{val} x{cnt}" for val, cnt in
                           sorted(topx.items(), key=lambda kv: -kv[1])[:4]))

    out.append("")
    out.append("## x/y relationship")
    out.append(f"  pearson r(x,y) = {pearson(list(zip(xs, ys))):+.3f}")
    out.append(f"  |x-y| mean = {st.mean(abs(a-b) for a, b in zip(xs, ys)):.0f}")

    # step-to-step motion vs the whole range: is there an actual swing?
    out.append("")
    out.append("## dynamics")
    for nm, v in (("x", xs), ("y", ys)):
        dv = [b - a for a, b in zip(v, v[1:])]
        out.append(f"  {nm}: |step| median={st.median(abs(d) for d in dv):.0f} "
                   f"max={max(abs(d) for d in dv)}  "
                   f"total range={max(v)-min(v)}")

    report = "\n".join(out)
    print(report)
    rp = os.path.join(outdir, f"{stem}-report.txt")
    with open(rp, "w", encoding="utf-8") as fh:
        fh.write(report + "\n")

    # ---- SVG time-series diagram -----------------------------------------
    W, H = 1040, 700
    pad_l, pad_r, pad_t = 76, 24, 92
    plot_w = W - pad_l - pad_r
    panel_h = 228
    gap = 86
    p1_top = pad_t
    p2_top = p1_top + panel_h + gap

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}">',
             f'<rect width="{W}" height="{H}" fill="#fff"/>',
             f'<text x="{pad_l}" y="22" font-family="sans-serif" font-size="15" '
             f'font-weight="700" fill="#111">EXP07 {stem} - raw ADC x(t), y(t) '
             f'and the 24-bit word bytes</text>',
             f'<text x="{pad_l}" y="38" font-family="sans-serif" font-size="11" '
             f'fill="#666">{n} samples, uptime {t0}..{t[-1]} ms, '
             f'~{n/max(dur,1e-9):.0f} Hz</text>']

    line_panel(parts, t0, t[-1], p1_top, panel_h, pad_l, plot_w,
               "Recorded raw values  (both axes wander the full scale; no stable "
               "level - the signal is noise)",
               [("#1565c0", "raw x", [(a, b) for a, b in zip(t, xs)]),
                ("#c62828", "raw y", [(a, b) for a, b in zip(t, ys)])],
               "raw counts")

    hx = [(a, (b >> 16) & 0xFF) for a, b in zip(t, xs)]
    mx = [(a, (b >> 8) & 0xFF) for a, b in zip(t, xs)]
    lx = [(a, b & 0xFF) for a, b in zip(t, xs)]
    line_panel(parts, t0, t[-1], p2_top, panel_h, pad_l, plot_w,
               "Bytes of the raw x word  (red mid byte rides on top of the blue "
               "hi byte on every sample -> hi==mid)",
               [("#1565c0", "x hi byte", hx, 5.0, 0.40),
                ("#c62828", "x mid byte", mx, 1.3, 1.0),
                ("#9e9e9e", "x lo byte", lx, 1.0, 0.8)],
               "byte value", y_lo=-5, y_hi=260, draw_zero=False)
    parts.append('</svg>')

    svg_path = os.path.join(outdir, f"{stem}-timeseries.svg")
    with open(svg_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))

    print(f"\nwrote {rp}")
    print(f"wrote {svg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
