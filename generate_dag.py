"""Generate an SVG diagram of the algorithm decision DAG."""

# ── Colours ──────────────────────────────────────────────────────────
BLUE = "#3B82F6"      # user inputs
TEAL = "#0D9488"      # deterministic resolution
ORANGE = "#F59E0B"    # RNG-driven choices
PURPLE = "#8B5CF6"    # solver / constraint engine
SLATE = "#64748B"     # final assembly

# lighter fills (20% opacity tints)
FILL = {
    BLUE:   "#DBEAFE",
    TEAL:   "#CCFBF1",
    ORANGE: "#FEF3C7",
    PURPLE: "#EDE9FE",
    SLATE:  "#F1F5F9",
}

# Highlight accents for the two key steps
PROFILE_ACCENT = "#0D9488"   # teal — matches profile colour
SOLVER_ACCENT  = "#7C3AED"   # violet — distinct from solver purple

# IDs of edges that feed INTO the two key nodes
PROFILE_INPUTS = {"profile"}      # target id
SOLVER_INPUTS  = {"solver"}       # target id

# ── Canvas ───────────────────────────────────────────────────────────
W, H = 1400, 1050
TIER_Y = [60, 195, 340, 490, 650, 820]   # y-centres for tiers 0–5
BOX_H = 42
BOX_RX = 10
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"
FONT_SIZE = 13
LABEL_SIZE = 10.5

# ── Nodes ────────────────────────────────────────────────────────────
# (id, label, colour, tier, x_centre, overridable)
NODES = [
    # tier 0 — user inputs
    ("seed",          "seed",                    BLUE, 0, 350,  False),
    ("preset",        "style_preset",            BLUE, 0, 700,  False),
    ("lot_width",     "lot_width",               BLUE, 0, 1050, False),

    # tier 1 — resolution
    ("rng",           "Seeded RNG",              TEAL, 1, 350,  False),
    ("profile",       "Profile (all proportions)", TEAL, 1, 820, False),

    # tier 2 — structure
    ("floors",        "floor sequence + heights", TEAL, 2, 450, False),
    ("bay_count",     "bay_count",               ORANGE, 2, 900, True),

    # tier 3 — layout (the critical pivot)
    ("door_bay",      "door_bay_idx",            ORANGE, 3, 330,  True),
    ("solver",        "BAY LAYOUT SOLVER",       PURPLE, 3, 660,  False),
    ("custom_bays",   "custom_bays",             ORANGE, 3, 990,  True),

    # tier 4 — parallel RNG choices
    ("porte",         "porte_style",             ORANGE, 4, 200,  True),
    ("gf_type",       "ground_floor_type",       ORANGE, 4, 460,  True),
    ("mansard",       "mansard_params",          ORANGE, 4, 730,  True),
    ("cust_style",    "custom_bay_style",        ORANGE, 4, 1020, True),

    # tier 5 — assembly
    ("windows",       "Windows",                 SLATE, 5, 200,  False),
    ("balconies",     "Balconies",               SLATE, 5, 410,  False),
    ("gf_bays",       "Ground floor bays",       SLATE, 5, 640,  False),
    ("dormers",       "Dormers",                 SLATE, 5, 880,  True),
    ("chimneys",      "Chimneys",                SLATE, 5, 1100, False),
]

