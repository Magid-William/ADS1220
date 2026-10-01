#!/usr/bin/env python3
"""EXP08 - extract and plot the circular motion from the gain-1 captures.

The raw captures are dominated by a ~50 Hz carrier (aliased by the 125 Hz poll)
and a ~-4.4e6 offset, which hides the nub motion. Processing:
  1. 5-sample boxcar (40 ms = 2 mains cycles) -> nulls 50 Hz and its 25 Hz half
  2. subtract the mean -> removes the DC offset
  3. optional extra moving-average high-pass -> removes slow drift

Panels: circle x(t)/y(t), rest x(t)/y(t) (same processing, as control), and an
X-Y scatter of both so a ring would show up.

Usage:
    python experiments/EXP08/plot_circle_motion.py
"""

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
BOXCAR = 5          # 40 ms at 125 Hz -> nulls 50 Hz and 25 Hz
DRIFT_MA = 0        # >1 to also high-pass with a moving average of that width
SKIP_MS = 5000      # drop the driver's startup/calibration burst


def load(path):
    out = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            q = XY_RE.search(line)
            if q:
                out.append((int(q.group(1)), int(q.group(2)), int(q.group(3))))
    return out


def boxcar(v, w):
    return [sum(v[i:i + w]) / w for i in range(0, len(v) - w + 1)]


def movavg(v, w):
    h = w // 2
    return [sum(v[max(0, i - h):min(len(v), i + h + 1)])
            / (min(len(v), i + h + 1) - max(0, i - h)) for i in range(len(v))]


