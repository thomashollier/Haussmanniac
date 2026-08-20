"""Oriels — the projecting bay windows the 1882 decree finally allowed.

Paris had banned projections over the street since the edicts of 1607 and
1667: no encorbellements, everything flush to the alignment.  That ban is
why the haussmannian facade is so flat, and it is the same instinct as the
0.80 m cap on balconies.  The decree of 22 July 1882 lifted it, hedged
about with conditions — start at the étage noble, project no more than
0.40 m, stop below the cornice, and be demountable.  Masonry oriels
followed in 1893, and the 1902 règlement let them carry above the cornice.

An oriel is therefore the clearest date-stamp on a Paris facade: a flat
wall reads pre-1882, a rippling one reads Belle Époque.

This module decides where they go; ``backends`` decide how they look.
"""

from __future__ import annotations

from .grammar import BaySpec, HaussmannGrammar
from .reglement import OrielRule
from .types import (
    BayNode,
    BayType,
    FloorNode,
    GroundFloorNode,
    IRNode,
    OrielNode,
    OrielStyle,
    Transform,
    WindowNode,
)
from .variation import Variation


def build_oriels(
    floor_nodes: list[IRNode],
    bay_layout: list[BaySpec],
    rule: OrielRule,
    variation: Variation,
    grammar: HaussmannGrammar,
    door_bay_index: int = -1,
) -> list[OrielNode]:
    """Produce the oriels for one facade, or nothing if the era forbids them.

    Consumes RNG from *variation* only — pass an isolated stream so that
    adding oriels cannot disturb any other part of the building.
    """
    if not rule.allowed or not bay_layout:
        return []

    presence, pattern, style, material, span = variation.vary_oriel(rule, grammar)
    if not presence:
        return []

    # -- Vertical extent: start at the étage noble, stop at the legal top --
    floors = [n for n in floor_nodes if isinstance(n, (FloorNode, GroundFloorNode))]
    start_y = rule.start_height
    spanned = [n for n in floors
               if isinstance(n, FloorNode) and n.y_offset >= start_y - 1e-6]
    if not spanned:
        return []

    spanned = spanned[:max(1, span)]
    top_y = spanned[-1].y_offset + spanned[-1].height

    passes_cornice = False
    if top_y > rule.max_top + 1e-6:
        top_y = rule.max_top
    elif rule.may_pass_cornice:
        cornice = floors[-1].y_offset + floors[-1].height \
            if isinstance(floors[-1], FloorNode) else top_y
        if top_y >= cornice - 1e-6:
            # 1902: the projection may carry on past the cornice line.
            top_y = min(rule.max_top, top_y + (rule.max_top - cornice))
            passes_cornice = top_y > cornice + 1e-6

    height = top_y - start_y
    if height <= 0.0:
        return []

    # -- Which bays carry one -------------------------------------------------
    candidates = [b for b in bay_layout
                  if b.bay_type not in (BayType.CUSTOM, BayType.DOOR)
                  and b.index != door_bay_index]
    if not candidates:
        return []

    chosen = _pick_bays(candidates, pattern)
    projection = min(rule.max_projection, grammar.reglement.max_oriel_projection)

    # An oriel is as wide as the bay module it stands on, not just the
    # opening: it laps onto the half-pier either side, which is what gives
    # it the mass to read as a projection rather than a frame.
    pier_ratio = grammar.profile.bays.pier_ratio
    module = 1.0 - pier_ratio if pier_ratio < 0.95 else 1.0

    oriels: list[OrielNode] = []
    for bay in chosen:
        full_w = bay.width / module
        oriel = OrielNode(
            transform=Transform(
                position=(round(bay.x_offset - (full_w - bay.width) / 2, 4),
                          start_y, 0.0)),
            width=round(full_w, 4),
            height=round(height, 3),
            projection=round(projection, 3),
            style=style,
            material=material,
            bay_index=bay.index,
            floor_span=len(spanned),
            passes_cornice=passes_cornice,
        )
        # The oriel carries its own glazing: one window per storey it runs
        # through, matching the bay window it stands in front of, with its
        # position given relative to the oriel's own base.
        oriel.children.extend(
            _front_windows(spanned, bay, start_y, top_y)
        )
        oriels.append(oriel)
    return oriels


def _front_windows(
    spanned: list[FloorNode],
    bay: BaySpec,
    start_y: float,
    top_y: float,
) -> list[IRNode]:
    """Copy the bay's window on each spanned storey onto the oriel front."""
    out: list[IRNode] = []
    for floor in spanned:
        source = _bay_window(floor, bay.x_offset)
        if source is None:
            continue
        y = floor.y_offset + source.transform.position[1]
        if y + source.height > top_y + 1e-6:
            continue
        out.append(WindowNode(
            transform=Transform(position=(0.0, round(y - start_y, 3), 0.0)),
            width=source.width,
            height=source.height,
            surround_style=source.surround_style,
            pediment=source.pediment,
            has_keystone=False,
        ))
    return out


def _bay_window(floor: FloorNode, x_offset: float) -> WindowNode | None:
    """Find the window of the bay at *x_offset* on *floor*."""
    for child in floor.children:
        if isinstance(child, BayNode) and abs(child.x_offset - x_offset) < 1e-4:
            for grand in child.children:
                if isinstance(grand, WindowNode):
                    return grand
    return None


def _pick_bays(candidates: list[BaySpec], pattern: str) -> list[BaySpec]:
    """Select the bays an oriel sits over.

    ``CENTER`` puts a single oriel on the middle bay, ``PAIR`` flanks the
    centre symmetrically, and ``EVERY_BAY`` runs one over every bay — the
    treatment that gives late facades their rippled front.
    """
    if pattern == "EVERY_BAY":
        return candidates
    if pattern == "PAIR" and len(candidates) >= 3:
        return [candidates[0], candidates[-1]]
    return [candidates[len(candidates) // 2]]
