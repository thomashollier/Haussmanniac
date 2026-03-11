"""Mansard roof generation — slopes, dormers, chimneys, and ridge.

Supports three mansard profiles:

- **STEEP**: Near-vertical lower slope (~80°). The lower face is almost a
  wall, providing maximum room for full-height dormers. Classic grand
  Haussmann on the boulevards.

- **BROKEN**: Very steep lower section (~70°) that breaks to a much flatter
  upper section (~20°) above the dormer heads. The most common Parisian
  mansard — dormers sit entirely within the steep lower zone.

- **SHALLOW**: Gentle continuous slope (~40°) without dormers. Used on
  rear facades and modest buildings.

All geometry is described as IR nodes — no actual meshes are created here.
"""

from __future__ import annotations

import math
from dataclasses import replace as _dc_replace

from .grammar import BaySpec, HaussmannGrammar
from .types import (
    ChimneyNode,
    DormerNode,
    DormerStyle,
    IRNode,
    MansardSlopeNode,
    MansardType,
    RoofNode,
    StylePreset,
    Transform,
)
from .variation import Variation


def build_roof(
    lot_width: float,
    lot_depth: float,
    cornice_height: float,
    style: StylePreset,
    variation: Variation,
    grammar: HaussmannGrammar | None = None,
    bay_count: int | None = None,
    bay_layout: list[BaySpec] | None = None,
    door_bay_index: int = -1,
    mansard_height: float | None = None,
    has_dormers: bool = True,
    break_ratio: float = 0.0,
    lower_angle_deg: float = 0.0,
    upper_angle_deg: float = 0.0,
    dormer_placement: str = "",
    dormer_style_override: DormerStyle | None = None,
) -> RoofNode:
    """Assemble the complete mansard roof from building parameters.

    The roof sits at *cornice_height* and contains:
    - Four mansard slope nodes (front, back, left, right)
    - Dormer nodes on the front slope (unless SHALLOW or *has_dormers* is False)
    - Chimney stacks distributed along the ridge

    When *bay_count* is provided, it is used directly (skipping
    ``vary_bay_count``).  When *bay_layout* is provided, it is passed
    directly to ``_build_dormers`` so dormers align exactly with the
    facade bays (same count, same x-positions, same wide-door layout).

    *mansard_height* overrides the roof spec height when provided (used
    by the variation system for short/tall modest roofs).
    *has_dormers* gates whether dormers are placed at all.

    Returns a fully-populated ``RoofNode``.
    """
    if grammar is None:
        grammar = HaussmannGrammar()

    if bay_count is None:
        bay_count = variation.vary_bay_count(lot_width, grammar)
    roof_spec = grammar.get_roof_spec(bay_count, style, is_front=True)
    rear_spec = grammar.get_roof_spec(bay_count, style, is_front=False)

    # Override mansard parameters from variation (height, break ratio, angle)
    if mansard_height is not None:
        roof_spec = _replace_mansard_params(roof_spec, mansard_height,
                                            break_ratio, lower_angle_deg, upper_angle_deg)
        rear_spec = _replace_mansard_params(rear_spec, mansard_height,
                                            break_ratio, lower_angle_deg, upper_angle_deg)

    roof = RoofNode(
        transform=Transform(position=(0.0, cornice_height, 0.0)),
        mansard_type=roof_spec.mansard_type,
        mansard_lower_angle=math.radians(roof_spec.mansard_lower_angle_deg),
        mansard_upper_angle=math.radians(roof_spec.mansard_upper_angle_deg),
    )

    # -- Mansard slopes (four sides) -------------------------------------------
    slopes = _build_slopes(lot_width, lot_depth, roof_spec, rear_spec)
    roof.children.extend(slopes)

    # -- Dormers on front slope ------------------------------------------------
    if has_dormers and roof_spec.dormer_every_n_bays > 0:
        dormers = _build_dormers(
            lot_width, style, variation, grammar, bay_count, roof_spec,
            bay_layout=bay_layout,
            dormer_placement=dormer_placement,
            dormer_style_override=dormer_style_override,
        )
        roof.children.extend(dormers)

    # -- Chimneys along the ridge ----------------------------------------------
    chimneys = _build_chimneys(
        lot_width, lot_depth, variation, grammar, bay_count, roof_spec,
        door_bay_index=door_bay_index,
    )
    roof.children.extend(chimneys)

    # -- Ridge chimneys between bays -------------------------------------------
    if bay_layout and len(bay_layout) >= 2:
        ridge_chimneys = _build_ridge_chimneys(
            bay_layout, variation, roof_spec, grammar=grammar,
            door_bay_index=door_bay_index,
        )
        roof.children.extend(ridge_chimneys)

    return roof


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _replace_mansard_params(spec, height: float,
                            break_ratio: float = 0.0,
                            lower_angle_deg: float = 0.0,
                            upper_angle_deg: float = 0.0):
    """Return a copy of *spec* with mansard parameters replaced.

    *break_ratio* (0.70–1.0) overrides break_pct.
    *lower_angle_deg* (70–85) overrides the steep section angle.
    *upper_angle_deg* (3–45) overrides the shallow section angle.
    When any is zero, the spec default is kept.
    """
    pct = break_ratio if break_ratio > 0 else spec.break_pct
    lower = lower_angle_deg if lower_angle_deg > 0 else spec.mansard_lower_angle_deg
    upper = upper_angle_deg if upper_angle_deg > 0 else spec.mansard_upper_angle_deg
    return _dc_replace(spec, mansard_height=height, break_pct=pct,
                       mansard_lower_angle_deg=lower, mansard_upper_angle_deg=upper)