# ── Edges ────────────────────────────────────────────────────────────
# (from_id, to_id, label | None, is_strong)
EDGES = [
    # tier 0 → 1
    ("seed",      "rng",        "deterministic\nsequence",  False),
    ("preset",    "profile",    "sets ALL\nproportions",    True),

    # tier 1 → 2
    ("profile",   "floors",     "num_floors,\nheights, ornament", False),
    ("profile",   "bay_count",  None,                       False),
    ("lot_width", "bay_count",  "how many\nbays fit",       False),
    ("rng",       "bay_count",  None,                       False),

    # tier 2 → 3
    ("bay_count", "solver",     "positions\n+ widths",      True),
    ("door_bay",  "solver",     None,                       False),
    ("rng",       "door_bay",   None,                       False),
    ("solver",    "custom_bays", None,                      False),
    ("lot_width", "solver",     None,                       False),
    ("profile",   "solver",     "pier_ratio,\nwindow_ratio", False),

    # tier 1/2 → 4
    ("rng",       "porte",      None,                       False),
    ("rng",       "gf_type",    None,                       False),
    ("rng",       "mansard",    None,                       False),
    ("rng",       "cust_style", None,                       False),

    # tier 3/4 → 5 (the fan-out from solver)
    ("solver",    "windows",    "x, width\nper floor",      True),
    ("solver",    "balconies",  None,                       True),
    ("solver",    "gf_bays",    "shop/door/res\nper bay",   True),
    ("solver",    "dormers",    "snap to\nbay centres",     True),
    ("solver",    "chimneys",   "at pier gaps,\naway from door", True),

    # floor heights → assembly
    ("floors",    "windows",    "height =\n75% of floor",   False),
    ("floors",    "balconies",  None,                       False),

    # mansard → dormers
    ("mansard",   "dormers",    "has_dormers\ngates existence", False),

    # ground floor type → ground floor bays
    ("gf_type",   "gf_bays",   None,                       False),
    ("porte",     "gf_bays",   None,                       False),

    # custom bays → custom bay style
    ("custom_bays", "cust_style", None,                    False),
]

# ── Helpers ──────────────────────────────────────────────────────────
def node_map():
    return {n[0]: n for n in NODES}

def text_width(txt, size=FONT_SIZE):
    """Rough estimate of text width in px."""
    return len(txt) * size * 0.58

def box_w(label):
    """Box width based on label length."""
    return max(text_width(label) + 36, 100)

def escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ── SVG generation ───────────────────────────────────────────────────
def build_svg():
    nm = node_map()
    parts = []

    # header
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" font-family="{FONT}">\n'
    )

    # defs: arrowheads
    parts.append("""<defs>
  <marker id="arrow" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
    <polygon points="0 0, 10 3.5, 0 7" fill="#94A3B8"/>
  </marker>
  <marker id="arrow-strong" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
    <polygon points="0 0, 10 3.5, 0 7" fill="#475569"/>
  </marker>
  <filter id="shadow" x="-4%" y="-4%" width="108%" height="116%">
    <feDropShadow dx="0" dy="1" stdDeviation="2" flood-opacity="0.08"/>
  </filter>
  <filter id="glow-teal" x="-18%" y="-18%" width="136%" height="136%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur"/>
    <feFlood flood-color="#0D9488" flood-opacity="0.25" result="color"/>
    <feComposite in="color" in2="blur" operator="in" result="glow"/>
    <feMerge><feMergeNode in="glow"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <filter id="glow-violet" x="-18%" y="-18%" width="136%" height="136%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur"/>
    <feFlood flood-color="#7C3AED" flood-opacity="0.25" result="color"/>
    <feComposite in="color" in2="blur" operator="in" result="glow"/>
    <feMerge><feMergeNode in="glow"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <marker id="arrow-profile" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
    <polygon points="0 0, 10 3.5, 0 7" fill="#0D9488"/>
  </marker>
  <marker id="arrow-solver" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
    <polygon points="0 0, 10 3.5, 0 7" fill="#7C3AED"/>
  </marker>
</defs>\n""")

    # background
    parts.append(f'<rect width="{W}" height="{H}" fill="#FAFBFC" rx="8"/>\n')

    # title
    parts.append(
        f'<text x="{W/2}" y="32" text-anchor="middle" font-size="18" '
        f'font-weight="600" fill="#1E293B">Algorithm Decision DAG — '
        f'How Early Choices Constrain Later Ones</text>\n'
    )

    # tier labels
    tier_labels = [
        "USER INPUTS", "RESOLUTION", "STRUCTURE",
        "LAYOUT (critical pivot)", "PARALLEL RNG CHOICES", "ASSEMBLY"
    ]
    for i, label in enumerate(tier_labels):
        y = TIER_Y[i]
        parts.append(
            f'<text x="28" y="{y + 5}" font-size="10" fill="#94A3B8" '
            f'font-weight="500" text-transform="uppercase">{label}</text>\n'
        )

    # ── Spotlight zones behind the two key nodes ──────────────────────
    # Profile spotlight: covers preset (tier 0) → Profile (tier 1)
    sp_x, sp_w = 590, 410
    sp_y = TIER_Y[0] - BOX_H / 2 - 16
    sp_h = (TIER_Y[1] + BOX_H / 2 + 16) - sp_y
    parts.append(
        f'<rect x="{sp_x}" y="{sp_y}" width="{sp_w}" height="{sp_h}" '
        f'rx="16" fill="#0D9488" fill-opacity="0.06" '
        f'stroke="#0D9488" stroke-opacity="0.18" stroke-width="1.5" '
        f'stroke-dasharray="6 3"/>\n'
    )
    # Solver spotlight: covers bay_count + door_bay + solver (tier 2–3)
    sv_x, sv_w = 235, 830
    sv_y = TIER_Y[2] - BOX_H / 2 - 16
    sv_h = (TIER_Y[3] + BOX_H / 2 + 16) - sv_y
    parts.append(
        f'<rect x="{sv_x}" y="{sv_y}" width="{sv_w}" height="{sv_h}" '
        f'rx="16" fill="#7C3AED" fill-opacity="0.05" '
        f'stroke="#7C3AED" stroke-opacity="0.15" stroke-width="1.5" '
        f'stroke-dasharray="6 3"/>\n'
    )

    # ── Draw edges first (behind nodes) ──────────────────────────────
    for from_id, to_id, label, strong in EDGES:
        fn = nm[from_id]
        tn = nm[to_id]
        x1, y1 = fn[4], TIER_Y[fn[3]]
        x2, y2 = tn[4], TIER_Y[tn[3]]

        # offset start/end to box edges
        y1_out = y1 + BOX_H / 2
        y2_in = y2 - BOX_H / 2

        # Colour input edges to the two key nodes
        if to_id in PROFILE_INPUTS:
            stroke, sw, marker = PROFILE_ACCENT, "2.5", "arrow-profile"
        elif to_id in SOLVER_INPUTS:
            stroke, sw, marker = SOLVER_ACCENT, "2.5", "arrow-solver"
        elif strong:
            stroke, sw, marker = "#475569", "1.8", "arrow-strong"
        else:
            stroke, sw, marker = "#CBD5E1", "1.1", "arrow"

        # simple straight or slight curve
        dx = x2 - x1
        if abs(dx) < 5:
            parts.append(
                f'<line x1="{x1}" y1="{y1_out}" x2="{x2}" y2="{y2_in}" '
                f'stroke="{stroke}" stroke-width="{sw}" '
                f'marker-end="url(#{marker})"/>\n'
            )
        else:
            # cubic bezier that drops vertically then curves to target
            cy1 = y1_out + (y2_in - y1_out) * 0.45
            cy2 = y1_out + (y2_in - y1_out) * 0.55
            parts.append(
                f'<path d="M{x1},{y1_out} C{x1},{cy1} {x2},{cy2} {x2},{y2_in}" '
                f'fill="none" stroke="{stroke}" stroke-width="{sw}" '
                f'marker-end="url(#{marker})"/>\n'
            )

        # edge label
        if label:
            lx = (x1 + x2) / 2
            ly = (y1_out + y2_in) / 2
            # offset label slightly to the right of midpoint to avoid line
            offset_x = 8 if dx >= 0 else -8
            anchor = "start" if dx >= 0 else "end"
            lines = label.split("\n")
            for li, line in enumerate(lines):
                parts.append(
                    f'<text x="{lx + offset_x}" y="{ly + li * 13 - (len(lines)-1)*6}" '
                    f'text-anchor="{anchor}" font-size="{LABEL_SIZE}" '
                    f'font-style="italic" fill="#64748B">{escape(line)}</text>\n'
                )

    # ── Draw nodes ───────────────────────────────────────────────────
    for nid, label, colour, tier, cx, overridable in NODES:
        bw = box_w(label)
        bx = cx - bw / 2
        by = TIER_Y[tier] - BOX_H / 2
        fill = FILL[colour]

        # display label
        display = label
        if overridable:
            display = label + "  \u2699"

        # Key nodes get glow + thicker stroke
        if nid == "profile":
            filt = "url(#glow-teal)"
            sw = "2.5"
        elif nid == "solver":
            filt = "url(#glow-violet)"
            sw = "2.5"
        else:
            filt = "url(#shadow)"
            sw = "1.5"

        parts.append(
            f'<rect x="{bx}" y="{by}" width="{bw}" height="{BOX_H}" '
            f'rx="{BOX_RX}" fill="{fill}" stroke="{colour}" '
            f'stroke-width="{sw}" filter="{filt}"/>\n'
        )
        parts.append(
            f'<text x="{cx}" y="{TIER_Y[tier] + 5}" text-anchor="middle" '
            f'font-size="{FONT_SIZE}" font-weight="500" fill="#1E293B">'
            f'{escape(display)}</text>\n'
        )

    # ── Annotation callouts for the two key steps ─────────────────────

    # --- Profile callout (right side of spotlight zone) ---
    pc_x, pc_y = 1030, 112      # callout box top-left
    pc_w, pc_h = 330, 110
    # leader line from callout to Profile node
    prof_node = nm["profile"]
    prof_cx, prof_cy = prof_node[4], TIER_Y[prof_node[3]]
    prof_bw = box_w(prof_node[1])
    parts.append(
        f'<line x1="{prof_cx + prof_bw/2}" y1="{prof_cy}" '
        f'x2="{pc_x}" y2="{pc_y + pc_h/2}" '
        f'stroke="{PROFILE_ACCENT}" stroke-width="1.2" stroke-dasharray="4 3"/>\n'
    )
    parts.append(
        f'<rect x="{pc_x}" y="{pc_y}" width="{pc_w}" height="{pc_h}" '
        f'rx="8" fill="white" stroke="{PROFILE_ACCENT}" stroke-width="1.5"/>\n'
    )
    callout_lines = [
        (pc_x + 14, pc_y + 22,  14, "600", PROFILE_ACCENT, "\u2605  TYPICALITY"),
        (pc_x + 14, pc_y + 42,  11, "400", "#334155",  "The DNA of Haussmann style"),
        (pc_x + 14, pc_y + 60,  10.5, "400", "#64748B", "Input: style_preset"),
        (pc_x + 14, pc_y + 76,  10.5, "400", "#64748B", "Sets: floor count, heights, pier ratios,"),
        (pc_x + 14, pc_y + 90,  10.5, "400", "#64748B", "window proportions, ornament, balcony rules"),
    ]
    for lx, ly, fs, fw, fc, txt in callout_lines:
        parts.append(
            f'<text x="{lx}" y="{ly}" font-size="{fs}" '
            f'font-weight="{fw}" fill="{fc}">{escape(txt)}</text>\n'
        )

    # --- Solver callout (right side of spotlight zone) ---
    sc_x, sc_y = 1090, 385     # callout box top-left
    sc_w, sc_h = 280, 120
    # leader line from callout to Solver node
    solv_node = nm["solver"]
    solv_cx, solv_cy = solv_node[4], TIER_Y[solv_node[3]]
    solv_bw = box_w(solv_node[1])
    parts.append(
        f'<line x1="{solv_cx + solv_bw/2}" y1="{solv_cy}" '
        f'x2="{sc_x}" y2="{sc_y + sc_h/2}" '
        f'stroke="{SOLVER_ACCENT}" stroke-width="1.2" stroke-dasharray="4 3"/>\n'
    )
    parts.append(
        f'<rect x="{sc_x}" y="{sc_y}" width="{sc_w}" height="{sc_h}" '
        f'rx="8" fill="white" stroke="{SOLVER_ACCENT}" stroke-width="1.5"/>\n'
    )
    callout_lines2 = [
        (sc_x + 14, sc_y + 22,  14, "600", SOLVER_ACCENT, "\u2605  HARMONY"),
        (sc_x + 14, sc_y + 42,  11, "400", "#334155",  "Resolves proportions into positions"),
        (sc_x + 14, sc_y + 60,  10.5, "400", "#64748B", "Inputs: bay_count, door_bay_idx,"),
        (sc_x + 14, sc_y + 76,  10.5, "400", "#64748B", "lot_width, profile (pier/window ratios)"),
        (sc_x + 14, sc_y + 96,  10.5, "400", "#64748B", "Sets: x-position and width for EVERY"),
        (sc_x + 14, sc_y + 110, 10.5, "400", "#64748B", "window, balcony, dormer, and chimney"),
    ]
    for lx, ly, fs, fw, fc, txt in callout_lines2:
        parts.append(
            f'<text x="{lx}" y="{ly}" font-size="{fs}" '
            f'font-weight="{fw}" fill="{fc}">{escape(txt)}</text>\n'
        )

    # ── Legend ────────────────────────────────────────────────────────
    legend_x, legend_y = 30, H - 170
    parts.append(
        f'<rect x="{legend_x}" y="{legend_y}" width="260" height="155" '
        f'rx="8" fill="white" stroke="#E2E8F0" stroke-width="1"/>\n'
    )
    parts.append(
        f'<text x="{legend_x + 14}" y="{legend_y + 22}" font-size="12" '
        f'font-weight="600" fill="#1E293B">Legend</text>\n'
    )

    legend_items = [
        (BLUE,   "User input"),
        (TEAL,   "Deterministic resolution"),
        (ORANGE, "RNG-driven choice"),
        (PURPLE, "Solver / constraint engine"),
        (SLATE,  "Final assembly"),
    ]
    for i, (colour, desc) in enumerate(legend_items):
        iy = legend_y + 42 + i * 22
        parts.append(
            f'<rect x="{legend_x + 14}" y="{iy - 9}" width="16" height="16" '
            f'rx="3" fill="{FILL[colour]}" stroke="{colour}" stroke-width="1"/>\n'
        )
        parts.append(
            f'<text x="{legend_x + 38}" y="{iy + 3}" font-size="11.5" '
            f'fill="#334155">{desc}</text>\n'
        )

    # gear icon explanation
    gy = legend_y + 42 + len(legend_items) * 22
    parts.append(
        f'<text x="{legend_x + 18}" y="{gy + 3}" font-size="14" '
        f'fill="#475569">\u2699</text>\n'
    )
    parts.append(
        f'<text x="{legend_x + 38}" y="{gy + 3}" font-size="11.5" '
        f'fill="#334155">Overridable via BuildingOverrides</text>\n'
    )

    # ── Strong-edge note ─────────────────────────────────────────────
    note_x = W - 360
    note_y = H - 55
    parts.append(
        f'<line x1="{note_x}" y1="{note_y}" x2="{note_x + 40}" y2="{note_y}" '
        f'stroke="#475569" stroke-width="2"/>\n'
    )
    parts.append(
        f'<text x="{note_x + 48}" y="{note_y + 4}" font-size="11" '
        f'fill="#475569">= strong constraint (narrows downstream space)</text>\n'
    )
    parts.append(
        f'<line x1="{note_x}" y1="{note_y + 20}" x2="{note_x + 40}" '
        f'y2="{note_y + 20}" stroke="#CBD5E1" stroke-width="1.2"/>\n'
    )
    parts.append(
        f'<text x="{note_x + 48}" y="{note_y + 24}" font-size="11" '
        f'fill="#94A3B8">= data flow</text>\n'
    )

    parts.append("</svg>\n")
    return "".join(parts)


if __name__ == "__main__":
    svg = build_svg()
    out = "output/algorithm_dag.svg"
    with open(out, "w") as f:
        f.write(svg)
    print(f"Wrote {out} ({len(svg)} bytes)")
