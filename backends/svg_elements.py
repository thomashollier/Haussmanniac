"""SVG renderers for element-level style variants.

Each public function dispatches on a style enum to draw the appropriate
visual.  All functions receive an ``SVGContext`` (duck-typed — uses
``ctx.rect``, ``ctx.line``, ``ctx.polygon``, ``ctx.x``, ``ctx.y``,
``ctx.px``, ``ctx.elements``).

Extending: add a new branch in the relevant ``render_*`` function.
"""

from __future__ import annotations

import math

from core.elements import (
    AwningStyle,
    BalconyStyle,
    CafeStyle,
    DoorStyle,
    ElementPalette,
    StorefrontStyle,
)

# ── Colour constants (match svg.py palette) ──────────────────────────

_C = {
    "window": "#4A6078",
    "window_frame": "#3A4A5A",
    "door": "#5A4A3A",
    "door_dark": "#4A3A2A",
    "door_panel": "#6B5A48",
    "door_glass": "#5A6878",
    "kickplate": "#1A2028",
    "mullion": "#B0A080",
    "mullion_light": "#C0B090",
    "stone": "#D4C9B5",
    "stone_stroke": "#B8A898",
    "lintel": "#C8B8A0",
    "sill": "#C8B8A0",
    "iron": "#3A3A3A",
    "iron_light": "#555",
    "rail": "#2A2A2A",
    "balcony_floor": "#D8D0C0",
    "cornice": "#D0D0D0",
    "cornice_stroke": "#A0A0A0",
    "recess": "#B8AE9A",
    "recess_stroke": "#A09888",
    "handle": "#888",
    "awning_red": "#8B2020",
    "awning_green": "#2D5A3D",
    "awning_navy": "#3A3A6B",
    "awning_gold": "#C8A050",
    "awning_cream": "#E8E0D0",
}

# Snapshot of original values (for color variation restore)
_C_ORIG: dict[str, str] = dict(_C)

# ── Common ground-floor opening proportions ──────────────────────────
# These match the reference cafe_options_v4.svg design sheet.

_KICK_H = 0.50     # Kickplate / knee wall height (metres) — matches door bottom
_OPEN_FRAC = 0.83   # Glass fills 83% of floor height

def _opening(floor_y, floor_h):
    """Return (glass_bot, glass_top, glass_h) for standard ground floor opening."""
    glass_bot = floor_y + _KICK_H
    glass_h = floor_h * _OPEN_FRAC - _KICK_H
    glass_top = glass_bot + glass_h
    return glass_bot, glass_top, glass_h


# Mullion bar widths in metres (rendered as filled rectangles for crisp visibility)
_MUL_W = 0.05     # standard vertical mullion bar
_MUL_BAY = 0.12   # bay boundary mullion (thick, stands out from internal)
_MUL_DOOR = 0.12  # door edge mullion (same as bay boundary)
_MUL_H = 0.04     # horizontal transom bar height


def _vmul(ctx, x, y_bot, y_top, w=None):
    """Draw a vertical mullion bar as a filled rectangle."""
    mw = w or _MUL_W
    ctx.rect(x - mw / 2, y_bot, mw, y_top - y_bot, _C["mullion"], stroke_w=0)


def _hmul(ctx, x_left, x_right, y, h=None):
    """Draw a horizontal mullion/transom bar as a filled rectangle."""
    mh = h or _MUL_H
    ctx.rect(x_left, y - mh / 2, x_right - x_left, mh, _C["mullion"], stroke_w=0)


# =====================================================================
# CAFE GROUP RENDERERS
# =====================================================================

def render_cafe_group(ctx, style: CafeStyle, group: list,
                      floor_y: float, floor_h: float):
    """Render a cafe group (list of BayNodes) as a continuous opening."""
    _CAFE_GROUP_DISPATCH[style](ctx, group, floor_y, floor_h)


def _cafe_group_span(group):
    """Return (x, w, entry_bay) for a bay group.

    The span covers the full zone from first bay's left pier-center to
    last bay's right pier-center, so glass fills the entire area with
    no wall background showing through.
    """
    first, last = group[0], group[-1]
    entry = next((b for b in group if b.is_store_entry), None)

    if len(group) >= 2:
        # Pier gap = space between consecutive bays
        gap = group[1].x_offset - (group[0].x_offset + group[0].width)
        half_pier = gap / 2
    else:
        half_pier = 0.0

    x = first.x_offset - half_pier
    w = (last.x_offset + last.width + half_pier) - x
    return x, w, entry


def _bay_extended(bay, group):
    """Return (bx, bw) for a bay extended to pier centers.

    Each bay's zone runs from the midpoint of the left pier gap to the
    midpoint of the right pier gap, so adjacent bays tile seamlessly.
    """
    idx = group.index(bay)
    # Left edge: midpoint of gap to previous bay (or bay edge if first)
    if idx > 0:
        prev = group[idx - 1]
        gap_left = bay.x_offset - (prev.x_offset + prev.width)
        bx = bay.x_offset - gap_left / 2
    else:
        # First bay — extend by same amount as right side
        if len(group) >= 2:
            gap = group[1].x_offset - (group[0].x_offset + group[0].width)
            bx = bay.x_offset - gap / 2
        else:
            bx = bay.x_offset

    # Right edge: midpoint of gap to next bay (or bay edge if last)
    if idx < len(group) - 1:
        nxt = group[idx + 1]
        gap_right = nxt.x_offset - (bay.x_offset + bay.width)
        bx_right = bay.x_offset + bay.width + gap_right / 2
    else:
        if len(group) >= 2:
            prev = group[idx - 1]
            gap = bay.x_offset - (prev.x_offset + prev.width)
            bx_right = bay.x_offset + bay.width + gap / 2
        else:
            bx_right = bay.x_offset + bay.width

    return bx, bx_right - bx