# ---------------------------------------------------------------------------
# Slope geometry
# ---------------------------------------------------------------------------

def _build_slopes(
    lot_width: float,
    lot_depth: float,
    front_spec,
    rear_spec,
) -> list[MansardSlopeNode]:
    """Create four mansard slope nodes.

    Front slope uses the style-appropriate mansard type (STEEP/BROKEN/SHALLOW).
    Rear and side slopes are always SHALLOW.
    """
    def _make_slope(spec, position, rotation=(0.0, 0.0, 0.0)) -> MansardSlopeNode:
        return MansardSlopeNode(
            transform=Transform(position=position, rotation=rotation),
            mansard_type=spec.mansard_type,
            lower_angle=math.radians(spec.mansard_lower_angle_deg),
            upper_angle=math.radians(spec.mansard_upper_angle_deg),
            break_pct=spec.break_pct,
            height=spec.mansard_height,
            material="zinc",
        )

    return [
        # Front (street-facing, style-driven)
        _make_slope(front_spec, (0.0, 0.0, 0.0)),
        # Rear (always shallow)
        _make_slope(rear_spec, (0.0, 0.0, lot_depth), (0.0, math.pi, 0.0)),
        # Left side (always shallow)
        _make_slope(rear_spec, (0.0, 0.0, 0.0), (0.0, math.pi / 2, 0.0)),
        # Right side (always shallow)
        _make_slope(rear_spec, (lot_width, 0.0, 0.0), (0.0, -math.pi / 2, 0.0)),
    ]


# ---------------------------------------------------------------------------
# Dormer placement
# ---------------------------------------------------------------------------