def process(rows):
    t = [r[0] for r in rows]
    x = boxcar([r[1] for r in rows], BOXCAR)
    y = boxcar([r[2] for r in rows], BOXCAR)
    tc = t[BOXCAR // 2: BOXCAR // 2 + len(x)]
    # drop the startup/calibration burst
    keep = [i for i, q in enumerate(tc) if q - tc[0] >= SKIP_MS]
    tc = [tc[i] for i in keep]
    x = [x[i] for i in keep]
    y = [y[i] for i in keep]
    if DRIFT_MA > 1:
        x = [a - b for a, b in zip(x, movavg(x, DRIFT_MA))]
        y = [a - b for a, b in zip(y, movavg(y, DRIFT_MA))]
    else:
        mx, my = st.mean(x), st.mean(y)
        x = [a - mx for a in x]
        y = [a - my for a in y]
    return tc, x, y


def pearson(a, b):
    ma, mb = st.mean(a), st.mean(b)
    sa = sum((q - ma) ** 2 for q in a) ** 0.5
    sb = sum((q - mb) ** 2 for q in b) ** 0.5
    return sum((a[i] - ma) * (b[i] - mb) for i in range(len(a))) / (sa * sb) if sa and sb else 0.0


def pca(a, b):
    n = len(a)
    ma, mb = st.mean(a), st.mean(b)
    sxx = sum((q - ma) ** 2 for q in a) / n
    syy = sum((q - mb) ** 2 for q in b) / n
    sxy = sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / n
    tr, det = sxx + syy, sxx * syy - sxy * sxy
    d = max(tr * tr / 4 - det, 0) ** 0.5
    return (tr / 2 + d) ** 0.5, (tr / 2 - d) ** 0.5


def scatter_panel(parts, left, top, size, pad, title, series, lim):
    def px(v):
        return left + pad + (v + lim) / (2 * lim) * (size - 2 * pad)

    def py(v):
        return top + size - pad - (v + lim) / (2 * lim) * (size - 2 * pad)

    parts.append(f'<text x="{left}" y="{top-10}" font-family="sans-serif" '
                 f'font-size="13" font-weight="600" fill="#222">{title}</text>')
    parts.append(f'<rect x="{left+pad}" y="{top+pad}" width="{size-2*pad}" '
                 f'height="{size-2*pad}" fill="none" stroke="#ccc"/>')
    parts.append(f'<line x1="{left+pad}" y1="{py(0):.1f}" x2="{left+size-pad}" '
                 f'y2="{py(0):.1f}" stroke="#e6e6e6"/>')
    parts.append(f'<line x1="{px(0):.1f}" y1="{top+pad}" x2="{px(0):.1f}" '
                 f'y2="{top+size-pad}" stroke="#e6e6e6"/>')
    for i, (color, label, pts) in enumerate(series):
        for a, b in pts:
            parts.append(f'<circle cx="{px(a):.1f}" cy="{py(b):.1f}" r="1.1" '
                         f'fill="{color}" fill-opacity="0.55"/>')
        lx = left + pad + 6
        ly = top + pad + 12 + i * 15
        parts.append(f'<circle cx="{lx}" cy="{ly}" r="3" fill="{color}"/>')
        parts.append(f'<text x="{lx+8}" y="{ly+4}" font-family="sans-serif" '
                     f'font-size="11" fill="#444">{label}</text>')
    parts.append(f'<text x="{left+size-pad}" y="{top+size-pad+14}" '
                 f'text-anchor="end" font-family="sans-serif" font-size="10" '
                 f'fill="#888">x (counts)</text>')
    parts.append(f'<text x="{left+pad-6}" y="{top+pad}" text-anchor="end" '
                 f'font-family="sans-serif" font-size="10" fill="#888">'
                 f'{lim/1000:.0f}k</text>')


def main():
    circle = load(os.path.join(HERE, "exp08-gain1-circle.log"))
    rest = load(os.path.join(HERE, "exp08-gain1-rest.log"))
    tc, cx, cy = process(circle)
    tr, rx, ry = process(rest)

    for tag, x, y in (("circle", cx, cy), ("rest", rx, ry)):
        maj, mnr = pca(x, y)
        print(f"{tag}: n={len(x)} x sd={st.pstdev(x):.0f} y sd={st.pstdev(y):.0f} "
              f"r(x,y)={pearson(x, y):+.3f} PCA minor/major={mnr/maj if maj else 0:.2f}")

    W = 1040
    pad_l, pad_r, pad_t = 84, 24, 132
    plot_w = W - pad_l - pad_r
    ph = 232
    A = pad_t
    sc_size = 392
    C = A + ph + 78
    H = C + sc_size + 44

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}">',
        f'<rect width="{W}" height="{H}" fill="#fff"/>',
        f'<text x="{pad_l}" y="24" font-family="sans-serif" font-size="15" '
        f'font-weight="700" fill="#111">EXP08 - the circular nub motion, '
        f'recovered from the gain-1 capture</text>',
        f'<text x="{pad_l}" y="42" font-family="sans-serif" font-size="11" '
        f'fill="#666">40 ms boxcar (nulls the 50/25 Hz mains) then mean removed, '
        f'first 5 s (driver calibration) dropped</text>',
        f'<text x="{pad_l}" y="58" font-family="sans-serif" font-size="11" '
        f'fill="#666">the motion is now clearly above the rest floor (sd '
        f'143k/156k vs 95k/96k) - but x and y move together, so it is a line, '
        f'not a ring</text>',
    ]

    lim = max(max(abs(v) for v in cx + cy), max(abs(v) for v in rx + ry))
    lim = (int(lim / 50000) + 1) * 50000

    ps.line_panel(parts, tc[0], tc[-1], A, ph, pad_l, plot_w,
                  f"circle capture - x(t) and y(t), mains-nulled  "
                  f"({len(cx)} samples, sd x {st.pstdev(cx):.0f} / y {st.pstdev(cy):.0f})",
                  [("#1565c0", "x", list(zip(tc, cx)), 1.3, 1.0),
                   ("#c62828", "y", list(zip(tc, cy)), 1.3, 1.0)],
                  "counts", y_lo=-lim, y_hi=lim, draw_zero=True)

    sc_left = (W - sc_size) // 2
    scatter_panel(parts, sc_left, C, sc_size, 40,
                  "x-y scatter, same processing  (green = circling, grey = rest)",
                  [("#2e7d32", "circle", list(zip(cx, cy))),
                   ("#9e9e9e", "rest", list(zip(rx, ry)))], lim)
    parts.append('</svg>')

    out = os.path.join(HERE, "exp08-circle-motion.svg")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