def _cafe_glass_door(ctx, bx, bw, glass_bot, glass_top, floor_y):
    """Draw entry bay: centered door (half bay width), flanked by windows.

    Layout: [window | door | window]
    - Door is centered, half the bay width, full height from ground.
    - Side windows start at glass_bot (same as other cafe bays) with the
      same kickplate treatment, so only the door goes to the ground.
    """
    door_w = bw / 2
    side_w = (bw - door_w) / 2
    door_x = bx + side_w
    left_x = bx
    right_x = door_x + door_w
    small_kick = 0.15  # small kickplate on the door itself
    kick_gap = glass_bot - floor_y  # kickplate height matches the style's glass_bot
    win_h = glass_top - glass_bot
    transom_y = glass_bot + win_h * 0.80

    # -- Left window: same height as other bays (glass_bot to glass_top) --
    if kick_gap > 0.02:
        ctx.rect(left_x, floor_y, side_w, kick_gap, _C["mullion"], stroke_w=0)
    ctx.rect(left_x, glass_bot, side_w, win_h, _C["window"], stroke_w=1.5)
    _hmul(ctx, left_x, left_x + side_w, transom_y)
    # Sill band below window (only if there's a visible kickplate)
    if kick_gap > 0.10:
        ctx.rect(left_x, glass_bot - 0.06, side_w, 0.06,
                 _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # -- Door (center): full height from ground --
    door_h = glass_top - floor_y
    ctx.rect(door_x, floor_y, door_w, door_h, _C["window"], stroke_w=1.5)
    ctx.rect(door_x, floor_y, door_w, small_kick, _C["mullion"], stroke_w=0)
    _hmul(ctx, door_x, door_x + door_w, transom_y)
    cx = door_x + door_w / 2
    _vmul(ctx, cx, floor_y + small_kick, glass_top)
    handle_y = floor_y + door_h * 0.45
    ctx.rect(cx - 0.06, handle_y, 0.04, 0.12, _C["handle"], stroke_w=0.8)
    ctx.rect(cx + 0.02, handle_y, 0.04, 0.12, _C["handle"], stroke_w=0.8)

    # -- Right window: same height as other bays --
    if kick_gap > 0.02:
        ctx.rect(right_x, floor_y, side_w, kick_gap, _C["mullion"], stroke_w=0)
    ctx.rect(right_x, glass_bot, side_w, win_h, _C["window"], stroke_w=1.5)
    _hmul(ctx, right_x, right_x + side_w, transom_y)
    if kick_gap > 0.10:
        ctx.rect(right_x, glass_bot - 0.06, side_w, 0.06,
                 _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # Thick mullion bars at door edges and outer edges of flanking windows
    _vmul(ctx, left_x, floor_y, glass_top, _MUL_DOOR)       # left outer edge
    _vmul(ctx, door_x, floor_y, glass_top, _MUL_DOOR)       # left door edge
    _vmul(ctx, right_x, floor_y, glass_top, _MUL_DOOR)      # right door edge
    _vmul(ctx, right_x + side_w, floor_y, glass_top, _MUL_DOOR)  # right outer edge


def _cg_bistro_mullions(ctx, group, floor_y, floor_h):
    """Glass panels with prominent vertical mullions + transom per bay."""
    span_x, span_w, entry = _cafe_group_span(group)
    glass_bot, glass_top, glass_h = _opening(floor_y, floor_h)

    # Kickplate band below glass (floor to glass_bot)
    ctx.rect(span_x, floor_y, span_w, _KICK_H, _C["mullion"], stroke_w=0)

    # Continuous glass background (covers pier zones)
    ctx.rect(span_x, glass_bot, span_w, glass_h, _C["window"], stroke_w=1.5)

    # Continuous transom bar at 80%
    transom_y = glass_bot + glass_h * 0.80
    _hmul(ctx, span_x, span_x + span_w, transom_y)

    # Per-bay mullions — 3 vertical divisions using extended bounds
    for bay in group:
        if bay is entry:
            continue
        bx, bw = _bay_extended(bay, group)
        for frac in (0.33, 0.67):
            _vmul(ctx, bx + bw * frac, glass_bot, glass_top)

    # Bay boundary mullion bars (at midpoint of pier gaps)
    for i in range(1, len(group)):
        prev_right = group[i - 1].x_offset + group[i - 1].width
        cur_left = group[i].x_offset
        mid = (prev_right + cur_left) / 2
        _vmul(ctx, mid, glass_bot, glass_top, _MUL_BAY)

    # Sill band
    ctx.rect(span_x - 0.03, glass_bot - 0.06, span_w + 0.06, 0.06,
             _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # Lintel band at top
    ctx.rect(span_x - 0.03, glass_top, span_w + 0.06, 0.08,
             _C["lintel"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # Entry door overlaid
    if entry:
        ex, ew = _bay_extended(entry, group)
        _cafe_glass_door(ctx, ex, ew, glass_bot, glass_top, floor_y)


def _cg_arched(ctx, group, floor_y, floor_h):
    """Semicircular arch tops with keystone per bay."""
    span_x, span_w, entry = _cafe_group_span(group)
    glass_bot, glass_top, glass_h = _opening(floor_y, floor_h)

    # Kickplate band below glass
    ctx.rect(span_x, floor_y, span_w, _KICK_H, _C["mullion"], stroke_w=0)

    # Continuous glass background across full span (covers pier zones)
    ctx.rect(span_x, glass_bot, span_w, glass_h, _C["window"], stroke_w=1.5)

    for bay in group:
        bx, bw = _bay_extended(bay, group)
        if bay is entry:
            _cafe_glass_door(ctx, bx, bw, glass_bot, glass_top, floor_y)
            continue

        # Arch takes up top 30% of glass
        arch_h = glass_h * 0.30
        rect_h = glass_h - arch_h

        cx_a = bx + bw / 2
        cy_a = glass_bot + rect_h

        # Arch outline — thick stone-coloured arc
        steps = 20
        for i in range(steps):
            a1 = math.pi * i / steps
            a2 = math.pi * (i + 1) / steps
            ctx.line(cx_a - (bw / 2) * math.cos(a1), cy_a + arch_h * math.sin(a1),
                     cx_a - (bw / 2) * math.cos(a2), cy_a + arch_h * math.sin(a2),
                     _C["mullion"], 4.0)

        # Keystone at arch crown
        ks_w, ks_h = 0.16, 0.20
        ctx.rect(cx_a - ks_w/2, cy_a + arch_h - ks_h * 0.5, ks_w, ks_h,
                 _C["lintel"], stroke=_C["stone_stroke"], stroke_w=1.0)

        # Center mullion bar (from glass_bot to arch spring)
        _vmul(ctx, cx_a, glass_bot, cy_a)

        # Radial mullions in arch
        for angle_deg in (-30, 30):
            a = math.radians(90 + angle_deg)
            x2 = cx_a + (bw/2 * 0.80) * math.cos(a)
            y2 = cy_a + (arch_h * 0.80) * math.sin(a)
            ctx.line(cx_a, cy_a, x2, y2, _C["mullion"], 3.0)

        # Impost blocks at arch spring points
        imp_w, imp_h = 0.10, 0.08
        for ix in (bx, bx + bw - imp_w):
            ctx.rect(ix, cy_a - imp_h/2, imp_w, imp_h,
                     _C["lintel"], stroke=_C["stone_stroke"], stroke_w=0.5)

    # Bay boundary mullion bars (thin separators at pier midpoints)
    for i in range(1, len(group)):
        prev_right = group[i - 1].x_offset + group[i - 1].width
        cur_left = group[i].x_offset
        mid = (prev_right + cur_left) / 2
        _vmul(ctx, mid, glass_bot, glass_top, _MUL_BAY)

    # Sill band across full span
    ctx.rect(span_x - 0.03, glass_bot - 0.06, span_w + 0.06, 0.06,
             _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)


def _cg_recessed(ctx, group, floor_y, floor_h):
    """Deep recess framing simple glass per bay — each bay in its own shadow box."""
    span_x, span_w, entry = _cafe_group_span(group)
    glass_bot, glass_top, glass_h = _opening(floor_y, floor_h)
    margin = 0.14

    # Kickplate band below glass
    ctx.rect(span_x, floor_y, span_w, _KICK_H, _C["mullion"], stroke_w=0)

    # Continuous glass background (covers pier zones)
    ctx.rect(span_x, glass_bot, span_w, glass_h, _C["window"], stroke_w=1.5)

    for bay in group:
        bx, bw = _bay_extended(bay, group)
        if bay is entry:
            ctx.rect(bx - margin, glass_bot - margin, bw + margin * 2, glass_h + margin * 2,
                     _C["recess"], stroke=_C["recess_stroke"], stroke_w=1.5)
            _cafe_glass_door(ctx, bx, bw, glass_bot, glass_top, floor_y)
            continue

        # Shadow recess frame
        ctx.rect(bx - margin, glass_bot - margin, bw + margin * 2, glass_h + margin,
                 _C["recess"], stroke=_C["recess_stroke"], stroke_w=1.5)
        ctx.rect(bx, glass_bot, bw, glass_h, _C["window"], stroke_w=1.5)

        # Transom bar at 80%
        _hmul(ctx, bx, bx + bw, glass_bot + glass_h * 0.80)

        # Center mullion bar
        _vmul(ctx, bx + bw / 2, glass_bot, glass_top)

    # Sill band
    ctx.rect(span_x - 0.03, glass_bot - 0.06, span_w + 0.06, 0.06,
             _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)


def _cg_knee_wall(ctx, group, floor_y, floor_h):
    """Low stone wall at bottom, tall glass above with mullions."""
    span_x, span_w, entry = _cafe_group_span(group)
    glass_bot, glass_top, glass_h = _opening(floor_y, floor_h)

    # Knee wall = the kickplate zone (floor_y to glass_bot) — stone with coursing
    ctx.rect(span_x, floor_y, span_w, _KICK_H,
             _C["stone"], stroke=_C["stone_stroke"], stroke_w=1.5)
    for frac in (0.35, 0.70):
        ctx.line(span_x, floor_y + _KICK_H * frac,
                 span_x + span_w, floor_y + _KICK_H * frac,
                 _C["stone_stroke"], 1.0)

    # Continuous glass above knee wall
    ctx.rect(span_x, glass_bot, span_w, glass_h, _C["window"], stroke_w=1.5)

    # Per-bay mullion bars using extended bounds
    for bay in group:
        if bay is entry:
            continue
        bx, bw = _bay_extended(bay, group)
        for frac in (0.33, 0.67):
            _vmul(ctx, bx + bw * frac, glass_bot, glass_top)
        _hmul(ctx, bx, bx + bw, glass_top - glass_h * 0.20)

    # Bay boundary mullion bars at pier midpoints
    for i in range(1, len(group)):
        prev_right = group[i - 1].x_offset + group[i - 1].width
        cur_left = group[i].x_offset
        mid = (prev_right + cur_left) / 2
        _vmul(ctx, mid, glass_bot, glass_top, _MUL_BAY)

    # Lintel band
    ctx.rect(span_x - 0.03, glass_top, span_w + 0.06, 0.10,
             _C["lintel"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # Sill band
    ctx.rect(span_x - 0.03, glass_bot - 0.06, span_w + 0.06, 0.06,
             _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # Entry door overlaid (full height)
    if entry:
        ex, ew = _bay_extended(entry, group)
        _cafe_glass_door(ctx, ex, ew, glass_bot, glass_top, floor_y)


def _cg_pilaster_frame(ctx, group, floor_y, floor_h):
    """Stone pilasters between bays, lintel band across top."""
    span_x, span_w, entry = _cafe_group_span(group)
    glass_bot, glass_top, glass_h = _opening(floor_y, floor_h)
    pil_w = 0.20

    # Kickplate band below glass
    ctx.rect(span_x, floor_y, span_w, _KICK_H, _C["mullion"], stroke_w=0)

    # Continuous glass background (covers pier zones)
    ctx.rect(span_x, glass_bot, span_w, glass_h, _C["window"], stroke_w=1.5)

    # Lintel/entablature across full span
    ctx.rect(span_x - 0.03, glass_top, span_w + 0.06, 0.14,
             _C["lintel"], stroke=_C["stone_stroke"], stroke_w=1.0)

    for bay in group:
        bx, bw = _bay_extended(bay, group)
        if bay is entry:
            _cafe_glass_door(ctx, bx + pil_w, bw - pil_w * 2,
                             glass_bot, glass_top, floor_y)
        else:
            # Center mullion bar
            _vmul(ctx, bx + bw / 2, glass_bot, glass_top)
            # Transom bar
            gx = bx + pil_w
            gw = bw - pil_w * 2
            _hmul(ctx, gx, gx + gw, glass_bot + glass_h * 0.78)

        # Pilasters on both sides of each bay
        for px in (bx, bx + bw - pil_w):
            ctx.rect(px, floor_y, pil_w, glass_h + _KICK_H + 0.14,
                     _C["lintel"], stroke=_C["stone_stroke"], stroke_w=1.2)
            # Capital
            ctx.rect(px - 0.03, glass_top - 0.03, pil_w + 0.06, 0.08,
                     _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)
            # Base
            ctx.rect(px - 0.02, floor_y, pil_w + 0.04, 0.08,
                     _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.5)

    # Sill band
    ctx.rect(span_x - 0.03, glass_bot - 0.06, span_w + 0.06, 0.06,
             _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)


# =====================================================================
# OPEN TERRACE CAFE RENDERERS (glass to ground, spanning across bays)
# =====================================================================

def _cg_full_span(ctx, group, floor_y, floor_h):
    """T1: Full-span glass, thin metal mullions replace piers."""
    span_x, span_w, entry = _cafe_group_span(group)
    glass_top = floor_y + floor_h * _OPEN_FRAC
    glass_h = glass_top - floor_y
    small_kick = 0.10

    # Small kickplate at ground
    ctx.rect(span_x, floor_y, span_w, small_kick, _C["mullion"], stroke_w=0)

    # Full-span glass from ground to top
    ctx.rect(span_x, floor_y + small_kick, span_w, glass_h - small_kick,
             _C["window"], stroke_w=1.5)

    # Thin metal mullions at each bay boundary (replacing stone piers)
    for i in range(1, len(group)):
        prev_right = group[i - 1].x_offset + group[i - 1].width
        cur_left = group[i].x_offset
        mid = (prev_right + cur_left) / 2
        _vmul(ctx, mid, floor_y, glass_top, _MUL_W)

    # Per-bay vertical subdivisions
    for bay in group:
        if bay is entry:
            continue
        bx, bw = _bay_extended(bay, group)
        for frac in (0.33, 0.67):
            _vmul(ctx, bx + bw * frac, floor_y + small_kick, glass_top)

    # Continuous transom bar
    transom_y = floor_y + glass_h * 0.82
    _hmul(ctx, span_x, span_x + span_w, transom_y)

    # Lintel band
    ctx.rect(span_x - 0.03, glass_top, span_w + 0.06, 0.08,
             _C["lintel"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # Entry door
    if entry:
        ex, ew = _bay_extended(entry, group)
        _cafe_glass_door(ctx, ex, ew, floor_y + small_kick, glass_top, floor_y)


def _cg_kickplate_glass(ctx, group, floor_y, floor_h):
    """T2: 15cm stone base, full glass above spanning across bays."""
    span_x, span_w, entry = _cafe_group_span(group)
    glass_top = floor_y + floor_h * _OPEN_FRAC
    kick = 0.15

    # Stone kickplate base with coursing
    ctx.rect(span_x, floor_y, span_w, kick,
             _C["stone"], stroke=_C["stone_stroke"], stroke_w=1.0)
    ctx.line(span_x, floor_y + kick * 0.5,
             span_x + span_w, floor_y + kick * 0.5,
             _C["stone_stroke"], 0.5)

    # Full glass above kickplate
    glass_bot = floor_y + kick
    glass_h = glass_top - glass_bot
    ctx.rect(span_x, glass_bot, span_w, glass_h, _C["window"], stroke_w=1.5)

    # Per-bay mullions
    for bay in group:
        if bay is entry:
            continue
        bx, bw = _bay_extended(bay, group)
        _vmul(ctx, bx + bw / 2, glass_bot, glass_top)

    # Bay boundary mullions
    for i in range(1, len(group)):
        prev_right = group[i - 1].x_offset + group[i - 1].width
        mid = (prev_right + group[i].x_offset) / 2
        _vmul(ctx, mid, floor_y, glass_top, _MUL_BAY)

    # Transom
    transom_y = glass_bot + glass_h * 0.80
    _hmul(ctx, span_x, span_x + span_w, transom_y)

    # Lintel band
    ctx.rect(span_x - 0.03, glass_top, span_w + 0.06, 0.10,
             _C["lintel"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # Entry door
    if entry:
        ex, ew = _bay_extended(entry, group)
        _cafe_glass_door(ctx, ex, ew, glass_bot, glass_top, floor_y)


def _cg_narrow_piers(ctx, group, floor_y, floor_h):
    """T3: Thin stone piers between glass bays, dark lintel band."""
    span_x, span_w, entry = _cafe_group_span(group)
    glass_top = floor_y + floor_h * _OPEN_FRAC
    glass_h = glass_top - floor_y
    small_kick = 0.10
    pier_w = 0.14

    # Small kickplate
    ctx.rect(span_x, floor_y, span_w, small_kick, _C["mullion"], stroke_w=0)

    # Glass per bay (with gaps for narrow stone piers)
    for bay in group:
        bx, bw = _bay_extended(bay, group)
        ctx.rect(bx, floor_y + small_kick, bw, glass_h - small_kick,
                 _C["window"], stroke_w=1.5)
        if bay is not entry:
            _vmul(ctx, bx + bw / 2, floor_y + small_kick, glass_top)

    # Narrow stone piers at bay boundaries
    for i in range(1, len(group)):
        prev_right = group[i - 1].x_offset + group[i - 1].width
        cur_left = group[i].x_offset
        mid = (prev_right + cur_left) / 2
        ctx.rect(mid - pier_w / 2, floor_y, pier_w, glass_h + 0.10,
                 _C["lintel"], stroke=_C["stone_stroke"], stroke_w=1.0)

    # Transom bar per bay
    transom_y = floor_y + glass_h * 0.82
    for bay in group:
        if bay is not entry:
            bx, bw = _bay_extended(bay, group)
            _hmul(ctx, bx, bx + bw, transom_y)

    # Dark lintel band across top
    ctx.rect(span_x - 0.03, glass_top, span_w + 0.06, 0.12,
             "#4A4A5A", stroke="#3A3A4A", stroke_w=1.0)

    # Entry door
    if entry:
        ex, ew = _bay_extended(entry, group)
        _cafe_glass_door(ctx, ex, ew, floor_y + small_kick, glass_top, floor_y)


def _cg_open_terrace(ctx, group, floor_y, floor_h):
    """T4: Open-air terrace — alternating open and glazed panels."""
    span_x, span_w, entry = _cafe_group_span(group)
    glass_top = floor_y + floor_h * _OPEN_FRAC
    glass_h = glass_top - floor_y
    small_kick = 0.10
    post_w = 0.10

    # Small kickplate
    ctx.rect(span_x, floor_y, span_w, small_kick, _C["mullion"], stroke_w=0)

    # Warm frame/lintel band across top
    ctx.rect(span_x - 0.03, glass_top, span_w + 0.06, 0.10,
             _C["awning_gold"], stroke=_C["stone_stroke"], stroke_w=0.8)

    for idx, bay in enumerate(group):
        bx, bw = _bay_extended(bay, group)

        if bay is entry:
            _cafe_glass_door(ctx, bx, bw, floor_y + small_kick, glass_top, floor_y)
            continue

        # Alternate: even bays glazed, odd bays open
        if idx % 2 == 0:
            # Glazed panel
            ctx.rect(bx, floor_y + small_kick, bw, glass_h - small_kick,
                     _C["window"], stroke_w=1.5)
            _vmul(ctx, bx + bw / 2, floor_y + small_kick, glass_top)
            transom_y = floor_y + glass_h * 0.82
            _hmul(ctx, bx, bx + bw, transom_y)
        else:
            # Open panel — just the frame outline, lighter fill
            ctx.rect(bx, floor_y + small_kick, bw, glass_h - small_kick,
                     "#C8C0B0", stroke=_C["stone_stroke"], stroke_w=1.0)
            # Thin railing bar at mid-height
            rail_y = floor_y + glass_h * 0.35
            ctx.line(bx, rail_y, bx + bw, rail_y, _C["iron"], 1.5)
            # Vertical posts
            for frac in (0.0, 0.5, 1.0):
                px = bx + bw * frac
                ctx.rect(px - post_w / 2, floor_y, post_w, glass_h,
                         _C["awning_gold"], stroke=_C["stone_stroke"], stroke_w=0.5)

    # Vertical posts at bay boundaries
    for i in range(1, len(group)):
        prev_right = group[i - 1].x_offset + group[i - 1].width
        mid = (prev_right + group[i].x_offset) / 2
        ctx.rect(mid - post_w / 2, floor_y, post_w, glass_h + 0.10,
                 _C["awning_gold"], stroke=_C["stone_stroke"], stroke_w=0.8)


_CAFE_GROUP_DISPATCH = {
    CafeStyle.BISTRO_MULLIONS: _cg_bistro_mullions,
    CafeStyle.ARCHED: _cg_arched,
    CafeStyle.RECESSED: _cg_recessed,
    CafeStyle.KNEE_WALL: _cg_knee_wall,
    CafeStyle.PILASTER_FRAME: _cg_pilaster_frame,
    CafeStyle.FULL_SPAN: _cg_full_span,
    CafeStyle.KICKPLATE_GLASS: _cg_kickplate_glass,
    CafeStyle.NARROW_PIERS: _cg_narrow_piers,
    CafeStyle.OPEN_TERRACE: _cg_open_terrace,
}


# =====================================================================
# STOREFRONT GROUP RENDERERS
# =====================================================================

def render_storefront_group(ctx, style: StorefrontStyle, group: list,
                            floor_y: float, floor_h: float):
    """Render a storefront/boutique group (list of BayNodes)."""
    _STOREFRONT_GROUP_DISPATCH[style](ctx, group, floor_y, floor_h)


def _sf_shop_door(ctx, bx, bw, glass_bot, glass_top, floor_y):
    """Draw entry bay: centered door (half bay width), flanked by windows.

    Side windows match other bays (start at glass_bot with kickplate).
    Only the door goes to the ground.
    """
    door_w = bw / 2
    side_w = (bw - door_w) / 2
    door_x = bx + side_w
    left_x = bx
    right_x = door_x + door_w
    small_kick = 0.15
    win_h = glass_top - glass_bot
    transom_y = glass_bot + win_h * 0.80

    # -- Left window: same height as other bays --
    ctx.rect(left_x, floor_y, side_w, _KICK_H, _C["mullion"], stroke_w=0)
    ctx.rect(left_x, glass_bot, side_w, win_h, _C["window"], stroke_w=1.5)
    _hmul(ctx, left_x, left_x + side_w, transom_y)
    ctx.rect(left_x, glass_bot - 0.06, side_w, 0.06,
             _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # -- Door (center): full height from ground --
    door_h = glass_top - floor_y
    ctx.rect(door_x, floor_y, door_w, door_h, _C["window"], stroke_w=1.5)
    ctx.rect(door_x, floor_y, door_w, small_kick, _C["mullion"], stroke_w=0)
    _hmul(ctx, door_x, door_x + door_w, transom_y)
    cx = door_x + door_w / 2
    _vmul(ctx, cx, floor_y + small_kick, glass_top)
    handle_y = floor_y + door_h * 0.45
    ctx.rect(cx + 0.02, handle_y, 0.04, 0.12, _C["handle"], stroke_w=0.8)

    # -- Right window: same height as other bays --
    ctx.rect(right_x, floor_y, side_w, _KICK_H, _C["mullion"], stroke_w=0)
    ctx.rect(right_x, glass_bot, side_w, win_h, _C["window"], stroke_w=1.5)
    _hmul(ctx, right_x, right_x + side_w, transom_y)
    ctx.rect(right_x, glass_bot - 0.06, side_w, 0.06,
             _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # Thick mullion bars at door edges and outer edges of flanking windows
    _vmul(ctx, left_x, floor_y, glass_top, _MUL_DOOR)       # left outer edge
    _vmul(ctx, door_x, floor_y, glass_top, _MUL_DOOR)       # left door edge
    _vmul(ctx, right_x, floor_y, glass_top, _MUL_DOOR)      # right door edge
    _vmul(ctx, right_x + side_w, floor_y, glass_top, _MUL_DOOR)  # right outer edge


def _sg_classic(ctx, group, floor_y, floor_h):
    """Traditional: continuous display window + signage band + shop door."""
    span_x, span_w, entry = _cafe_group_span(group)
    glass_bot, glass_top, glass_h = _opening(floor_y, floor_h)

    # Kickplate band below glass
    ctx.rect(span_x, floor_y, span_w, _KICK_H, _C["mullion"], stroke_w=0)

    # Continuous display window (covers pier zones)
    ctx.rect(span_x, glass_bot, span_w, glass_h, _C["window"], stroke_w=1.5)

    # Transom bar at 80%
    _hmul(ctx, span_x, span_x + span_w, glass_bot + glass_h * 0.80)

    # Per-bay center mullion bars + bay boundary bars
    for bay in group:
        if bay is not entry:
            bx, bw = _bay_extended(bay, group)
            _vmul(ctx, bx + bw / 2, glass_bot, glass_top)
    for i in range(1, len(group)):
        prev_right = group[i - 1].x_offset + group[i - 1].width
        mid = (prev_right + group[i].x_offset) / 2
        _vmul(ctx, mid, glass_bot, glass_top, _MUL_BAY)

    # Entry door overlaid
    if entry:
        ex, ew = _bay_extended(entry, group)
        _sf_shop_door(ctx, ex, ew, glass_bot, glass_top, floor_y)

    # Signage band
    ctx.rect(span_x - 0.03, glass_top, span_w + 0.06, 0.22,
             _C["lintel"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # Sill
    ctx.rect(span_x - 0.03, glass_bot - 0.06, span_w + 0.06, 0.06,
             _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)


def _sg_display_window(ctx, group, floor_y, floor_h):
    """Large plate glass — maximum transparency, minimal frame."""
    span_x, span_w, entry = _cafe_group_span(group)
    glass_bot, glass_top, glass_h = _opening(floor_y, floor_h)

    # Kickplate band below glass
    ctx.rect(span_x, floor_y, span_w, _KICK_H, _C["mullion"], stroke_w=0)

    # Continuous pane (covers pier zones)
    ctx.rect(span_x, glass_bot, span_w, glass_h, _C["window"], stroke_w=1.5)

    # Bay boundary bars at pier midpoints
    for i in range(1, len(group)):
        prev_right = group[i - 1].x_offset + group[i - 1].width
        mid = (prev_right + group[i].x_offset) / 2
        _vmul(ctx, mid, glass_bot, glass_top, _MUL_BAY)

    # Entry door
    if entry:
        ex, ew = _bay_extended(entry, group)
        _sf_shop_door(ctx, ex, ew, glass_bot, glass_top, floor_y)

    # Lintel
    ctx.rect(span_x - 0.03, glass_top, span_w + 0.06, 0.08,
             _C["lintel"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # Sill
    ctx.rect(span_x - 0.03, glass_bot - 0.06, span_w + 0.06, 0.06,
             _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)


def _sg_recessed_entry(ctx, group, floor_y, floor_h):
    """Recessed entry with display windows flanking."""
    span_x, span_w, entry = _cafe_group_span(group)
    glass_bot, glass_top, glass_h = _opening(floor_y, floor_h)

    # Kickplate band below glass
    ctx.rect(span_x, floor_y, span_w, _KICK_H, _C["mullion"], stroke_w=0)

    # Continuous display window (covers pier zones)
    ctx.rect(span_x, glass_bot, span_w, glass_h, _C["window"], stroke_w=1.5)

    # Center mullion bars + bay boundaries at pier midpoints
    for bay in group:
        if bay is not entry:
            bx, bw = _bay_extended(bay, group)
            _vmul(ctx, bx + bw / 2, glass_bot, glass_top)
    for i in range(1, len(group)):
        prev_right = group[i - 1].x_offset + group[i - 1].width
        mid = (prev_right + group[i].x_offset) / 2
        _vmul(ctx, mid, glass_bot, glass_top, _MUL_BAY)

    # Transom bar
    _hmul(ctx, span_x, span_x + span_w, glass_bot + glass_h * 0.80)

    # Recessed entry door
    if entry:
        ex, ew = _bay_extended(entry, group)
        recess = 0.15
        ctx.rect(ex + recess, floor_y, ew - recess * 2, glass_top - floor_y + recess,
                 _C["recess"], stroke=_C["recess_stroke"], stroke_w=1.5)
        _sf_shop_door(ctx, ex, ew, glass_bot, glass_top, floor_y)

    # Signage band
    ctx.rect(span_x - 0.03, glass_top, span_w + 0.06, 0.18,
             _C["lintel"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # Sill
    ctx.rect(span_x - 0.03, glass_bot - 0.06, span_w + 0.06, 0.06,
             _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)


def _sg_pilastered(ctx, group, floor_y, floor_h):
    """Stone pilasters framing each bay."""
    span_x, span_w, entry = _cafe_group_span(group)
    pil_w = 0.20
    glass_bot, glass_top, glass_h = _opening(floor_y, floor_h)

    # Kickplate band below glass
    ctx.rect(span_x, floor_y, span_w, _KICK_H, _C["mullion"], stroke_w=0)

    # Continuous glass background (covers pier zones)
    ctx.rect(span_x, glass_bot, span_w, glass_h, _C["window"], stroke_w=1.5)

    for bay in group:
        bx, bw = _bay_extended(bay, group)
        if bay is entry:
            _sf_shop_door(ctx, bx + pil_w, bw - pil_w * 2,
                          glass_bot, glass_top, floor_y)
        else:
            # Center mullion bar
            _vmul(ctx, bx + bw / 2, glass_bot, glass_top)
            # Transom bar
            gx = bx + pil_w
            gw = bw - pil_w * 2
            _hmul(ctx, gx, gx + gw, glass_bot + glass_h * 0.78)

        # Pilasters — wide stone columns
        for px in (bx, bx + bw - pil_w):
            ctx.rect(px, floor_y, pil_w, glass_h + _KICK_H + 0.14,
                     _C["lintel"], stroke=_C["stone_stroke"], stroke_w=1.2)
            ctx.rect(px - 0.03, glass_top - 0.03, pil_w + 0.06, 0.08,
                     _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)
            ctx.rect(px - 0.02, floor_y, pil_w + 0.04, 0.08,
                     _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.5)

    # Lintel band
    ctx.rect(span_x - 0.03, glass_top, span_w + 0.06, 0.12,
             _C["lintel"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # Sill
    ctx.rect(span_x - 0.03, glass_bot - 0.06, span_w + 0.06, 0.06,
             _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)


def _sg_minimal(ctx, group, floor_y, floor_h):
    """Simple opening, minimal frame."""
    span_x, span_w, entry = _cafe_group_span(group)
    glass_bot, glass_top, glass_h = _opening(floor_y, floor_h)

    # Kickplate band below glass
    ctx.rect(span_x, floor_y, span_w, _KICK_H, _C["mullion"], stroke_w=0)

    # Continuous window (covers pier zones)
    ctx.rect(span_x, glass_bot, span_w, glass_h, _C["window"], stroke_w=1.5)

    # Bay divider bars at pier midpoints
    for i in range(1, len(group)):
        prev_right = group[i - 1].x_offset + group[i - 1].width
        mid = (prev_right + group[i].x_offset) / 2
        _vmul(ctx, mid, glass_bot, glass_top, _MUL_BAY)

    # Entry door
    if entry:
        ex, ew = _bay_extended(entry, group)
        _sf_shop_door(ctx, ex, ew, glass_bot, glass_top, floor_y)

    # Lintel
    ctx.rect(span_x - 0.03, glass_top, span_w + 0.06, 0.06,
             _C["lintel"], stroke=_C["stone_stroke"], stroke_w=0.8)

    # Sill
    ctx.rect(span_x - 0.03, glass_bot - 0.06, span_w + 0.06, 0.06,
             _C["sill"], stroke=_C["stone_stroke"], stroke_w=0.8)


_STOREFRONT_GROUP_DISPATCH = {
    StorefrontStyle.CLASSIC: _sg_classic,
    StorefrontStyle.DISPLAY_WINDOW: _sg_display_window,
    StorefrontStyle.RECESSED_ENTRY: _sg_recessed_entry,
    StorefrontStyle.PILASTERED: _sg_pilastered,
    StorefrontStyle.MINIMAL: _sg_minimal,
}


# =====================================================================
# DOOR (PORTE-COCHERE) RENDERERS
# =====================================================================

def render_door(ctx, style: DoorStyle, x: float, y: float,
                w: float, h: float):
    """Render a porte-cochère / building entrance in the given style."""
    _DOOR_DISPATCH[style](ctx, x, y, w, h)


def _door_arched_classic(ctx, x, y, w, h):
    """Traditional stone arch with keystone and wooden doors."""
    arch_h = w * 0.35
    rect_h = h - arch_h
    # Rectangular lower
    ctx.rect(x, y, w, rect_h, _C["door"], stroke_w=1.2)
    # Arch
    cx = x + w / 2
    cy = y + rect_h
    steps = 12
    pts = [(x, cy)]
    for i in range(steps + 1):
        a = math.pi * i / steps
        pts.append((cx - (w / 2) * math.cos(a), cy + arch_h * math.sin(a)))
    pts.append((x + w, cy))
    ctx.polygon(pts, _C["door"], stroke_w=1.2)
    # Keystone
    ctx.rect(cx - 0.06, cy + arch_h - 0.05, 0.12, 0.10,
             _C["lintel"], stroke=_C["stone_stroke"], stroke_w=0.5)
    # Door split
    ctx.line(cx, y, cx, y + rect_h, _C["mullion"], 2.0)
    # Panels
    panel_w = w * 0.35
    panel_h = rect_h * 0.35
    for dx in (x + (w / 2 - panel_w) / 2, cx + (w / 2 - panel_w) / 2):
        for dy_frac in (0.15, 0.55):
            ctx.rect(dx, y + rect_h * dy_frac, panel_w, panel_h,
                     _C["door_panel"], stroke=_C["door_dark"], stroke_w=0.5)
    # Handle
    ctx.rect(cx - 0.05, y + rect_h * 0.48, 0.04, 0.10, _C["handle"], stroke_w=0.5)
    ctx.rect(cx + 0.01, y + rect_h * 0.48, 0.04, 0.10, _C["handle"], stroke_w=0.5)


def _door_flat_panel(ctx, x, y, w, h):
    """Flat lintel with wooden paneled door."""
    ctx.rect(x, y, w, h, _C["door"], stroke_w=1.2)
    # Lintel
    ctx.rect(x - 0.04, y + h - 0.08, w + 0.08, 0.08,
             _C["lintel"], stroke=_C["stone_stroke"], stroke_w=0.5)
    # Door split
    cx = x + w / 2
    ctx.line(cx, y, cx, y + h - 0.08, _C["mullion"], 2.0)
    # Panels (3 rows)
    panel_w = w * 0.35
    for dx in (x + (w / 2 - panel_w) / 2, cx + (w / 2 - panel_w) / 2):
        for frac in (0.08, 0.38, 0.68):
            ctx.rect(dx, y + h * frac, panel_w, h * 0.22,
                     _C["door_panel"], stroke=_C["door_dark"], stroke_w=0.5)
    # Handle
    ctx.rect(cx - 0.05, y + h * 0.45, 0.04, 0.10, _C["handle"], stroke_w=0.5)
    ctx.rect(cx + 0.01, y + h * 0.45, 0.04, 0.10, _C["handle"], stroke_w=0.5)


def _door_double_leaf(ctx, x, y, w, h):
    """Double doors with glass upper panels."""
    ctx.rect(x, y, w, h, _C["door"], stroke_w=1.2)
    cx = x + w / 2
    ctx.line(cx, y, cx, y + h, _C["mullion"], 2.0)
    # Glass upper panels
    glass_h = h * 0.40
    glass_y = y + h * 0.45
    margin = w * 0.08
    for dx in (x + margin, cx + margin):
        pw = w / 2 - margin * 2
        ctx.rect(dx, glass_y, pw, glass_h, _C["door_glass"], stroke_w=0.8)
        # Mullion cross
        ctx.line(dx + pw / 2, glass_y, dx + pw / 2, glass_y + glass_h,
                 _C["mullion"], 1.0)
        ctx.line(dx, glass_y + glass_h / 2, dx + pw, glass_y + glass_h / 2,
                 _C["mullion"], 1.0)
    # Handle
    ctx.rect(cx - 0.05, y + h * 0.40, 0.04, 0.10, _C["handle"], stroke_w=0.5)
    ctx.rect(cx + 0.01, y + h * 0.40, 0.04, 0.10, _C["handle"], stroke_w=0.5)


def _door_glass_topped(ctx, x, y, w, h):
    """Solid lower half, fanlight above."""
    split = h * 0.55
    # Lower solid
    ctx.rect(x, y, w, split, _C["door"], stroke_w=1.2)
    # Upper fanlight
    cx = x + w / 2
    fan_h = h - split
    ctx.rect(x, y + split, w, fan_h, _C["door_glass"], stroke_w=1.2)
    # Radial mullions
    for angle_deg in (-40, -20, 0, 20, 40):
        a = math.radians(angle_deg)
        ctx.line(cx, y + split, cx + (w / 2) * math.sin(a),
                 y + split + fan_h * math.cos(a), _C["mullion"], 1.0)
    # Door split + panels
    ctx.line(cx, y, cx, y + split, _C["mullion"], 2.0)
    panel_w = w * 0.35
    for dx in (x + (w / 2 - panel_w) / 2, cx + (w / 2 - panel_w) / 2):
        ctx.rect(dx, y + split * 0.10, panel_w, split * 0.35,
                 _C["door_panel"], stroke=_C["door_dark"], stroke_w=0.5)
        ctx.rect(dx, y + split * 0.55, panel_w, split * 0.35,
                 _C["door_panel"], stroke=_C["door_dark"], stroke_w=0.5)
    ctx.rect(cx - 0.05, y + split * 0.45, 0.04, 0.10, _C["handle"], stroke_w=0.5)
    ctx.rect(cx + 0.01, y + split * 0.45, 0.04, 0.10, _C["handle"], stroke_w=0.5)


def _door_ornate_carved(ctx, x, y, w, h):
    """Heavy carved wood with iron studs."""
    ctx.rect(x, y, w, h, _C["door_dark"], stroke_w=1.2)
    cx = x + w / 2
    ctx.line(cx, y, cx, y + h, _C["mullion"], 2.5)
    # Carved panels (3 rows per leaf)
    panel_w = w * 0.33
    panel_h = h * 0.18
    for dx in (x + (w / 2 - panel_w) / 2, cx + (w / 2 - panel_w) / 2):
        for frac in (0.08, 0.35, 0.65):
            ctx.rect(dx, y + h * frac, panel_w, panel_h,
                     _C["door_panel"], stroke=_C["door"], stroke_w=0.8)
    # Iron studs (dots)
    stud_r = 0.03
    for sx in (x + w * 0.12, x + w * 0.88):
        for sy_frac in (0.15, 0.50, 0.85):
            ctx.rect(sx - stud_r, y + h * sy_frac - stud_r,
                     stud_r * 2, stud_r * 2, _C["iron"], stroke_w=0.3)
    # Heavy ring handle
    ctx.rect(cx - 0.07, y + h * 0.45, 0.05, 0.12, _C["iron"], stroke_w=0.5)
    ctx.rect(cx + 0.02, y + h * 0.45, 0.05, 0.12, _C["iron"], stroke_w=0.5)


_DOOR_DISPATCH = {
    DoorStyle.ARCHED_CLASSIC: _door_arched_classic,
    DoorStyle.FLAT_PANEL: _door_flat_panel,
    DoorStyle.DOUBLE_LEAF: _door_double_leaf,
    DoorStyle.GLASS_TOPPED: _door_glass_topped,
    DoorStyle.ORNATE_CARVED: _door_ornate_carved,
}


# =====================================================================
# BALCONY RENDERERS (continuous + balconette)
# =====================================================================

def render_continuous_balcony(ctx, style: BalconyStyle,
                              span_left: float, span_right: float,
                              floor_y: float, railing_h: float,
                              bal_left: float, bal_right: float):
    """Render a continuous balcony spanning the bay extent."""
    _BALCONY_DISPATCH[style](ctx, span_left, span_right, floor_y,
                             railing_h, bal_left, bal_right)


def render_balconette(ctx, style: BalconyStyle,
                      x: float, y: float, width: float):
    """Render an individual balconette railing."""
    _BALCONETTE_DISPATCH[style](ctx, x, y, width)


# -- Continuous balcony helpers --

def _bal_slab(ctx, span_left, span_right, floor_y, bal_left, bal_right):
    """Draw the balcony slab + supports (shared by all styles)."""
    slab_h = 0.06
    ctx.rect(span_left, floor_y - slab_h, span_right - span_left, slab_h,
             _C["balcony_floor"], stroke=_C["cornice_stroke"], stroke_w=0.5)
    # Bracket supports
    n_brackets = max(2, int((bal_right - bal_left) / 1.5))
    step = (bal_right - bal_left) / (n_brackets - 1) if n_brackets > 1 else 0
    for i in range(n_brackets):
        bx = bal_left + i * step
        ctx.polygon([
            (bx - 0.04, floor_y - slab_h),
            (bx + 0.04, floor_y - slab_h),
            (bx, floor_y - slab_h - 0.10),
        ], _C["cornice"], stroke=_C["cornice_stroke"], stroke_w=0.3)


def _bal_classic_scroll(ctx, sl, sr, fy, rh, bl, br):
    """Ornate scrollwork — Haussmann standard."""
    _bal_slab(ctx, sl, sr, fy, bl, br)
    rail_y = fy
    top_y = fy + rh
    span = sr - sl
    # Top rail
    ctx.line(sl, top_y, sr, top_y, _C["rail"], 2.0)
    ctx.line(sl, top_y - 0.04, sr, top_y - 0.04, _C["iron"], 1.0)
    # Bottom rail
    ctx.line(sl, rail_y + 0.03, sr, rail_y + 0.03, _C["iron"], 1.0)
    # Vertical bars with scroll tops
    n_bars = max(3, int(span / 0.12))
    step = span / n_bars
    for i in range(n_bars + 1):
        bx = sl + i * step
        ctx.line(bx, rail_y + 0.03, bx, top_y - 0.04, _C["iron"], 0.8)
    # Mid-rail
    mid_y = fy + rh * 0.5
    ctx.line(sl, mid_y, sr, mid_y, _C["iron"], 0.6)
    # Scroll motifs (circles at intervals)
    n_scrolls = max(2, int(span / 0.35))
    scroll_step = span / n_scrolls
    for i in range(n_scrolls):
        cx = sl + (i + 0.5) * scroll_step
        r = min(0.06, scroll_step * 0.25)
        pts = []
        for s in range(9):
            a = math.pi * 2 * s / 8
            pts.append((cx + r * math.cos(a), mid_y + 0.12 + r * math.sin(a)))
        ctx.polygon(pts, _C["iron"], stroke=_C["iron"], stroke_w=0.5)


def _bal_geometric(ctx, sl, sr, fy, rh, bl, br):
    """Rectilinear pattern."""
    _bal_slab(ctx, sl, sr, fy, bl, br)
    rail_y = fy
    top_y = fy + rh
    span = sr - sl
    ctx.line(sl, top_y, sr, top_y, _C["rail"], 2.0)
    ctx.line(sl, rail_y + 0.03, sr, rail_y + 0.03, _C["iron"], 1.0)
    # Horizontal rails
    for frac in (0.33, 0.67):
        ctx.line(sl, fy + rh * frac, sr, fy + rh * frac, _C["iron"], 0.8)
    # Vertical bars
    n_bars = max(3, int(span / 0.15))
    step = span / n_bars
    for i in range(n_bars + 1):
        bx = sl + i * step
        ctx.line(bx, rail_y + 0.03, bx, top_y, _C["iron"], 0.8)


def _bal_simple_bars(ctx, sl, sr, fy, rh, bl, br):
    """Plain vertical bars."""
    _bal_slab(ctx, sl, sr, fy, bl, br)
    rail_y = fy
    top_y = fy + rh
    span = sr - sl
    ctx.line(sl, top_y, sr, top_y, _C["rail"], 2.0)
    ctx.line(sl, rail_y + 0.03, sr, rail_y + 0.03, _C["iron"], 1.0)
    n_bars = max(3, int(span / 0.10))
    step = span / n_bars
    for i in range(n_bars + 1):
        bx = sl + i * step
        ctx.line(bx, rail_y + 0.03, bx, top_y, _C["iron"], 0.8)


def _bal_art_nouveau(ctx, sl, sr, fy, rh, bl, br):
    """Organic flowing curves."""
    _bal_slab(ctx, sl, sr, fy, bl, br)
    rail_y = fy
    top_y = fy + rh
    span = sr - sl
    ctx.line(sl, top_y, sr, top_y, _C["rail"], 2.0)
    ctx.line(sl, rail_y + 0.03, sr, rail_y + 0.03, _C["iron"], 1.0)
    # Flowing wave pattern at mid height
    mid_y = fy + rh * 0.5
    n_waves = max(3, int(span / 0.30))
    wave_w = span / n_waves
    for i in range(n_waves):
        wx = sl + i * wave_w
        pts = []
        for s in range(9):
            t = s / 8
            px = wx + t * wave_w
            py = mid_y + 0.08 * math.sin(t * math.pi * 2)
            pts.append((px, py))
        for j in range(len(pts) - 1):
            ctx.line(pts[j][0], pts[j][1], pts[j + 1][0], pts[j + 1][1],
                     _C["iron"], 0.8)
    # Verticals
    n_bars = max(3, int(span / 0.18))
    step = span / n_bars
    for i in range(n_bars + 1):
        bx = sl + i * step
        ctx.line(bx, rail_y + 0.03, bx, top_y, _C["iron"], 0.6)


def _bal_greek_key(ctx, sl, sr, fy, rh, bl, br):
    """Greek key / meander pattern."""
    _bal_slab(ctx, sl, sr, fy, bl, br)
    rail_y = fy
    top_y = fy + rh
    span = sr - sl
    ctx.line(sl, top_y, sr, top_y, _C["rail"], 2.0)
    ctx.line(sl, rail_y + 0.03, sr, rail_y + 0.03, _C["iron"], 1.0)
    # Horizontal bands
    for frac in (0.30, 0.70):
        ctx.line(sl, fy + rh * frac, sr, fy + rh * frac, _C["iron"], 0.8)
    # Vertical bars in pairs
    n_pairs = max(2, int(span / 0.25))
    step = span / n_pairs
    for i in range(n_pairs):
        bx = sl + i * step
        ctx.line(bx + step * 0.3, rail_y + 0.03, bx + step * 0.3, top_y, _C["iron"], 0.6)
        ctx.line(bx + step * 0.7, rail_y + 0.03, bx + step * 0.7, top_y, _C["iron"], 0.6)


_BALCONY_DISPATCH = {
    BalconyStyle.CLASSIC_SCROLL: _bal_classic_scroll,
    BalconyStyle.GEOMETRIC: _bal_geometric,
    BalconyStyle.SIMPLE_BARS: _bal_simple_bars,
    BalconyStyle.ART_NOUVEAU: _bal_art_nouveau,
    BalconyStyle.GREEK_KEY: _bal_greek_key,
}


# -- Balconette helpers --

def _bte_classic(ctx, x, y, w):
    h = 0.45
    ctx.line(x, y + h, x + w, y + h, _C["rail"], 1.5)
    ctx.line(x, y + 0.02, x + w, y + 0.02, _C["iron"], 0.8)
    n = max(3, int(w / 0.10))
    step = w / n
    for i in range(n + 1):
        ctx.line(x + i * step, y + 0.02, x + i * step, y + h, _C["iron"], 0.6)
    ctx.line(x, y + h * 0.5, x + w, y + h * 0.5, _C["iron"], 0.4)


def _bte_geometric(ctx, x, y, w):
    h = 0.45
    ctx.line(x, y + h, x + w, y + h, _C["rail"], 1.5)
    ctx.line(x, y + 0.02, x + w, y + 0.02, _C["iron"], 0.8)
    for frac in (0.33, 0.67):
        ctx.line(x, y + h * frac, x + w, y + h * frac, _C["iron"], 0.6)
    n = max(3, int(w / 0.12))
    step = w / n
    for i in range(n + 1):
        ctx.line(x + i * step, y + 0.02, x + i * step, y + h, _C["iron"], 0.6)


def _bte_simple(ctx, x, y, w):
    h = 0.40
    ctx.line(x, y + h, x + w, y + h, _C["rail"], 1.5)
    ctx.line(x, y + 0.02, x + w, y + 0.02, _C["iron"], 0.8)
    n = max(3, int(w / 0.08))
    step = w / n
    for i in range(n + 1):
        ctx.line(x + i * step, y + 0.02, x + i * step, y + h, _C["iron"], 0.6)


def _bte_art_nouveau(ctx, x, y, w):
    _bte_classic(ctx, x, y, w)


def _bte_greek_key(ctx, x, y, w):
    _bte_geometric(ctx, x, y, w)


_BALCONETTE_DISPATCH = {
    BalconyStyle.CLASSIC_SCROLL: _bte_classic,
    BalconyStyle.GEOMETRIC: _bte_geometric,
    BalconyStyle.SIMPLE_BARS: _bte_simple,
    BalconyStyle.ART_NOUVEAU: _bte_art_nouveau,
    BalconyStyle.GREEK_KEY: _bte_greek_key,
}


# =====================================================================
# AWNING RENDERERS
# =====================================================================

def render_awning(ctx, style: AwningStyle, x: float, y: float, w: float):
    """Render an awning above commercial ground floor.

    *y* is the top of the glass opening.  Awnings extend downward from
    here, partially covering the glass — matching reference proportions.
    """
    if style == AwningStyle.NONE:
        return
    _AWNING_DISPATCH[style](ctx, x, y, w)


def _awning_flat_box(ctx, x, y, w):
    """Flat rectangular box awning — prominent, covers upper glass."""
    h = 0.70
    top_y = y  # top of awning at top of glass
    # Main box — extends downward from glass top
    ctx.rect(x - 0.04, top_y - h, w + 0.08, h, _C["awning_green"],
             stroke=_C["awning_green"], stroke_w=0.5)
    # Bottom trim
    ctx.rect(x - 0.04, top_y - h, w + 0.08, 0.04, _C["awning_green"], stroke_w=0.0)


def _awning_retractable(ctx, x, y, w):
    """Angled fabric canopy — tilts out from wall, gold coloured."""
    bar_y = y  # attached at glass top
    drop = 0.55
    front_y = bar_y - drop
    ctx.polygon([
        (x - 0.04, bar_y), (x + w + 0.04, bar_y),
        (x + w + 0.08, front_y), (x - 0.08, front_y),
    ], _C["awning_gold"], stroke=_C["stone_stroke"], stroke_w=0.5)
    # Valance at bottom edge
    ctx.rect(x - 0.08, front_y - 0.06, w + 0.16, 0.06,
             _C["awning_gold"], stroke_w=0.0)


def _awning_scalloped(ctx, x, y, w):
    """Navy flat bar with decorative scalloped valance."""
    bar_h = 0.10
    bar_y = y  # at glass top
    ctx.rect(x - 0.02, bar_y - bar_h, w + 0.04, bar_h,
             _C["awning_navy"], stroke_w=0.5)
    # Scallops hanging from bottom
    scallop_w = 0.25
    n = max(2, int(w / scallop_w))
    actual_w = w / n
    scallop_depth = 0.10
    for i in range(n):
        sx = x + i * actual_w
        pts = [
            (sx, bar_y - bar_h),
            (sx + actual_w, bar_y - bar_h),
            (sx + actual_w, bar_y - bar_h - scallop_depth * 0.3),
            (sx + actual_w * 0.5, bar_y - bar_h - scallop_depth),
            (sx, bar_y - bar_h - scallop_depth * 0.3),
        ]
        ctx.polygon(pts, _C["awning_navy"], stroke_w=0.0)


def _awning_striped(ctx, x, y, w):
    """Striped retractable awning — red and cream."""
    bar_y = y
    drop = 0.55
    front_y = bar_y - drop
    # Cream base
    ctx.polygon([
        (x - 0.04, bar_y), (x + w + 0.04, bar_y),
        (x + w + 0.08, front_y), (x - 0.08, front_y),
    ], _C["awning_cream"], stroke=_C["stone_stroke"], stroke_w=0.5)
    # Red stripes
    stripe_w = 0.15
    n_stripes = int(w / (stripe_w * 2)) + 1
    for i in range(n_stripes):
        sx = x + i * stripe_w * 2
        sw = min(stripe_w, x + w - sx)
        if sw > 0:
            ctx.rect(sx, front_y, sw, bar_y - front_y,
                     _C["awning_red"], stroke_w=0.0)
    # Valance
    ctx.rect(x - 0.08, front_y - 0.06, w + 0.16, 0.06,
             _C["awning_red"], stroke_w=0.0)


_AWNING_DISPATCH = {
    AwningStyle.FLAT_BOX: _awning_flat_box,
    AwningStyle.RETRACTABLE: _awning_retractable,
    AwningStyle.SCALLOPED: _awning_scalloped,
    AwningStyle.STRIPED: _awning_striped,
}