def _build_dormers(
    lot_width: float,
    style: StylePreset,
    variation: Variation,
    grammar: HaussmannGrammar,
    bay_count: int,
    roof_spec,
    bay_layout: list[BaySpec] | None = None,
    dormer_placement: str = "",
    dormer_style_override: DormerStyle | None = None,
) -> list[DormerNode]:
    """Place dormers on the front mansard slope.

    Four placement rules (selected by *dormer_placement*):

    - ``EVERY_BAY``:    one dormer centered above each bay
    - ``EVERY_OTHER``:  one dormer above every other bay
    - ``BETWEEN_BAYS``: one dormer at each pier gap between adjacent bays
    - ``CENTER_ONLY``:  one dormer above the center bay only

    When *dormer_placement* is empty, falls back to the roof spec's
    ``dormer_every_n_bays`` (legacy behaviour for non-modest styles).

    Dormers sit within the steep lower zone of the mansard:
    - STEEP:  Dormers can be tall, positioned at ~20% up the slope.
    - BROKEN: Dormers fit below the break point (break_pct * height).
    - SHALLOW: No dormers (caller should not invoke this).
    """
    if bay_layout is None:
        bay_layout = grammar.get_bay_layout(lot_width, style)
    dormer_style = variation.vary_dormer_style(grammar, bay_count)
    if dormer_style_override is not None:
        dormer_style = dormer_style_override

    mansard_type = roof_spec.mansard_type
    lower_angle_rad = math.radians(roof_spec.mansard_lower_angle_deg)

    # Dormer vertical position within the steep zone
    if mansard_type == MansardType.STEEP:
        dormer_y = roof_spec.mansard_height * 0.15
        max_dormer_h = roof_spec.mansard_height * 0.6
    elif mansard_type == MansardType.BROKEN:
        break_h = roof_spec.mansard_height * roof_spec.break_pct
        dormer_y = break_h * 0.10
        max_dormer_h = break_h * 0.75
    else:
        return []  # No dormers on shallow

    dormer_h = min(grammar.profile.roof.dormer_max_height, max_dormer_h)

    # Horizontal inset at dormer base: how far in the slope edge is at dormer_y
    inset_at_dormer = dormer_y / math.tan(lower_angle_rad) if lower_angle_rad else 0.0

    # Dormer width matches the window width on upper floors
    bp = grammar.profile.bays
    wp = grammar.profile.windows
    std_bay_window_w = bp.bay_width[1] * (1 - bp.pier_ratio)
    win_w = std_bay_window_w * wp.width_ratio

    # Compute dormer x-positions based on placement rule
    x_positions: list[float] = []
    if dormer_placement == "EVERY_BAY":
        x_positions = [b.x_offset + b.width / 2 for b in bay_layout]
    elif dormer_placement == "EVERY_OTHER":
        x_positions = [b.x_offset + b.width / 2
                       for i, b in enumerate(bay_layout) if i % 2 == 0]
    elif dormer_placement == "BETWEEN_BAYS":
        for i in range(len(bay_layout) - 1):
            left = bay_layout[i]
            right = bay_layout[i + 1]
            x_positions.append((left.x_offset + left.width + right.x_offset) / 2)
    elif dormer_placement == "CENTER_ONLY":
        mid = len(bay_layout) // 2
        x_positions = [bay_layout[mid].x_offset + bay_layout[mid].width / 2]
    else:
        # Legacy: use dormer_every_n_bays from roof spec
        x_positions = [b.x_offset + b.width / 2
                       for i, b in enumerate(bay_layout)
                       if i % roof_spec.dormer_every_n_bays == 0]

    left_edge = inset_at_dormer
    right_edge = lot_width - inset_at_dormer

    dormers: list[DormerNode] = []
    for dormer_x in x_positions:
        # Skip if dormer would be outside the slope surface
        if (dormer_x - win_w / 2) < left_edge - 0.05:
            continue
        if (dormer_x + win_w / 2) > right_edge + 0.05:
            continue

        dormer = DormerNode(
            transform=Transform(position=(dormer_x, dormer_y, 0.0)),
            width=round(win_w, 3),
            height=round(dormer_h, 3),
            style=dormer_style,
        )
        dormers.append(dormer)

    return dormers


# ---------------------------------------------------------------------------
# Chimney placement
# ---------------------------------------------------------------------------

def _build_chimneys(
    lot_width: float,
    lot_depth: float,
    variation: Variation,
    grammar: HaussmannGrammar,
    bay_count: int,
    roof_spec,
    door_bay_index: int = -1,
) -> list[ChimneyNode]:
    """Place chimney stacks on party walls (left and right lot edges).

    Real Haussmann chimneys sit on the *murs mitoyens* (party walls shared
    with adjacent buildings).  Each stack contains multiple flues grouped
    together.  The stacks are placed at both edges of the lot, slightly
    inset, and staggered in depth (z) so they don't line up monotonously.

    When the door is on a side bay, chimneys cluster on the opposite wall
    (typical of modest Parisian buildings).
    """
    total_chimney_count = variation.vary_chimney_count(grammar, bay_count)
    base_height = roof_spec.chimney_height

    chimneys: list[ChimneyNode] = []
    if total_chimney_count <= 0:
        return chimneys

    # Split total between edge (party-wall) and ridge chimneys
    ratio = grammar.profile.roof.ridge_to_edge_ratio
    edge_count = max(1, round(total_chimney_count / (1 + ratio)))
    # Ridge chimneys are handled by _build_ridge_chimneys; edge_count here

    # Split edge chimneys between left and right party walls.
    # If door is on a side, put all chimneys on the opposite wall.
    if door_bay_index == 0:
        # Door on left → chimneys on right
        left_count = 0
        right_count = edge_count
    elif door_bay_index >= 0 and door_bay_index == bay_count - 1:
        # Door on right → chimneys on left
        left_count = edge_count
        right_count = 0
    else:
        # Center door or no door → split between both walls
        right_count = edge_count // 2
        left_count = edge_count - right_count

    # Chimney dimensions — smaller for modest buildings
    is_modest = (ratio > 1.0)  # modest has ridge_to_edge_ratio=2.0
    stack_w = 0.6 if is_modest else 0.8
    stack_depth = 0.4 if is_modest else 0.5

    # Chimneys start at the base of the mansard (y=0 relative to roof node)
    # and must clear the top.  Total height = mansard + clearance above.
    mansard_h = roof_spec.mansard_height

    # Depth (z) positions: stagger front-to-back within each stack group
    z_start = lot_depth * 0.25
    z_end = lot_depth * 0.65

    def _place_stack(count: int, x: float) -> None:
        if count <= 0:
            return
        z_spacing = (z_end - z_start) / max(count, 1)
        for j in range(count):
            z = z_start + z_spacing * (j + 0.5)
            # 33% shorter clearance above mansard
            clearance = variation.uniform(base_height * 0.60, base_height * 0.77)
            h = mansard_h + clearance
            chimneys.append(ChimneyNode(
                transform=Transform(
                    position=(x, 0.0, z),
                ),
                width=round(stack_w + variation.uniform(-0.05, 0.05), 3),
                depth=round(stack_depth + variation.uniform(-0.05, 0.05), 3),
                height=round(h, 3),
                material="stone",
                has_pipe=True,
            ))

    # Left party wall — outer edge flush with facade wall (x=0)
    _place_stack(left_count, stack_w / 2)
    # Right party wall — outer edge flush with facade wall (x=lot_width)
    _place_stack(right_count, lot_width - stack_w / 2)

    return chimneys


