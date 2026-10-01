#!/usr/bin/env python3
"""EXP04 - analyze a paired raw X/Y circle-motion capture.

Parses the 'XY <uptime_ms> <raw_x> <raw_y>' lines that the EXP04 firmware build
emits once per poll, plus the '### phase: cue|stop' markers written by
capture-serial.ps1, and reports whether the raw signal can resolve two
independent axes well enough to drive pointer motion.

Stdlib only (matplotlib/numpy are not installed in this environment).
Outputs: a text report, <stem>-xy.csv, and three SVG plots.

Usage:
    python experiments/EXP04/analyze_xy.py experiments/EXP04/exp04-circle.log
"""

import argparse
import math
import os
import re
import statistics as st
import sys

XY_RE = re.compile(r"XY\s+(\d+)\s+(-?\d+)\s+(-?\d+)")
PHASE_RE = re.compile(r"### phase:\s*(cue|stop)\s*'([^']*)'")

RAIL_MIN = -8388608          # 0x800000, 24-bit two's-complement negative FS
RAIL_MAX = 8388607           # 0x7FFFFF
RAIL_MARGIN = 20000          # counts from full scale counted as "at the rail"


def load(path):
    """-> (samples[(t,x,y)], markers[(n_samples_before, kind, text)])"""
    samples, markers = [], []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = XY_RE.search(line)
            if m:
                samples.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
                continue
            p = PHASE_RE.search(line)
            if p:
                markers.append((len(samples), p.group(1), p.group(2)))
    return samples, markers


def window_by_markers(samples, markers):
    """Use the cue/stop file markers if present, else None."""
    cue = next((i for i, k, _ in markers if k == "cue"), None)
    stop = next((i for i, k, _ in markers if k == "stop"), None)
    if cue is None:
        return None
    if stop is None or stop <= cue:
        stop = len(samples)
    return cue, stop


def window_by_motion(samples, frac=0.15):
    """Fallback: rest = first `frac` of the capture; moving = far from its centre."""
    n = len(samples)
    head = samples[: max(10, int(n * frac))]
    cx = st.median(x for _, x, _ in head)
    cy = st.median(y for _, _, y in head)
    dx = [abs(x - cx) for _, x, _ in head]
    dy = [abs(y - cy) for _, _, y in head]
    thr = max(4 * st.median(dx), 4 * st.median(dy), 20000)
    idx = [i for i, (_, x, y) in enumerate(samples)
           if abs(x - cx) > thr or abs(y - cy) > thr]
    if not idx:
        return 0, n
    return idx[0], idx[-1] + 1


