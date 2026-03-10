"""Facade composition — distribute bays, assign windows, balconies, ornament.

Given a facade width, floor stack, and grammar, this module populates each
FloorNode / GroundFloorNode with BayNodes containing the appropriate
WindowNode, BalconyNode, PilasterNode, and OrnamentNode children.
"""

from __future__ import annotations

import math

from .grammar import BaySpec, HaussmannGrammar
from .ground_floor import build_ground_floor
from .types import (
    BalconyNode,
    BayNode,
    BayType,
    CorniceNode,
    FacadeNode,
    FloorNode,
    FloorType,
    GroundFloorNode,
    GroundFloorType,
    IRNode,
    Orientation,
    OrnamentLevel,
    OrnamentNode,
    PedimentStyle,
    PilasterNode,
    PorteStyle,
    StringCourseNode,
    StylePreset,
    Transform,
    WindowNode,
)
from .variation import Variation


def build_facade(
    orientation: Orientation,
    facade_width: float,
    floor_nodes: list[IRNode],
    style: StylePreset,
    variation: Variation,
    grammar: HaussmannGrammar | None = None,
    has_porte_cochere: bool = True,
    bay_count: int | None = None,
    bay_layout: list[BaySpec] | None = None,
    door_bay_index: int = -1,
    ground_floor_type: GroundFloorType = GroundFloorType.COMMERCIAL,
    porte_style: PorteStyle = PorteStyle.ARCHED,
) -> FacadeNode:
    """Compose a complete facade from floor nodes and bay layout.

    Walks each floor node, distributes bays across the facade width, and
    populates every bay with windows, balconies, pilasters, and ornament
    appropriate to the floor type and style preset.

    When *bay_layout* is provided, it is used directly (skipping all
    internal layout computation).  When only *bay_count* is provided,
    the layout is computed here.

    Returns a fully-populated FacadeNode.
    """
    if grammar is None:
        grammar = HaussmannGrammar()

    if bay_layout is not None:
        # Pre-computed layout from generator — use as-is
        door_bay_idx = door_bay_index
    else:
        # Legacy path: compute layout internally
        if bay_count is None:
            bay_count = variation.vary_bay_count(facade_width, grammar)

        door_bay_idx = -1
        if has_porte_cochere and bay_count > 0:
            door_bay_idx = variation.pick_porte_cochere_bay(bay_count)

        bay_layout = grammar.solve_bay_layout(
            facade_width=facade_width,
            bay_count=bay_count,
            has_door=(has_porte_cochere and door_bay_idx >= 0),
            door_bay_index=door_bay_idx,
            rng=variation.rng,
        )

    facade = FacadeNode(
        orientation=orientation,
        width=facade_width,
    )

    for floor_node in floor_nodes:
        if isinstance(floor_node, GroundFloorNode):
            build_ground_floor(
                floor_node, bay_layout, facade_width, style, variation, grammar,
                has_porte_cochere, door_bay_index=door_bay_idx,
                ground_floor_type=ground_floor_type,
                porte_style=porte_style,
            )
        elif isinstance(floor_node, FloorNode):
            _populate_upper_floor(
                floor_node, bay_layout, facade_width, style, variation, grammar,
            )
        facade.children.append(floor_node)

    # Roofline cornice at the top of the facade
    top_y = 0.0
    for fn in floor_nodes:
        if isinstance(fn, (FloorNode, GroundFloorNode)):
            top_y += fn.height

    roofline_cornice = CorniceNode(
        transform=Transform(position=(0.0, top_y, 0.0)),
        width=facade_width,
        profile_id="roofline",
        projection=grammar.get_cornice_projection(is_roofline=True),
        has_modillions=grammar.has_roofline_modillions(style),
        has_dentils=grammar.has_roofline_dentils(style),
    )
    facade.children.append(roofline_cornice)

    return facade


# ---------------------------------------------------------------------------
# Upper floors
# ---------------------------------------------------------------------------

