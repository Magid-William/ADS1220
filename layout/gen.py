#!/usr/bin/env python3
"""
Perfboard layout generator + checker for the TrackPoint / ADS1220 front-end.

Board: 16 columns x 8 rows, 2.54 mm pitch ("dotted" perfboard, no strips).
Every connection is a wire: the layout is placement + a jumper list.

Outputs (next to this file):
    board.md     hole map, parts list, wire list, build order, checklist
    board.tex    1:1 drawing (compile with tectonic -> PDF -> PNG)

Usage:  python gen.py
"""

from collections import defaultdict

PITCH_MM = 2.54
ROWS = "ABCDEFGH"                     # A = top row, H = bottom row
COLS = range(1, 17)                   # 1 .. 16 (left to right)

# ---------------------------------------------------------------- geometry ---


def hole(col, row):
    """('C', 3) -> 'D3'  (row letter first, then column number)"""
    return f"{ROWS[row]}{col}"


def rc(h):
    """'D3' -> (3, 3)  i.e. (col, row_index)"""
    return int(h[1:]), ROWS.index(h[0])


# ---- components ------------------------------------------------------------
# The ADS1220 breakout is a 2x8 pin module: pin rows 6 holes (0.6") apart.
MOD_L, MOD_R = 2, 8                   # pin columns
MOD_PINS_L = ["DRDY", "MISO", "MOSI", "SCLK", "CS", "CLK", "DVDD", "DGND"]
MOD_PINS_R = ["AIN0", "AIN1", "AIN2", "AIN3", "REFN0", "REFP0", "AVDD", "AGND"]

MODULE_PINS = {}
for i, name in enumerate(MOD_PINS_L):
    MODULE_PINS[name] = hole(MOD_L, i)
for i, name in enumerate(MOD_PINS_R):
    MODULE_PINS[name] = hole(MOD_R, i)

# the module body occupies everything between the two pin columns
MODULE_BODY = {hole(c, r) for c in range(MOD_L, MOD_R + 1) for r in range(8)}

# resistors: (ref, value, lead a, lead b); the body spans the holes between
RESISTORS = [
    # R2 branch (a -> a/2), two 1.2k in series
    ("R2a", "1.2k", "E10", "E13"),
    ("R2b", "1.2k", "D10", "D13"),
    # R1 branch (a/2 -> GND), two 1.2k in series
    ("R1a", "1.2k", "C16", "E16"),
    ("R1b", "1.2k", "E16", "H16"),
]

# capacitors: (ref, value, lead a, lead b)
CAPS = [
    ("C1", "100n", "G9", "H9"),       # AVDD - AGND
    ("C2", "100n", "G1", "H1"),       # DVDD - DGND
    ("C3", "100n", "C9", "E9"),       # AIN2 - GND
]

# ---- electrical nodes ------------------------------------------------------
# Each node lists the holes that are *soldered* to it, grouped into wire runs.
# A run's intermediate holes are passed over (never soldered): they must not
# belong to another node.
NODES = {
    "GND": [
        # digital side
        ["E1", "E2"],                 # landing -> CS
        ["E1", "F1"],                 # landing rail
        ["F1", "F2"],                 # -> CLK
        ["H1", "H2"],                 # landing -> DGND
        # analog side: REFN0 -> (under the socketed module) -> ground rail
        ["E8", "E9"],                 # REFN0 -> C3 ground lead
        ["E8", "E7", "F7", "G7", "H7", "H8"],
        ["H8", "H9"],                 # AGND -> C1 ground lead
        ["H9", "H14", "H15", "H16"],  # ground rail (H14 = GND landing)
    ],
    "3V3": [
        ["G1", "G2"],                 # landing -> DVDD
        ["G8", "G9", "G10", "G11"],   # AVDD -> C1 -> landing
    ],
    "x": [["A8", "A16"]],
    "y": [["B8", "B16"]],
    "DRDY": [["A1", "A2"]],
    "MISO": [["B1", "B2"]],
    "MOSI": [["C1", "C2"]],
    "SCLK": [["D1", "D2"]],
    "MID": [                          # a/2, AIN2
        ["C8", "C9", "C10"],
        ["C10", "D10"],               # -> R2b
        ["C10", "C16"],               # -> R1a
    ],
    "A": [                            # trackpoint a (bridge top)
        ["F8", "F9", "F10", "E10"],   # REFP0 -> R2a
        ["F10", "F15"],               # -> sensor landing
    ],
    "N1": [["E13", "D13"]],           # R2a - R2b junction
}