def _build_ridge_chimneys(
    bay_layout: list[BaySpec],
    variation: Variation,
    roof_spec,
    grammar: HaussmannGrammar | None = None,
    door_bay_index: int = -1,
) -> list[ChimneyNode]:
    """Place ridge chimneys between bays, straddling the mansard top.

    These smaller chimneys sit on the ridge line at pier positions
    (between adjacent bay windows).  Each has a thin flue pipe on top.
    Target density: ~3 chimneys per 7 bays, evenly distributed across
    the available pier gaps.

    When *door_bay_index* indicates a side door (edge chimneys cluster
    on the opposite wall), ridge chimneys prefer the door side to
    balance the composition.
    """
    n_bays = len(bay_layout)
    if n_bays < 2:
        return []

    mansard_h = roof_spec.mansard_height
    chimneys: list[ChimneyNode] = []

    # Determine ridge chimney count from bay density (~3 per 7 bays)
    ratio = grammar.profile.roof.ridge_to_edge_ratio if grammar else 1.0
    is_modest = (ratio > 1.0)
    n_gaps = n_bays - 1
    target_count = max(1, round(n_bays * 3 / 7))
    target_count = min(target_count, n_gaps)  # can't exceed gap count

    # Choose gap indices: prefer opposite side from edge chimneys
    # (edge chimneys cluster opposite the door, so ridge goes near the door)
    if target_count == 1 and n_gaps >= 2:
        if door_bay_index == 0:
            # Door on left → edge chimneys on right → ridge on left (gap 0)
            gap_indices = [0]
        elif door_bay_index >= 0 and door_bay_index >= n_bays - 1:
            # Door on right → edge chimneys on left → ridge on right (last gap)
            gap_indices = [n_gaps - 1]
        else:
            # Center door → distribute evenly
            gap_indices = [n_gaps // 2]
    else:
        # Multiple ridge chimneys: distribute evenly
        step = n_gaps / target_count
        gap_indices = [min(int(k * step + step / 2), n_gaps - 1) for k in range(target_count)]

    # Scale dimensions for modest buildings
    base_stack_w = 0.45 if is_modest else 0.55
    base_stack_depth = 0.35 if is_modest else 0.45
    base_stack_h = 0.5 if is_modest else 0.6

    for i in gap_indices:
        left_bay = bay_layout[i]
        right_bay = bay_layout[i + 1]
        pier_x = (left_bay.x_offset + left_bay.width + right_bay.x_offset) / 2

        stack_w = base_stack_w + variation.uniform(-0.03, 0.03)
        stack_h = base_stack_h + variation.uniform(-0.05, 0.10)

        chimneys.append(ChimneyNode(
            transform=Transform(position=(pier_x, mansard_h, 0.0)),
            width=round(stack_w, 3),
            depth=base_stack_depth,
            height=round(stack_h, 3),
            material="stone",
            is_ridge=True,
            has_pipe=True,
        ))

    return chimneys