def _populate_upper_floor(
    node: FloorNode,
    bay_layout: list,
    facade_width: float,
    style: StylePreset,
    variation: Variation,
    grammar: HaussmannGrammar,
) -> None:
    """Fill an upper-floor node with window bays, balconies, and ornament."""
    ft = node.floor_type
    ornament = node.ornament_level
    has_balcony = grammar.has_continuous_balcony(ft)
    has_balconette = grammar.has_balconette(ft)

    # Continuous balcony spans the full facade
    if has_balcony:
        railing_pattern = variation.vary_railing_pattern(ft)
        balcony = BalconyNode(
            transform=Transform(position=(0.0, 0.0, 0.0)),
            width=facade_width,
            depth=grammar.profile.balconies.balcony_depth,
            is_continuous=True,
            railing_pattern=railing_pattern,
            railing_height=grammar.get_railing_height(),
        )
        node.children.append(balcony)

    bay_count = len(bay_layout)
    center_idx = bay_count // 2

    # Standard bay window width — used for window sizing on all bays so that
    # windows above a wider door bay stay the same size as other windows.
    bp = grammar.profile.bays
    std_bay_window_w = bp.bay_width[1] * (1 - bp.pier_ratio)

    for bay_spec in bay_layout:
        bay = BayNode(
            transform=Transform(position=(bay_spec.x_offset, 0.0, 0.0)),
            width=bay_spec.width,
            x_offset=bay_spec.x_offset,
            bay_type=BayType.WINDOW,
        )

        # Window — use standard bay window width so door bays get normal windows
        win_spec = grammar.get_window_spec(ft, ornament, std_bay_window_w, node.height)
        surround = variation.vary_surround(ft, grammar)

        pediment = PedimentStyle.NONE

        # Noble floor with continuous balcony: windows touch the balcony floor
        if ft == FloorType.NOBLE and has_balcony and grammar.profile.balconies.noble_sill_at_floor:
            sill_height = 0.0
        else:
            sill_height = (node.height - win_spec.height) * grammar.profile.windows.sill_position_ratio
        window = WindowNode(
            transform=Transform(position=(0.0, sill_height, 0.0)),
            width=win_spec.width,
            height=win_spec.height,
            surround_style=surround,
            pediment=pediment,
            has_keystone=win_spec.has_keystone,
        )
        bay.children.append(window)

        # Individual balconette (not on continuous-balcony floors)
        if has_balconette and not has_balcony:
            balconette = BalconyNode(
                transform=Transform(position=(0.0, sill_height, 0.0)),
                width=bay_spec.width,
                depth=grammar.profile.balconies.balconette_depth,
                is_continuous=False,
                railing_pattern=variation.vary_railing_pattern(ft),
                railing_height=grammar.get_railing_height(),
            )
            bay.children.append(balconette)

        # Pilasters on rich floors
        if ornament == OrnamentLevel.RICH and ft != FloorType.GROUND:
            op = grammar.profile.ornament
            for side in (-1, 1):
                x_off = side * (bay_spec.width / 2 + op.pilaster_offset)
                pilaster = PilasterNode(
                    transform=Transform(position=(x_off, 0.0, 0.0)),
                    width=op.pilaster_width,
                    depth=op.pilaster_depth,
                    height=node.height,
                    has_capital=(ft == FloorType.NOBLE),
                )
                bay.children.append(pilaster)

        # Pediment ornament piece (if pediment is present)
        if pediment != PedimentStyle.NONE:
            ornament_node = OrnamentNode(
                transform=Transform(
                    position=(0.0, sill_height + win_spec.height, 0.0),
                ),
                ornament_id=f"pediment_{pediment.name.lower()}",
                ornament_level=ornament,
            )
            bay.children.append(ornament_node)

        node.children.append(bay)

    # Inter-floor string course at the top of this floor
    string_course = StringCourseNode(
        transform=Transform(position=(0.0, node.height, 0.0)),
        width=facade_width,
    )
    node.children.append(string_course)