# ---- off-board landing wires ----------------------------------------------
# hole -> (signal, where it goes)
LANDINGS = {
    "A1": ("DRDY", "nice!nano P1.06"),
    "B1": ("MISO", "nice!nano P0.20"),
    "C1": ("MOSI", "nice!nano P0.17"),
    "D1": ("SCLK", "nice!nano P0.08"),
    "G1": ("3V3", "nice!nano VCC"),
    "E1": ("GND", "nice!nano GND (digital)"),
    "H1": ("GND", "nice!nano GND (digital)"),
    "A16": ("x", "TrackPoint x"),
    "B16": ("y", "TrackPoint y"),
    "F15": ("a", "TrackPoint a"),
    "H15": ("b", "TrackPoint b"),
    "G11": ("3V3", "nice!nano VCC (analog side)"),
    "H14": ("GND", "nice!nano GND (analog star)"),
}

# ---------------------------------------------------------------- checking ---


def body_holes():
    """holes covered by a component body (must stay free of foreign nets)"""
    blocked = {}
    for ref, _val, a, b in RESISTORS:
        (c1, r1), (c2, r2) = rc(a), rc(b)
        if c1 == c2:
            for r in range(min(r1, r2) + 1, max(r1, r2)):
                blocked[hole(c1, r)] = ref
        else:
            for c in range(min(c1, c2) + 1, max(c1, c2)):
                blocked[hole(c, r1)] = ref
    for ref, _val, a, b in CAPS:
        (c1, r1), (c2, r2) = rc(a), rc(b)
        if c1 == c2:
            for r in range(min(r1, r2) + 1, max(r1, r2)):
                blocked[hole(c1, r)] = ref
        else:
            for c in range(min(c1, c2) + 1, max(c1, c2)):
                blocked[hole(c, r1)] = ref
    return blocked


def component_terminals():
    term = {}
    for ref, _val, a, b in RESISTORS + CAPS:
        term[a] = ref
        term[b] = ref
    return term


def check():
    errors, warnings = [], []
    owner = defaultdict(set)          # hole -> {nodes}
    passed = defaultdict(set)         # hole -> {nodes passing over it}

    for node, runs in NODES.items():
        for run in runs:
            for h in run:
                owner[h].add(node)
            # holes strictly between consecutive points are passed over
            for a, b in zip(run, run[1:]):
                (c1, r1), (c2, r2) = rc(a), rc(b)
                if c1 == c2:
                    for r in range(min(r1, r2) + 1, max(r1, r2)):
                        passed[hole(c1, r)].add(node)
                elif r1 == r2:
                    for c in range(min(c1, c2) + 1, max(c1, c2)):
                        passed[hole(c, r1)].add(node)
                else:
                    errors.append(f"diagonal wire {a}->{b}: keep runs orthogonal")

    for h, nodes in owner.items():
        if len(nodes) > 1:
            errors.append(f"hole {h} is claimed by {sorted(nodes)}")

    blocked = body_holes()
    for h, ref in blocked.items():
        if h in owner:
            errors.append(f"hole {h} is under {ref}'s body but wired by "
                          f"{sorted(owner[h])}")

    # a wire may never run over a hole that belongs to a different node
    for h, nodes in passed.items():
        if h in owner:
            for n in nodes:
                if n not in owner[h]:
                    warnings.append(
                        f"wire {n} passes over hole {h} ({sorted(owner[h])})"
                        " - keep it clear / add a bend")
        if h in blocked:
            for n in nodes:
                warnings.append(f"wire {n} passes over {blocked[h]}'s body at {h}")

    # landings must sit on a real node
    for h, (sig, _dest) in LANDINGS.items():
        if h not in owner:
            errors.append(f"landing {h} ({sig}) is not on any node")

    # module pins must be reachable (each needs a wire); AIN3 floats on purpose
    wired = set(owner) | set(component_terminals())
    for name, h in MODULE_PINS.items():
        if h not in wired and name != "AIN3":
            warnings.append(f"module pin {name} ({h}) has no connection")

    # wires that have to pass under the module (between the two pin columns)
    under = sorted({h for h in owner if rc(h)[0] in range(MOD_L + 1, MOD_R)})
    return errors, warnings, under


