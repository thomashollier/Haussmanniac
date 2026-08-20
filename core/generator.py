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
from .grammar import HaussmannGrammar, compute_gabarit
from .profile import RangeParam, get_profile, vary_profile
from .oriel import build_oriels
from .reglement import balcony_rule, compute_envelope, get_reglement, oriel_rule
from .roof import build_roof
from .types import (
    BalconyType,
    BayType,
    BuildingConfig,
    BuildingDecisions,
    BuildingNode,
    BuildingOverrides,
    CornerNode,
    CustomBayStyle,
    FloorNode,
    FloorType,
    GroundFloorNode,
    GroundFloorType,
    Orientation,
    PorteStyle,
    StylePreset,
    Transform,
)
from .elements import vary_element_palette
from .variation import Variation

# FloorType → FloorHeights attribute name
_FLOOR_TYPE_TO_ATTR: dict[FloorType, str] = {
    FloorType.GROUND: "ground",
    FloorType.ENTRESOL: "entresol",
    FloorType.NOBLE: "noble",
    FloorType.THIRD: "third",
    FloorType.FOURTH: "fourth",
    FloorType.FIFTH: "fifth",
}


def _derive_balcony_types(
    floor_nodes: list,
    era,
    prominence: dict[FloorType, BalconyType],
) -> dict[FloorType, BalconyType]:
    """Assign balcony treatments to floors under the 1823 ordinance.

    *floor_nodes* is the stacked facade, bottom-up.  *prominence* is the
    per-building roll from ``vary_balcony_types`` — its two values are read
    as "how prominent is the lower line" and "how prominent is the upper
    line", and are applied to whichever floors the rule makes eligible.

    Every floor type present gets an explicit entry, so the legal rule —
    not the profile's ``continuous_floors`` list — has the last word.
    """
    levels: list[float] = []
    types: list[FloorType] = []
    for node in floor_nodes:
        if isinstance(node, GroundFloorNode):
            levels.append(node.transform.position[1])
            types.append(FloorType.GROUND)
        elif isinstance(node, FloorNode):
            levels.append(node.y_offset)
            types.append(node.floor_type)

    rule = balcony_rule(levels, era)
    result: dict[FloorType, BalconyType] = {ft: BalconyType.NONE for ft in types}

    ranked = [prominence.get(FloorType.NOBLE, BalconyType.CONTINUOUS),
              prominence.get(FloorType.FIFTH, BalconyType.CONTINUOUS)]
    for k, idx in enumerate(rule.continuous):
        result[types[idx]] = ranked[min(k, len(ranked) - 1)]
    for idx in rule.individual:
        if result[types[idx]] == BalconyType.NONE:
            result[types[idx]] = BalconyType.BALCONETTE
    return result


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
    era = config.resolved_era()

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

        grammar = HaussmannGrammar(profile=profile, era=era)
    else:
        # Caller-supplied grammar: it still gets this run's era, and
        # HaussmannGrammar has already copied the profile so the sampled
        # values written below cannot leak back into a shared preset.
        grammar.reglement = get_reglement(era)

    # -- Resolve defaults from profile when not specified -------------------------
    lot_width = config.lot_width if config.lot_width is not None else grammar.profile.typical_lot_width.typ
    lot_depth = config.lot_depth if config.lot_depth is not None else grammar.profile.typical_lot_depth

    # Variation master — only used to derive isolated children
    variation = Variation(seed=config.seed, style=style)

    # Derive isolated RNG streams for each pipeline stage
    v_stacking = variation.derive_child_rng("stacking")
    v_layout = variation.derive_child_rng("layout")
    v_roof = variation.derive_child_rng("roof")
    v_front = variation.derive_child_rng("front")
    v_side_east = variation.derive_child_rng("side_east")
    v_side_west = variation.derive_child_rng("side_west")
    v_rear = variation.derive_child_rng("rear")
    v_roof_detail = variation.derive_child_rng("roof_detail")

    # -- Gabarit-driven floor count derivation ------------------------------------
    street_width = config.street_width if config.street_width is not None else 0.0
    if config.num_floors is not None:
        # Hard override — skip gabarit derivation entirely
        num_floors = config.num_floors
        has_entresol = config.has_entresol if config.has_entresol is not None else grammar.profile.has_entresol
        if not street_width:
            street_width = grammar.profile.typical_street_width.typ
    else:
        # Bottom-up stacking: gabarit budget → floor count + heights
        if config.street_width is not None:
            gabarit = compute_gabarit(config.street_width, era)
            street_range = None  # explicit street width — skip range pick
        else:
            gabarit = None
            street_range = grammar.profile.typical_street_width

        stacking = v_stacking.vary_floor_stacking(
            grammar, gabarit, street_range,
            has_entresol_override=config.has_entresol,
        )
        num_floors, has_entresol = stacking.num_floors, stacking.has_entresol
        if config.street_width is None:
            street_width = stacking.street_width
        # Write effective heights into grammar for downstream floor/facade code
        for ft, h in stacking.heights.items():
            attr = _FLOOR_TYPE_TO_ATTR[ft]
            old = getattr(grammar.profile.floors, attr)
            setattr(grammar.profile.floors, attr, RangeParam(h, old.variation, old.sigma))
    ovr = config.overrides or BuildingOverrides()

    # -- Gabarit envelope: the legal solid this frontage may occupy ------------
    # Street width fixes the cornice line; the decree in force fixes the
    # shape of the comble above it.  Everything the roof does follows from
    # this object rather than from free-floating random parameters.
    envelope = compute_envelope(
        street_width=street_width,
        era=era,
        parcel_depth=lot_depth,
        roof_fill=(config.roof_fill if config.roof_fill is not None
                   else grammar.profile.roof.roof_fill),
        # The comble holds servants' rooms; a building takes the storeys it
        # needs rather than every metre the decree would allow.
        max_ridge=(grammar.profile.roof.comble_storeys
                   * grammar.profile.floors.mansard.typ),
    )
    grammar.set_envelope(envelope)

    # -- Element palette (6 RNG calls, isolated stream) -------------------------
    v_elements = variation.derive_child_rng("elements")
    element_palette = vary_element_palette(v_elements.rng, config.style_preset)

    building = BuildingNode(
        lot_width=lot_width,
        lot_depth=lot_depth,
        num_floors=num_floors,
        style_preset=style,
        seed=config.seed,
        era=era,
        street_width=round(street_width, 3),
        element_palette=element_palette,
    )

    # -- 1. Floor stacking -----------------------------------------------------
    floor_nodes = build_floor_stack(
        num_floors=num_floors,
        facade_width=lot_width,
        style=style,
        variation=v_front,
        grammar=grammar,
        has_entresol=has_entresol,
        has_porte_cochere=config.has_porte_cochere,
    )

    # -- 2. Compute front facade bay layout once ---------------------------------
    front_bay_count = v_layout.vary_bay_count(lot_width, grammar)
    if ovr.bay_count is not None:
        front_bay_count = ovr.bay_count

    # Pick porte-cochère bay index before solver so it can size the door bay
    door_bay_idx = -1
    if config.has_porte_cochere and front_bay_count > 0:
        door_bay_idx = v_layout.pick_porte_cochere_bay(front_bay_count, grammar)
        if ovr.porte_cochere_bay is not None:
            door_bay_idx = ovr.porte_cochere_bay
        # Clamp to actual bay count (pick_porte_cochere_bay may exceed range)
        door_bay_idx = min(door_bay_idx, front_bay_count - 1)

    # Pick porte-cochère style (arched or flat)
    porte_style = v_layout.pick_porte_style(grammar) if config.has_porte_cochere else PorteStyle.ARCHED
    if ovr.porte_style is not None:
        porte_style = ovr.porte_style

    # -- Custom bay style (always consume RNG for stability) -------------------
    custom_bay_style = v_layout.vary_custom_bay_style(grammar)
    if ovr.custom_bay_style is not None:
        custom_bay_style = ovr.custom_bay_style

    # -- Custom bay side (always consume 1 RNG call) -------------------------
    custom_bay_side = v_layout.vary_custom_bay_side(door_bay_idx, front_bay_count)

    # -- Door bay width ratio (sample per-building, write into profile) --------
    door_ratio = v_layout.sample_range(grammar.profile.variation.door_bay_width_ratio)
    door_ratio = round(max(1.0, door_ratio), 3)  # clamp: never narrower than regular
    grammar.profile.bays.door_bay_width_ratio = door_ratio

    # -- Solve bay layout with custom_bay_side ---------------------------------
    front_bay_layout = grammar.solve_bay_layout(
        facade_width=lot_width,
        bay_count=front_bay_count,
        has_door=config.has_porte_cochere,
        door_bay_index=door_bay_idx,
        custom_bay_side=custom_bay_side,
    )
    front_bay_count = len(front_bay_layout)

    # Read actual door index from solver output (may have been clamped)
    if config.has_porte_cochere:
        door_bays = [b for b in front_bay_layout if b.bay_type == BayType.DOOR]
        door_bay_idx = door_bays[0].index if door_bays else min(door_bay_idx, front_bay_count - 1)

    # Apply has_custom_bays override
    has_custom = any(b.bay_type == BayType.CUSTOM for b in front_bay_layout)
    if ovr.has_custom_bays is not None:
        if ovr.has_custom_bays and not has_custom:
            # Force custom bays: re-solve with allow_custom_bays=True and
            # a lowered threshold so they always appear
            saved_threshold = grammar.profile.bays.custom_bay_threshold
            grammar.profile.bays.custom_bay_threshold = 0.0
            front_bay_layout = grammar.solve_bay_layout(
                facade_width=lot_width,
                bay_count=front_bay_count,
                has_door=config.has_porte_cochere,
                door_bay_index=door_bay_idx,
                allow_custom_bays=True,
                custom_bay_side=custom_bay_side,
            )
            grammar.profile.bays.custom_bay_threshold = saved_threshold
        elif not ovr.has_custom_bays and has_custom:
            # Suppress custom bays: re-solve without them
            front_bay_layout = grammar.solve_bay_layout(
                facade_width=lot_width,
                bay_count=front_bay_count,
                has_door=config.has_porte_cochere,
                door_bay_index=door_bay_idx,
                allow_custom_bays=False,
            )

    # Update bay count and door index after potential re-solve
    front_bay_count = len(front_bay_layout)
    if config.has_porte_cochere:
        door_bays = [b for b in front_bay_layout if b.bay_type == BayType.DOOR]
        if door_bays:
            door_bay_idx = door_bays[0].index

    # -- 3. Resolve ground floor type ------------------------------------------
    gf_type = GroundFloorType[config.ground_floor_type]
    if gf_type == GroundFloorType.AUTO:
        gf_type = v_layout.vary_ground_floor_type(config.has_porte_cochere, grammar)
    if ovr.ground_floor_type is not None:
        gf_type = ovr.ground_floor_type

    # -- 3b. Balcony decisions (always 2 RNG calls) ----------------------------
    # Where balconies may go is not a style choice: the ordinance of 1823
    # allows them only at 6 m or more above the pavement, and never more
    # than 0.80 m deep.  That rule is what puts the balcon filant on the
    # étage noble of a building with an entresol, and a storey higher on
    # one without.  The RNG still decides how prominent each line is.
    decisions = BuildingDecisions()
    decisions.balcony_types = _derive_balcony_types(
        floor_nodes, era, v_layout.vary_balcony_types(grammar)
    )

    # Element palette is on BuildingNode (generated earlier with isolated RNG)
    decisions.element_palette = element_palette

    # -- 3c. Roof decisions (isolated via v_roof) --------------------------------
    # The comble's height and angles come from the gabarit envelope, not
    # from free sampling: above the cornice the decree in force is what
    # decides the silhouette.  The RNG calls are still made — they keep the
    # stream stable and still choose whether a modest building bothers
    # building its comble out to the legal maximum.
    _, roof_has_dormers, _, _, _ = v_roof.vary_mansard(grammar)

    mansard_h = envelope.ridge_height
    if not roof_has_dormers:
        # The "short roof" branch: built well below the legal envelope,
        # too low to take dormers.
        mansard_h = round(envelope.ridge_height * 0.62, 3)
    lower_angle, upper_angle, break_ratio = envelope.mansard_angles()

    if ovr.mansard_height is not None:
        mansard_h = ovr.mansard_height
    if ovr.break_ratio is not None:
        break_ratio = ovr.break_ratio
    if ovr.lower_angle is not None:
        lower_angle = ovr.lower_angle
    if ovr.upper_angle is not None:
        upper_angle = ovr.upper_angle

    # Dormer placement: use original RNG has_dormers for conditional flow
    dormer_placement = v_roof.vary_dormer_placement(grammar) if roof_has_dormers else ""
    if ovr.dormer_placement is not None:
        dormer_placement = ovr.dormer_placement

    # Apply has_dormers override AFTER conditional RNG calls
    if ovr.has_dormers is not None:
        roof_has_dormers = ovr.has_dormers
        if roof_has_dormers and not dormer_placement:
            dormer_placement = ovr.dormer_placement or "BETWEEN_BAYS"

    # Dormer style + chimney count (isolated via v_roof)
    dormer_style = v_roof.vary_dormer_style(grammar, front_bay_count)
    if ovr.dormer_style is not None:
        dormer_style = ovr.dormer_style
    chimney_count = v_roof.vary_chimney_count(grammar, front_bay_count)

    # -- 4. Front facade -------------------------------------------------------
    front_facade = build_facade(
        orientation=Orientation.SOUTH,
        facade_width=lot_width,
        floor_nodes=floor_nodes,
        style=style,
        variation=v_front,
        grammar=grammar,
        has_porte_cochere=config.has_porte_cochere,
        bay_count=front_bay_count,
        bay_layout=front_bay_layout,
        door_bay_index=door_bay_idx,
        ground_floor_type=gf_type,
        porte_style=porte_style,
        custom_bay_style=custom_bay_style,
        decisions=decisions,
    )
    # -- 4b. Oriels (isolated stream — a late addition that must not disturb
    #        any decision an existing seed already made) --------------------
    v_oriel = variation.derive_child_rng("oriel")
    oriels = build_oriels(
        floor_nodes=floor_nodes,
        bay_layout=front_bay_layout,
        rule=oriel_rule(
            floor_levels=[n.transform.position[1] for n in floor_nodes],
            floor_names=[
                FloorType.GROUND.name if isinstance(n, GroundFloorNode) else n.floor_type.name
                for n in floor_nodes
            ],
            cornice_height=total_height(floor_nodes),
            era=era,
        ),
        variation=v_oriel,
        grammar=grammar,
        door_bay_index=door_bay_idx,
    )
    front_facade.children.extend(oriels)
    building.children.append(front_facade)

    # -- 5. Side facades (simplified — fewer bays, less ornament) --------------
    side_style = StylePreset.MODEST  # Sides are always simpler
    for orient, z_offset, v_side in [
        (Orientation.EAST, 0.0, v_side_east),
        (Orientation.WEST, lot_depth, v_side_west),
    ]:
        side_floors = build_floor_stack(
            num_floors=num_floors,
            facade_width=lot_depth,
            style=side_style,
            variation=v_side,
            grammar=grammar,
            has_entresol=has_entresol,
            has_porte_cochere=False,
        )
        side_facade = build_facade(
            orientation=orient,
            facade_width=lot_depth,
            floor_nodes=side_floors,
            style=side_style,
            variation=v_side,
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
        variation=v_rear,
        grammar=grammar,
        has_entresol=has_entresol,
        has_porte_cochere=False,
    )
    rear_facade = build_facade(
        orientation=Orientation.NORTH,
        facade_width=lot_width,
        floor_nodes=rear_floors,
        style=StylePreset.MODEST,
        variation=v_rear,
        grammar=grammar,
        has_porte_cochere=False,
    )
    rear_facade.transform = Transform(position=(0.0, 0.0, lot_depth))
    building.children.append(rear_facade)

    # -- 7. Roof ---------------------------------------------------------------
    cornice_height = total_height(floor_nodes)
    roof = build_roof(
        lot_width=lot_width,
        lot_depth=lot_depth,
        cornice_height=cornice_height,
        style=style,
        variation=v_roof_detail,
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
        dormer_style=dormer_style,
        chimney_count=chimney_count,
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
