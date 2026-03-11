"""Top-level building generation pipeline.

Accepts a ``BuildingConfig`` and orchestrates:
  1. Variation system initialisation (seeded RNG)
  2. Floor stacking (vertical zoning)
  3. Facade composition (bay layout, windows, ornament)
  4. Roof assembly (mansard slopes, dormers, chimneys)

Returns a complete ``BuildingNode`` IR tree.
"""

from __future__ import annotations

from .facade import build_facade
from .floor import build_floor_stack, total_height
from .grammar import HaussmannGrammar
from .profile import get_profile, vary_profile
from .roof import build_roof
from .types import (
    BayType,
    BuildingConfig,
    BuildingNode,
    BuildingOverrides,
    CornerNode,
    GroundFloorType,
    Orientation,
    PorteStyle,
    StylePreset,
    Transform,
)
from .variation import Variation


def generate_building(
    config: BuildingConfig,
    grammar: HaussmannGrammar | None = None,
) -> BuildingNode:
    """Generate a complete Haussmann building IR tree from *config*.

    This is the main entry point for the generative core.  The returned
    ``BuildingNode`` contains fully-populated facades, roof, and optional
    corner chamfers — ready to be consumed by a backend adapter.
    """
    style = StylePreset[config.style_preset]

    # -- Resolve profile -------------------------------------------------------
    if grammar is None:
        if config.profile_name:
            profile = get_profile(config.profile_name)
        elif style == StylePreset.BOULEVARD:
            profile = get_profile("grand_boulevard")
        elif style == StylePreset.MODEST:
            profile = get_profile("modest")
        else:
            profile = get_profile("residential")

        if config.profile_variation > 0:
            profile = vary_profile(profile, config.seed, config.profile_variation)

        grammar = HaussmannGrammar(profile=profile)

    # -- Resolve defaults from profile when not specified -------------------------
    lot_width = config.lot_width if config.lot_width is not None else grammar.profile.typical_lot_width[1]
    lot_depth = config.lot_depth if config.lot_depth is not None else grammar.profile.typical_lot_depth
    num_floors = config.num_floors if config.num_floors is not None else grammar.profile.typical_num_floors
    has_entresol = config.has_entresol if config.has_entresol is not None else grammar.profile.has_entresol

    variation = Variation(seed=config.seed, style=style)
    ovr = config.overrides or BuildingOverrides()

    building = BuildingNode(
        lot_width=lot_width,
        lot_depth=lot_depth,
        num_floors=num_floors,
        style_preset=style,
        seed=config.seed,
    )

    # -- 1. Floor stacking -----------------------------------------------------
    floor_nodes = build_floor_stack(
        num_floors=num_floors,
        facade_width=lot_width,
        style=style,
        variation=variation,
        grammar=grammar,
        has_entresol=has_entresol,
        has_porte_cochere=config.has_porte_cochere,
    )

    # -- 2. Compute front facade bay layout once ---------------------------------
    front_bay_count = variation.vary_bay_count(lot_width, grammar)
    if ovr.bay_count is not None:
        front_bay_count = ovr.bay_count

    # Pick porte-cochère bay index before solver so it can size the door bay
    door_bay_idx = -1
    if config.has_porte_cochere and front_bay_count > 0:
        door_bay_idx = variation.pick_porte_cochere_bay(front_bay_count)
        if ovr.porte_cochere_bay is not None:
            door_bay_idx = ovr.porte_cochere_bay
        # Clamp to actual bay count (pick_porte_cochere_bay may exceed range)
        door_bay_idx = min(door_bay_idx, front_bay_count - 1)

    front_bay_layout = grammar.solve_bay_layout(
        facade_width=lot_width,
        bay_count=front_bay_count,
        has_door=config.has_porte_cochere,
        door_bay_index=door_bay_idx,
    )
    front_bay_count = len(front_bay_layout)

    # Read actual door index from solver output (may have been clamped)
    if config.has_porte_cochere:
        door_bays = [b for b in front_bay_layout if b.bay_type == BayType.DOOR]
        door_bay_idx = door_bays[0].index if door_bays else min(door_bay_idx, front_bay_count - 1)

    # Pick porte-cochère style (arched or flat)
    porte_style = variation.pick_porte_style() if config.has_porte_cochere else PorteStyle.ARCHED
    if ovr.porte_style is not None:
        porte_style = ovr.porte_style

    # -- 3. Resolve ground floor type ------------------------------------------
    gf_type = GroundFloorType[config.ground_floor_type]
    if gf_type == GroundFloorType.AUTO:
        gf_type = variation.vary_ground_floor_type(config.has_porte_cochere)
    if ovr.ground_floor_type is not None:
        gf_type = ovr.ground_floor_type

    # -- 4. Front facade -------------------------------------------------------
    front_facade = build_facade(
        orientation=Orientation.SOUTH,
        facade_width=lot_width,
        floor_nodes=floor_nodes,
        style=style,
        variation=variation,
        grammar=grammar,
        has_porte_cochere=config.has_porte_cochere,
        bay_count=front_bay_count,
        bay_layout=front_bay_layout,
        door_bay_index=door_bay_idx,
        ground_floor_type=gf_type,
        porte_style=porte_style,
    )
    building.children.append(front_facade)

    # -- 5. Side facades (simplified — fewer bays, less ornament) --------------
    side_style = StylePreset.MODEST  # Sides are always simpler
    for orient, z_offset in [
        (Orientation.EAST, 0.0),
        (Orientation.WEST, lot_depth),
    ]:
        side_floors = build_floor_stack(
            num_floors=num_floors,
            facade_width=lot_depth,
            style=side_style,
            variation=variation,
            grammar=grammar,
            has_entresol=has_entresol,
            has_porte_cochere=False,
        )
        side_facade = build_facade(
            orientation=orient,
            facade_width=lot_depth,
            floor_nodes=side_floors,
            style=side_style,
            variation=variation,
            grammar=grammar,
            has_porte_cochere=False,
        )
        # Position at the correct z offset
        side_facade.transform = Transform(position=(0.0, 0.0, z_offset))
        building.children.append(side_facade)

    # -- 6. Rear facade (minimal) ----------------------------------------------
    rear_floors = build_floor_stack(
        num_floors=num_floors,
        facade_width=lot_width,
        style=StylePreset.MODEST,
        variation=variation,
        grammar=grammar,
        has_entresol=has_entresol,
        has_porte_cochere=False,
    )
    rear_facade = build_facade(
        orientation=Orientation.NORTH,
        facade_width=lot_width,
        floor_nodes=rear_floors,
        style=StylePreset.MODEST,
        variation=variation,
        grammar=grammar,
        has_porte_cochere=False,
    )
    rear_facade.transform = Transform(position=(0.0, 0.0, lot_depth))
    building.children.append(rear_facade)

    # -- 7. Roof ---------------------------------------------------------------
    cornice_height = total_height(floor_nodes)
    mansard_h, roof_has_dormers, break_ratio, lower_angle, upper_angle = variation.vary_mansard(grammar)
    if ovr.mansard_height is not None:
        mansard_h = ovr.mansard_height
    if ovr.break_ratio is not None:
        break_ratio = ovr.break_ratio
    if ovr.lower_angle is not None:
        lower_angle = ovr.lower_angle
    if ovr.upper_angle is not None:
        upper_angle = ovr.upper_angle

    # Dormer placement: use original RNG has_dormers for conditional flow
    dormer_placement = variation.vary_dormer_placement() if roof_has_dormers else ""
    if ovr.dormer_placement is not None:
        dormer_placement = ovr.dormer_placement

    # Apply has_dormers override AFTER conditional RNG calls
    if ovr.has_dormers is not None:
        roof_has_dormers = ovr.has_dormers
        if roof_has_dormers and not dormer_placement:
            dormer_placement = ovr.dormer_placement or "BETWEEN_BAYS"

    roof = build_roof(
        lot_width=lot_width,
        lot_depth=lot_depth,
        cornice_height=cornice_height,
        style=style,
        variation=variation,
        grammar=grammar,
        bay_count=front_bay_count,
        bay_layout=front_bay_layout,
        door_bay_index=door_bay_idx,
        mansard_height=mansard_h,
        has_dormers=roof_has_dormers,
        break_ratio=break_ratio,
        lower_angle_deg=lower_angle,
        upper_angle_deg=upper_angle,
        dormer_placement=dormer_placement,
        dormer_style_override=ovr.dormer_style,
    )
    building.children.append(roof)

    # -- 8. Corner chamfers (optional) -----------------------------------------
    if config.corner_chamfer:
        chamfer_w = grammar.get_chamfer_width()
        corner = CornerNode(
            transform=Transform(position=(0.0, 0.0, 0.0)),
            chamfer_width=chamfer_w,
        )
        building.children.append(corner)

    return building
