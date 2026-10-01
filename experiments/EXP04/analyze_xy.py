#!/usr/bin/env python3
"""EXP04 - analyze a paired raw X/Y circle-motion capture.

Parses the 'XY <uptime_ms> <raw_x> <raw_y>' lines that the EXP04 firmware build
emits once per poll, plus the '### phase: cue|stop' markers written by
capture-serial.ps1, and reports whether the raw signal can resolve two
independent axes well enough to drive pointer motion.

Stdlib only (matplotlib/numpy are not installed in this environment).
Outputs: a text report, <stem>-xy.csv, and four SVG plots.

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
PLATEAU_TOL = 5000           # counts: within this of the modal value = "on the plateau"
MAX_GAP_MS = 1000            # a bigger step = a new capture segment (stale USB buffer)


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


def segments(samples):
    """Split on USB stale-buffer jumps. -> (list_of_blocks, list_of_start_indices)."""
    segs, starts = [], []
    cur, cur_start = [samples[0]], 0
    for i, (a, b) in enumerate(zip(samples, samples[1:]), start=1):
        if b[0] - a[0] > MAX_GAP_MS:
            segs.append(cur)
            starts.append(cur_start)
            cur, cur_start = [b], i
        else:
            cur.append(b)
    segs.append(cur)
    starts.append(cur_start)
    return segs, starts


def modal(vals):
    counts = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    v, n = max(counts.items(), key=lambda kv: kv[1])
    return v, n, sorted(counts.items(), key=lambda kv: -kv[1])[:4]


def pearson(pairs):
    n = len(pairs)
    if n < 2:
        return 0.0
    mx = st.mean(x for x, _ in pairs)
    my = st.mean(y for _, y in pairs)
    sx = math.sqrt(sum((x - mx) ** 2 for x, _ in pairs))
    sy = math.sqrt(sum((y - my) ** 2 for _, y in pairs))
    if sx == 0 or sy == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in pairs) / (sx * sy)


def pca(pairs):
    n = len(pairs)
    mx = st.mean(x for x, _ in pairs)
    my = st.mean(y for _, y in pairs)
    sxx = sum((x - mx) ** 2 for x, _ in pairs) / n
    syy = sum((y - my) ** 2 for _, y in pairs) / n
    sxy = sum((x - mx) * (y - my) for x, y in pairs) / n
    tr, det = sxx + syy, sxx * syy - sxy * sxy
    disc = math.sqrt(max(tr * tr / 4 - det, 0.0))
    l1, l2 = tr / 2 + disc, tr / 2 - disc
    return math.sqrt(max(l1, 0)), math.sqrt(max(l2, 0))


def _svg(path, title, series, w=760, h=420, pad=46):
    pts_all = [p for _, data in series for p in data]
    xs = [p[0] for p in pts_all]
    ys = [p[1] for p in pts_all]
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
           f'fill="none" stroke="#ccc"/>']
    for color, data in series:
        if len(data) < 2:
            continue
        pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in data)
        out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" '
                   f'stroke-width="1.1"/>')
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

    raw, markers = load(args.logfile)
    if len(raw) < 20:
        print(f"ERROR: only {len(raw)} XY samples parsed from {args.logfile}")
        print("       (is the EXP04 firmware flashed and 'tpoint xy' on?)")
        return 1

    segs, starts = segments(raw)
    best = max(range(len(segs)), key=lambda i: len(segs[i]))
    data = segs[best]
    seg_start = starts[best]
    # remap marker sample-indices into the chosen segment
    markers = [(idx - seg_start, kind, text) for idx, kind, text in markers
               if seg_start <= idx <= seg_start + len(data)]
    dropped = len(raw) - len(data)
    print(f"# EXP04 X/Y capture report - {os.path.basename(args.logfile)}")
    print(f"samples: {len(data)} used of {len(raw)}"
          + (f"  (dropped {dropped} stale pre-buffer samples in "
             f"{len(segs) - 1} earlier segment(s))" if dropped else ""))

    # motion / rest window from the phase markers, falling back to magnitude
    cue = next((i for i, k, _ in markers if k == "cue"), None)
    stop = next((i for i, k, _ in markers if k == "stop"), None)
    t0 = data[0][0]
    if cue is not None and cue < len(data):
        mv0 = cue
        mv1 = stop if (stop is not None and stop > cue) else len(data)
        src = "phase markers"
    else:
        head = data[: max(10, len(data) // 8)]
        cx = st.median(x for _, x, _ in head)
        cy = st.median(y for _, _, y in head)
        dxs = [abs(x - cx) for _, x, _ in head]
        dys = [abs(y - cy) for _, _, y in head]
        thr = max(4 * st.median(dxs), 4 * st.median(dys), 20000)
        idx = [i for i, (_, x, y) in enumerate(data)
               if abs(x - cx) > thr or abs(y - cy) > thr]
        mv0, mv1 = (idx[0], idx[-1] + 1) if idx else (0, len(data))
        src = "motion auto-detect"
    rest = data[:mv0] + data[mv1:]
    motion = data[mv0:mv1]

    ts = [t for t, _, _ in data]
    dts = [b - a for a, b in zip(ts, ts[1:]) if b > a]
    dur_s = (ts[-1] - ts[0]) / 1000.0
    print(f"duration: {dur_s:.1f} s   rate: {len(data)/max(dur_s,1e-9):.1f} Hz   "
          f"dt median {st.median(dts) if dts else 0:.1f} ms   "
          f"dt max {max(dts) if dts else 0} ms   gaps>20ms: "
          f"{sum(1 for d in dts if d > 20)}")
    print(f"motion window: [{mv0}:{mv1}] ({len(motion)} samples, {src}); "
          f"rest: {len(rest)} samples")
    print("  (expected ~8 ms/poll = 125 Hz; a lower rate means dropped lines)")

    mx = [x for _, x, _ in motion]
    my = [y for _, _, y in motion]
    rx = [x for _, x, _ in rest]
    ry = [y for _, _, y in rest]

    print("\n## rest window (nub untouched)")
    for nm, v in (("x", rx), ("y", ry)):
        if v:
            print(f"  {nm}: n={len(v)} min={min(v)} max={max(v)} "
                  f"mean={st.mean(v):.0f} std={st.pstdev(v):.0f} pp={max(v)-min(v)}")
        else:
            print(f"  {nm}: (no rest samples)")

    print("\n## plateau / rail behaviour")
    for nm, v in (("x", mx), ("y", my)):
        modal_v, modal_n, top = modal(v)
        at_rail = sum(1 for q in v if q <= RAIL_MIN or q >= RAIL_MAX)
        near_rail = sum(1 for q in v if abs(q - RAIL_MIN) <= PLATEAU_TOL
                        or abs(q - RAIL_MAX) <= PLATEAU_TOL)
        print(f"  {nm}: modal value {modal_v} x{modal_n} ({100*modal_n/len(v):.0f}%)  "
              f"exactly on a rail: {at_rail} ({100*at_rail/len(v):.0f}%)  "
              f"within {PLATEAU_TOL} of a rail: {near_rail} "
              f"({100*near_rail/len(v):.0f}%)")
        print(f"     top values: "
              + ", ".join(f"{val} x{cnt}" for val, cnt in top))

    # samples where BOTH channels are off the plateau = the usable motion signal
    plateau_x, _, _ = modal(mx) if mx else (0, 0, [])
    live = [(x, y) for x, y in zip(mx, my)
            if abs(x - plateau_x) > PLATEAU_TOL]
    print(f"\n## usable motion signal (x off the x-plateau in the motion window)")
    print(f"  {len(live)} of {len(motion)} samples "
          f"({100*len(live)/max(len(motion),1):.0f}%)")
    if len(live) > 10:
        lx = [x for x, _ in live]
        ly = [y for _, y in live]
        print(f"  x: min={min(lx)} max={max(lx)} mean={st.mean(lx):.0f} std={st.pstdev(lx):.0f}")
        print(f"  y: min={min(ly)} max={max(ly)} mean={st.mean(ly):.0f} std={st.pstdev(ly):.0f}")

    print("\n## two-axis independence (motion window)")
    r = pearson(list(zip(mx, my)))
    maj, mnr = pca(list(zip(mx, my)))
    print(f"  pearson r(x,y) = {r:+.3f}   (a circle -> ~0; one coupled axis -> +/-1)")
    print(f"  PCA major std = {maj:.0f}  minor std = {mnr:.0f}  "
          f"minor/major = {mnr/maj if maj else 0:.2f}   (a ring -> ~1; a line -> ~0)")
    if len(live) > 10:
        rl = pearson(live)
        majl, mnrl = pca(live)
        print(f"  off-plateau only: r = {rl:+.3f}  minor/major = "
              f"{mnrl/majl if majl else 0:.2f}  (n={len(live)})")

    print("\n## direction coverage")
    for nm, mv, rv in (("x", mx, rx), ("y", my, ry)):
        c = st.median(rv) if rv else st.mean(mv)
        print(f"  {nm}: rest centre {c:.0f}  motion reaches {min(mv)} "
              f"(below? {min(mv) < c}) and {max(mv)} (above? {max(mv) > c})")

    print("\n## SNR (motion std / rest std)")
    for nm, mv, rv in (("x", mx, rx), ("y", my, ry)):
        ns = st.pstdev(rv) if len(rv) > 1 else 0.0
        ss = st.pstdev(mv)
        print(f"  {nm}: signal std {ss:.0f} / noise std {ns:.0f} = "
              f"{('inf' if ns == 0 else f'{ss/ns:.1f}')}")

    # ---- verdict ---------------------------------------------------------
    reasons = []
    for nm, mv, rv in (("x", mx, rx), ("y", my, ry)):
        c = st.median(rv) if rv else st.mean(mv)
        if not (min(mv) < c < max(mv)):
            reasons.append(f"{nm} does not swing to both sides of its rest value "
                           f"(rest {c:.0f}; range {min(mv)}..{max(mv)})")
    plateau_frac = max(
        sum(1 for q in mx if abs(q - modal(mx)[0]) <= PLATEAU_TOL) / max(len(mx), 1),
        sum(1 for q in my if abs(q - modal(my)[0]) <= PLATEAU_TOL) / max(len(my), 1))
    if plateau_frac > 0.5:
        reasons.append(f"{100*plateau_frac:.0f}% of samples sit on one plateau/rail "
                       f"value (signal is not continuously readable)")
    if maj and mnr / maj < 0.25:
        reasons.append("X-Y cloud is essentially a line (axes not independent)")
    if abs(r) > 0.9:
        reasons.append(f"X and Y are {r:+.2f} correlated (crosstalk / shared node)")
    railed = sum(1 for q in (mx + my) if q <= RAIL_MIN or q >= RAIL_MAX)
    if railed:
        reasons.append(f"{railed} samples sit exactly on a rail (clipped)")
    if r < -0.4 or r > 0.4:
        reasons.append(f"X and Y are {r:+.2f} correlated (crosstalk / shared node)")

    print("\n## verdict")
    if not reasons:
        print("  SUFFICIENT: both axes swing around rest with independent, "
              "non-clipped, well-above-noise ranges.")
    else:
        print("  NOT SUFFICIENT as-is:")
        for why in reasons:
            print(f"    - {why}")

    # ---- artifacts -------------------------------------------------------
    os.makedirs(outdir, exist_ok=True)
    csv_path = os.path.join(outdir, f"{stem}-xy.csv")
    with open(csv_path, "w", encoding="utf-8") as fh:
        fh.write("t_ms,raw_x,raw_y,phase\n")
        for i, (t, x, y) in enumerate(data):
            fh.write(f"{t},{x},{y},{'motion' if mv0 <= i < mv1 else 'rest'}\n")
    _svg(os.path.join(outdir, f"{stem}-xy-scatter.svg"),
         "X-Y scatter (blue = motion, red = rest)",
         [("#1565c0", [(x, y) for x, y in zip(mx, my)]),
          ("#c62828", [(x, y) for x, y in zip(rx, ry)])])
    if len(live) > 10:
        _svg(os.path.join(outdir, f"{stem}-xy-live.svg"),
             f"X-Y scatter, off-plateau samples only (n={len(live)})",
             [("#2e7d32", live)])
    _svg(os.path.join(outdir, f"{stem}-x.svg"), "x(t)",
         [("#1565c0", [((t - t0) / 1000.0, x) for t, x, _ in data])])
    _svg(os.path.join(outdir, f"{stem}-y.svg"), "y(t)",
         [("#1565c0", [((t - t0) / 1000.0, y) for t, _, y in data])])
    print(f"\nwrote {csv_path}")
    print(f"wrote {stem}-xy-scatter.svg / -xy-live.svg / -x.svg / -y.svg in {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