# ---------------------------------------------------------------- markdown ---


def node_holes(node):
    out = []
    for run in NODES[node]:
        for h in run:
            if h not in out:
                out.append(h)
    return out


def crossed_holes(node):
    """holes the wires of this node pass over (must stay unsoldered)"""
    out = []
    for run in NODES[node]:
        for a, b in zip(run, run[1:]):
            (c1, r1), (c2, r2) = rc(a), rc(b)
            if c1 == c2:
                span = [hole(c1, r) for r in range(min(r1, r2) + 1, max(r1, r2))]
            elif r1 == r2:
                span = [hole(c, r1) for c in range(min(c1, c2) + 1, max(c1, c2))]
            else:
                span = []
            for h in span:
                if h not in out and h not in node_holes(node):
                    out.append(h)
    return out


def markdown(errors, warnings, under):
    L = []
    L.append("# Perfboard layout - ADS1220 front-end (16 x 8 holes)\n")
    L.append(f"Board: 16 columns x 8 rows at {PITCH_MM} mm pitch = "
             f"**{15 * PITCH_MM:.1f} x {7 * PITCH_MM:.2f} mm** "
             "(single-sided dotted perfboard, no strips).\n")
    L.append("Generated by `gen.py` - do not hand-edit; change the data in the "
             "script and re-run.\n")
    L.append("Rules the layout obeys:\n")
    L.append("- every hole is soldered to at most one net;")
    L.append("- no wire runs over a hole of a different net;")
    L.append("- no component body sits on top of another net's hole;")
    L.append("- the ADS1220 module is **socketed** (2x8 female header): two wires "
             "pass underneath it.\n")

    L.append("## 1. Parts and where they go\n")
    L.append("| ref | part | value | holes | notes |")
    L.append("|---|---|---|---|---|")
    L.append(f"| U1 | ADS1220 breakout | - | pins at columns {MOD_L} and {MOD_R}, "
             f"rows A-H | socket: 2x8 female header. Left column = digital, "
             "right column = analog |")
    for ref, val, a, b in RESISTORS:
        L.append(f"| {ref} | resistor 1/4 W | {val} | {a} - {b} | vertical/horizontal "
                 "axial, leads bent to the holes |")
    for ref, val, a, b in CAPS:
        L.append(f"| {ref} | ceramic cap | {val} | {a} - {b} | body sits flat, "
                 "leads in the two holes |")

    L.append("\n## 2. Nets (solder map)\n")
    L.append("Holes in **bold** are where a wire/lead is soldered. Holes between "
             "two bold holes in the same run are *passed over* - never solder a "
             "wire there.\n")
    L.append("| net | solder here | pass over (do NOT solder) | lands off-board |")
    L.append("|---|---|---|---|")
    for node in sorted(NODES):
        holes = node_holes(node)
        crossed = crossed_holes(node)
        lands = [f"{h} -> {sig} ({dest})" for h, (sig, dest) in LANDINGS.items()
                 if h in holes]
        L.append(f"| **{node}** | {', '.join(holes)} | "
                 f"{', '.join(crossed) or '-'} | {'; '.join(lands) or '-'} |")

    L.append("\n## 3. Wire list (grouped by net; build order is section 4)\n")
    n = 0
    for node in sorted(NODES):
        for run in NODES[node]:
            n += 1
            pts = " -> ".join(run)
            L.append(f"{n}. **{node}**: {pts}")
    L.append("\nComponents that act as wires (they are already listed above):\n")
    for ref, val, a, b in RESISTORS:
        L.append(f"- {ref} ({val}): {a} - {b}")
    for ref, val, a, b in CAPS:
        L.append(f"- {ref} ({val}): {a} - {b}")

    L.append("\n## 4. Build order\n")
    L.append("1. Solder the 2x8 female socket in columns 2 and 8, rows A-H "
             "(DRDY at A2). Keep the socket straight - the module plugs in "
             "from above.")
    L.append("2. Solder the four 1.2k resistors (R2a, R2b, R1a, R1b).")
    L.append("3. Solder C1, C2, C3.")
    L.append("4. Wire the digital side: the four SPI/DRDY jumpers and the two "
             "ground/3V3 runs on column 1.")
    L.append("5. Wire the analog side: REFP0->R2a, the two ground tap wires, the "
             "3V3 run to AVDD, then the under-module ground wire (step 6).")
    L.append("6. The one wire that passes underneath the module: "
             f"{' -> '.join(['E8', 'E7', 'F7', 'G7', 'H7', 'H8'])}. "
             "Route it flat against the board before plugging the module in.")
    L.append("7. Plug in the module and land the off-board wires (section 2).")
    L.append("8. Print `board.pdf` at 100 % and tape it to the board as a "
             "soldering guide.")

    L.append("\n## 5. Before you power it up\n")
    L.append("- continuity: each net in section 2 should beep only within itself;")
    L.append("- no continuity between `3V3` and `GND`, or between the analog pins "
             "(AIN0/1/2) and anything else;")
    L.append("- `AIN3` (D8) must be floating;")
    L.append("- with the driver polling: V(a)-V(b) >= 0.75 V, V(x) ~ V(y) ~ V(a)/2.")

    if warnings:
        L.append("\n## 6. Checker notes\n")
        for w in warnings:
            L.append(f"- {w}")

    L.append("\n## 6. Under-module routing\n")
    L.append("These holes are inside the module footprint and carry wires: "
             f"{', '.join(under) if under else 'none'}. "
             "They only work with the socket fitted - do not solder the module "
             "directly to the board.\n")

    L.append("## 7. Checker status\n")
    L.append(f"- errors: **{len(errors)}**")
    for e in errors:
        L.append(f"  - {e}")
    L.append(f"- warnings: **{len(warnings)}**")
    for w in warnings:
        L.append(f"  - {w}")
    return "\n".join(L) + "\n"