def describe(name, vals):
    lo, hi = min(vals), max(vals)
    return (f"  {name:<8} n={len(vals):<6} min={lo:>10} max={hi:>10} "
            f"mean={st.mean(vals):>12.1f} std={st.pstdev(vals):>11.1f} "
            f"pp={hi - lo:>10}")


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = st.mean(xs), st.mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def pca(xs, ys):
    """-> (major_std, minor_std, angle_deg) of the 2-D point cloud."""
    n = len(xs)
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs) / n
    syy = sum((y - my) ** 2 for y in ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
    tr, det = sxx + syy, sxx * syy - sxy * sxy
    disc = math.sqrt(max(tr * tr / 4 - det, 0.0))
    l1, l2 = tr / 2 + disc, tr / 2 - disc
    angle = 0.5 * math.degrees(math.atan2(2 * sxy, sxx - syy))
    return math.sqrt(max(l1, 0)), math.sqrt(max(l2, 0)), angle


# --------------------------------------------------------------------------- SVG
def _svg(path, title, polylines, w=760, h=420, pad=46):
    xs = [p[0] for ln in polylines for p in ln]
    ys = [p[1] for ln in polylines for p in ln]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 == x0:
        x1 = x0 + 1
    if y1 == y0:
        y1 = y0 + 1
    def sx(v):
        return pad + (v - x0) / (x1 - x0) * (w - 2 * pad)
    def sy(v):
        return h - pad - (v - y0) / (y1 - y0) * (h - 2 * pad)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}">',
           f'<rect width="{w}" height="{h}" fill="#fff"/>',
           f'<text x="{pad}" y="24" font-family="sans-serif" font-size="15">{title}</text>',
           f'<rect x="{pad}" y="{pad}" width="{w-2*pad}" height="{h-2*pad}" '
           f'fill="none" stroke="#bbb"/>']
    for ln in polylines:
        pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in ln)
        out.append(f'<polyline points="{pts}" fill="none" stroke="#1565c0" '
                   f'stroke-width="1.2"/>')
    out.append(f'<text x="{pad}" y="{h-14}" font-family="sans-serif" '
               f'font-size="11" fill="#666">x: {x0} .. {x1}</text>')
    out.append('</svg>')
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))


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

    samples, markers = load(args.logfile)
    if len(samples) < 20:
        print(f"ERROR: only {len(samples)} XY samples parsed from {args.logfile}")
        print("       (is the EXP04 firmware flashed and 'tpoint xy' on?)")
        return 1

    ws = window_by_markers(samples, markers)
    source = "phase markers"
    if ws is None:
        ws = window_by_motion(samples)
        source = "motion auto-detect"
    mv0, mv1 = ws
    rest = samples[:mv0] + samples[mv1:]
    motion = samples[mv0:mv1]

    print(f"# EXP04 X/Y capture report - {os.path.basename(args.logfile)}")
    print(f"samples: {len(samples)}   motion window: [{mv0}:{mv1}] "
          f"({len(motion)} samples, {source})")

    ts = [t for t, _, _ in samples]
    dts = [b - a for a, b in zip(ts, ts[1:]) if b > a]
    dur_s = (ts[-1] - ts[0]) / 1000.0
    print(f"duration: {dur_s:.1f} s   rate: {len(samples)/max(dur_s,1e-9):.1f} Hz   "
          f"dt median {st.median(dts) if dts else 0:.1f} ms   "
          f"dt max {max(dts) if dts else 0} ms   gaps>20ms: "
          f"{sum(1 for d in dts if d > 20)}")

    mx = [x for _, x, _ in motion]
    my = [y for _, _, y in motion]
    rx = [x for _, x, _ in rest]
    ry = [y for _, _, y in rest]

    print("\n## rest window (noise / bias)")
    if rest:
        print(describe("x", rx))
        print(describe("y", ry))
    else:
        print("  (no rest samples)")

    print("\n## motion window (signal)")
    print(describe("x", mx))
    print(describe("y", my))

    print("\n## rail / clipping  (full scale {0} / {1})".format(RAIL_MIN, RAIL_MAX))
    for nm, v in (("x", mx), ("y", my)):
        hi = sum(1 for q in v if q <= RAIL_MIN + RAIL_MARGIN or q >= RAIL_MAX - RAIL_MARGIN)
        top = {}
        for q in v:
            top[q] = top.get(q, 0) + 1
        common = sorted(top.items(), key=lambda kv: -kv[1])[:3]
        print(f"  {nm}: {hi} samples ({100*hi/len(v):.1f}%) within {RAIL_MARGIN} of a "
              f"rail; hit min={min(v) == RAIL_MIN} max={max(v) == RAIL_MAX}")
        print(f"     most common raw values: "
              + ", ".join(f"{val} x{cnt} ({100*cnt/len(v):.0f}%)" for val, cnt in common))

    print("\n## two-axis independence (motion window)")
    r = pearson(mx, my)
    maj, mnr, ang = pca(mx, my)
    print(f"  pearson r(x,y) = {r:+.3f}   (circle ~0; a single coupled axis ~ +/-1)")
    print(f"  PCA major std = {maj:.0f}   minor std = {mnr:.0f}   "
          f"minor/major = {mnr/maj if maj else 0:.2f}   angle = {ang:.1f} deg")
    print(f"  (minor/major near 1.0 = a ring -> two independent axes; near 0 = one line)")

    print("\n## direction coverage vs rest centre")
    for nm, mv, rv in (("x", mx, rx), ("y", my, ry)):
        c = st.median(rv) if rv else st.mean(mv)
        print(f"  {nm}: centre~{c:.0f}  reaches {min(mv)} (below? {min(mv) < c}) "
              f"and {max(mv)} (above? {max(mv) > c})")

    print("\n## SNR (motion std / rest std)")
    for nm, mv, rv in (("x", mx, rx), ("y", my, ry)):
        ns = st.pstdev(rv) if len(rv) > 1 else 0.0
        ss = st.pstdev(mv)
        print(f"  {nm}: signal std {ss:.0f} / noise std {ns:.0f} = "
              f"{('inf' if ns == 0 else f'{ss/ns:.1f}')}")

    # ---- operator verdict -------------------------------------------------
    verdict_ok = True
    reasons = []
    if not (min(mx) < (st.median(rx) if rx else 0) < max(mx)) or \
       not (min(my) < (st.median(ry) if ry else 0) < max(my)):
        verdict_ok = False
        reasons.append("an axis does not swing to both sides of its rest value")
    if maj and mnr / maj < 0.25:
        verdict_ok = False
        reasons.append("X-Y cloud is essentially a line (axes not independent)")
    if abs(r) > 0.9:
        verdict_ok = False
        reasons.append(f"X and Y are {r:+.2f} correlated (crosstalk / shared node)")
    railed = sum(1 for v in (mx, my) for q in v
                 if q <= RAIL_MIN or q >= RAIL_MAX)
    if railed:
        verdict_ok = False
        reasons.append(f"{railed} samples sit exactly on a rail (clipped)")

    print("\n## verdict")
    if verdict_ok:
        print("  SUFFICIENT: both axes swing around rest with independent, "
              "non-clipped, well-above-noise ranges (see numbers above).")
    else:
        print("  NOT SUFFICIENT as-is:")
        for why in reasons:
            print(f"    - {why}")

    # ---- artifacts --------------------------------------------------------
    os.makedirs(outdir, exist_ok=True)
    csv_path = os.path.join(outdir, f"{stem}-xy.csv")
    with open(csv_path, "w", encoding="utf-8") as fh:
        fh.write("t_ms,raw_x,raw_y,phase\n")
        for i, (t, x, y) in enumerate(samples):
            fh.write(f"{t},{x},{y},{'motion' if mv0 <= i < mv1 else 'rest'}\n")
    t0 = ts[0]
    _svg(os.path.join(outdir, f"{stem}-xy-scatter.svg"),
         "X-Y scatter (blue = motion, red = rest)",
         [[(x, y) for _, x, y in motion], [(x, y) for _, x, y in rest]])
    _svg(os.path.join(outdir, f"{stem}-x.svg"), "x(t)",
         [[((t - t0) / 1000.0, x) for t, x, _ in samples]])
    _svg(os.path.join(outdir, f"{stem}-y.svg"), "y(t)",
         [[((t - t0) / 1000.0, y) for t, _, y in samples]])
    print(f"\nwrote {csv_path}")
    print(f"wrote {stem}-xy-scatter.svg / -x.svg / -y.svg in {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
