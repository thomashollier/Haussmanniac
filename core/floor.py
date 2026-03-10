"""Floor stacking — build a vertical sequence of FloorNodes for a facade.

Given a building configuration and grammar, produces FloorNode (and
GroundFloorNode) instances with correct heights, y-offsets, ornament levels,
and local transforms.  The resulting list is ordered bottom-to-top.
"""

from __future__ import annotations

from .grammar import HaussmannGrammar
from .types import (
    FloorNode,
    FloorType,
    GroundFloorNode,
    IRNode,
    StylePreset,
    Transform,
)
from .variation import Variation


def build_floor_stack(
    num_floors: int,
    facade_width: float,
    style: StylePreset,
    variation: Variation,
    grammar: HaussmannGrammar | None = None,
    has_entresol: bool = True,
    has_porte_cochere: bool = True,
) -> list[IRNode]:
    """Produce the vertical stack of floor nodes for one facade.

    Returns a list of IRNode (FloorNode or GroundFloorNode) ordered from
    ground level upward.  Each node's transform.position has the correct
    y-offset so the floors stack without gaps.

    Floor heights use the exact typical values from the grammar —
    ground 3.8, entresol 2.3, noble 3.2, 3rd 3.0, 4th 2.8, 5th 2.5 m.
    The mansard sits above the cornice and is excluded from this list.
    """
    if grammar is None:
        grammar = HaussmannGrammar()

    floor_types = grammar.floor_sequence(num_floors, has_entresol)

    # Remove MANSARD — roof is separate (sits above the cornice)
    if floor_types and floor_types[-1] == FloorType.MANSARD:
        floor_types = floor_types[:-1]

    gf_spec = grammar.get_ground_floor_spec(style, has_porte_cochere)

    # -- 1. Assign floor heights from grammar (exact typical values) ----------
    floor_heights: dict[int, float] = {}
    for i, ft in enumerate(floor_types):
        floor_heights[i] = grammar.get_floor_height(ft)

    # -- 2. Build nodes --------------------------------------------------------
    nodes: list[IRNode] = []
    y = 0.0

    for i, ft in enumerate(floor_types):
        height = floor_heights[i]

        if ft == FloorType.GROUND:
            node = GroundFloorNode(
                transform=Transform(position=(0.0, y, 0.0)),
                height=height,
                has_rustication=gf_spec.has_rustication,
                has_porte_cochere=has_porte_cochere,
                porte_cochere_bay_index=None,  # Assigned during facade composition
            )
        else:
            ornament = grammar.get_ornament_level(ft)
            node = FloorNode(
                transform=Transform(position=(0.0, y, 0.0)),
                floor_type=ft,
                height=height,
                y_offset=y,
                ornament_level=ornament,
            )

        nodes.append(node)
        y += height

    return nodes


def total_height(floor_nodes: list[IRNode]) -> float:
    """Sum the heights of a floor stack (excluding roof)."""
    total = 0.0
    for node in floor_nodes:
        if isinstance(node, (FloorNode, GroundFloorNode)):
            total += node.height
    return total