# -------------------------------------------------------------------- tikz ---

NETCOL = {
    "GND": "black", "3V3": "red!80!black", "x": "blue!70!black",
    "y": "blue!40!black", "MID": "orange!90!black", "A": "green!55!black",
    "N1": "green!30!black",
    "DRDY": "violet", "MISO": "violet!75!black", "MOSI": "violet!50!black",
    "SCLK": "violet!30!black",
}


def cm(col):
    return (col - 1) * 0.254


def cmy(row):
    return -row * 0.254


def tikz():
    L = []
    L.append(r"% 1:1 perfboard layout - compile with tectonic, print at 100%")
    L.append(r"\documentclass[border=5mm]{standalone}")
    L.append(r"\usepackage{tikz}")
    L.append(r"\usepackage{xcolor}")
    L.append(r"\begin{document}")
    L.append(r"\begin{tikzpicture}[line width=0.25mm]")
    L.append(r"\tikzset{tf/.style={font=\fontsize{4}{4.6}\selectfont}}")
    L.append(r"\definecolor{netgnd}{HTML}{555555}")
    L.append(r"\definecolor{net3v3}{HTML}{C00000}")
    L.append(r"\definecolor{netx}{HTML}{0044AA}")
    L.append(r"\definecolor{nety}{HTML}{3388CC}")
    L.append(r"\definecolor{netmid}{HTML}{D07000}")
    L.append(r"\definecolor{neta}{HTML}{008040}")
    L.append(r"\definecolor{netn}{HTML}{70B070}")
    L.append(r"\definecolor{netspi}{HTML}{8000A0}")
    w, hgt = cm(16), -cmy(7)

    # ---- board + hole grid
    L.append(f"\\draw[line width=0.4mm,fill=green!5] (-0.45,0.45) rectangle "
             f"({w + 0.45:.3f},{-hgt - 0.45:.3f});")
    for c in COLS:
        for r in range(8):
            L.append(f"\\draw[gray!55,fill=gray!25] ({cm(c):.3f},{cmy(r):.3f}) "
                     "circle (0.35mm);")

    # ---- row / column references in the margin
    for r, letter in enumerate(ROWS):
        L.append(f"\\node[tf,text=gray!70] at ({cm(1) - 0.62:.3f},{cmy(r):.3f}) "
                 f"{{{letter}}};")
    for c in COLS:
        L.append(f"\\node[tf,text=gray!70] at ({cm(c):.3f},{-hgt - 0.28:.3f}) "
                 f"{{{c}}};")

    # ---- module footprint
    L.append(f"\\draw[dashed,gray!60] ({cm(MOD_L) - 0.13:.3f},0.13) rectangle "
             f"({cm(MOD_R) + 0.13:.3f},{-hgt - 0.13:.3f});")

    # ---- components
    for ref, val, a, b in RESISTORS:
        (c1, r1), (c2, r2) = rc(a), rc(b)
        x1, y1, x2, y2 = cm(c1), cmy(r1), cm(c2), cmy(r2)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        L.append(f"\\draw[line width=0.4mm] ({x1:.3f},{y1:.3f}) -- "
                 f"({x2:.3f},{y2:.3f});")
        if c1 == c2:
            L.append(f"\\draw[fill=brown!35,draw=black,line width=0.15mm] "
                     f"({mx - 0.10:.3f},{my - 0.30:.3f}) rectangle "
                     f"({mx + 0.10:.3f},{my + 0.30:.3f});")
            lx = mx + 0.16 if c1 < 16 else mx - 0.16
            anc = "west" if c1 < 16 else "east"
        else:
            L.append(f"\\draw[fill=brown!35,draw=black,line width=0.15mm] "
                     f"({mx - 0.30:.3f},{my + 0.10:.3f}) rectangle "
                     f"({mx + 0.30:.3f},{my - 0.10:.3f});")
            lx, anc = mx, "north"
        L.append(f"\\node[tf,anchor={anc}] at ({lx:.3f},{my:.3f}) {{{ref}}};")

    for ref, val, a, b in CAPS:
        (c1, r1), (c2, r2) = rc(a), rc(b)
        x1, y1, x2, y2 = cm(c1), cmy(r1), cm(c2), cmy(r2)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        L.append(f"\\draw[line width=0.4mm] ({x1:.3f},{y1:.3f}) -- "
                 f"({mx:.3f},{my + 0.035:.3f}) ({mx:.3f},{my - 0.035:.3f}) -- "
                 f"({x2:.3f},{y2:.3f});")
        L.append(f"\\draw[line width=0.4mm] ({mx - 0.11:.3f},{my + 0.035:.3f}) -- "
                 f"({mx + 0.11:.3f},{my + 0.035:.3f});")
        L.append(f"\\draw[line width=0.4mm] ({mx - 0.11:.3f},{my - 0.035:.3f}) -- "
                 f"({mx + 0.11:.3f},{my - 0.035:.3f});")
        lx = mx + 0.15 if c1 < 15 else mx - 0.15
        anc = "west" if c1 < 15 else "east"
        L.append(f"\\node[tf,anchor={anc}] at ({lx:.3f},{my:.3f}) {{{ref}}};")

    # ---- wires
    colours = {"GND": "netgnd", "3V3": "net3v3", "x": "netx", "y": "nety",
               "MID": "netmid", "A": "neta", "N1": "netn"}
    for node in sorted(NODES):
        col = colours.get(node, "netspi")
        for run in NODES[node]:
            pts = " -- ".join(f"({cm(rc(h)[0]):.3f},{cmy(rc(h)[1]):.3f})"
                              for h in run)
            L.append(f"\\draw[{col},line width=0.3mm] {pts};")
        for h in node_holes(node):
            L.append(f"\\fill[{col}] ({cm(rc(h)[0]):.3f},{cmy(rc(h)[1]):.3f}) "
                     "circle (0.14mm);")

    # ---- off-board landings (staggered leaders + names outside the board)
    for i, (h, (sig, _dest)) in enumerate(sorted(LANDINGS.items())):
        c, r = rc(h)
        far = (i % 2 == 0)
        if c == 1:
            ex = -0.75 if far else -1.15
            L.append(f"\\draw[gray!70,dashed,line width=0.15mm] "
                     f"({cm(c):.3f},{cmy(r):.3f}) -- ({ex + 0.05:.3f},{cmy(r):.3f});")
            L.append(f"\\node[tf,anchor=east] at ({ex:.3f},{cmy(r):.3f}) {{{sig}}};")
        else:
            ex = w + 0.75 if far else w + 1.15
            L.append(f"\\draw[gray!70,dashed,line width=0.15mm] "
                     f"({cm(c):.3f},{cmy(r):.3f}) -- ({w + 0.45:.3f},{cmy(r):.3f})"
                     f" -- ({ex - 0.05:.3f},{cmy(r):.3f});")
            L.append(f"\\node[tf,anchor=west] at ({ex:.3f},{cmy(r):.3f}) "
                     f"{{{sig}}};")

    # ---- key block, to the right of everything (one node per line)
    kx = w + 2.60
    key = [
        ("key", True),
        ("module pins (socket, 2x8)", False),
        ("left column, rows A-H:", False),
        ("DRDY MISO MOSI SCLK", False),
        ("CS CLK DVDD DGND", False),
        ("right column, rows A-H:", False),
        ("AIN0 AIN1 AIN2 AIN3", False),
        ("REFN0 REFP0 AVDD AGND", False),
        ("", False),
        ("R2a R2b R1a R1b = 1.2k", False),
        ("C1 C2 C3 = 100nF", False),
        ("", False),
        ("wire colours:", False),
        ("GND grey, 3V3 red", False),
        ("x dark blue, y light blue", False),
        ("a/2 orange, a green", False),
        ("SPI and DRDY purple", False),
        ("", False),
        ("filled dot = soldered hole", False),
        ("plain hole = free / passed over", False),
        ("R1a spans 2 holes: keep wires", False),
        ("out from under its body", False),
        ("one GND wire runs under the", False),
        ("socketed module", False),
        ("print at 100 percent, no scaling", False),
    ]
    y = 0.45
    for text, bold in key:
        if text:
            body = f"\\textbf{{{text}}}" if bold else text
            L.append(f"\\node[tf,anchor=north west] at ({kx:.3f},{y:.3f}) "
                     f"{{{body}}};")
        y -= 0.145

    L.append(r"\end{tikzpicture}")
    L.append(r"\end{document}")
    return "\n".join(L) + "\n"


def owner_nodes(h):
    return [n for n, runs in NODES.items() if any(h in r for r in runs)]


def landed(h):
    return h in LANDINGS


def terminal(h):
    return h in component_terminals()


# -------------------------------------------------------------------- main ---

if __name__ == "__main__":
    errors, warnings, under = check()
    with open("board.md", "w", encoding="utf-8") as f:
        f.write(markdown(errors, warnings, under))
    with open("board.tex", "w", encoding="utf-8") as f:
        f.write(tikz())

    print(f"board.md + board.tex written")
    print(f"errors  : {len(errors)}")
    for e in errors:
        print(f"   ! {e}")
    print(f"warnings: {len(warnings)}")
    for w in warnings:
        print(f"   - {w}")
    print(f"under-module holes: {', '.join(under)}")
