"""Ground floor logic — shopfronts, porte-cochère, rustication.

The ground floor (rez-de-chaussée) has its own architectural vocabulary
distinct from the upper floors: tall commercial openings, rusticated
stonework, heavy keystones, and an optional carriage entrance
(porte-cochère).

This module populates a ``GroundFloorNode`` with the appropriate bay
children and ornament.
"""

from __future__ import annotations

from .grammar import HaussmannGrammar, BaySpec
from .types import (
    BayNode,
    BayType,
    CorniceNode,
    CustomBayStyle,
    FloorType,
    GroundFloorNode,
    GroundFloorType,
    IRNode,
    OrnamentLevel,
    OrnamentNode,
    PedimentStyle,
    PorteStyle,
    StoreType,
    StylePreset,
    SurroundStyle,
    Transform,
    WindowNode,
)
from .variation import Variation


def build_ground_floor(
    ground_node: GroundFloorNode,
    bay_layout: list[BaySpec],
    facade_width: float,
    style: StylePreset,
    variation: Variation,
    grammar: HaussmannGrammar | None = None,
    has_porte_cochere: bool = True,
    door_bay_index: int = -1,
    ground_floor_type: GroundFloorType = GroundFloorType.COMMERCIAL,
    porte_style: PorteStyle = PorteStyle.ARCHED,
    custom_bay_style: CustomBayStyle | None = None,
) -> None:
    """Populate a GroundFloorNode with bays appropriate to the ground floor type.

    Modifies *ground_node* in place, adding BayNode children for each
    bay position.  One bay may be designated as the porte-cochère
    (carriage entrance).

    Ground floor types:
    - COMMERCIAL: all non-porte bays are shopfronts (low sill ~0.15m)
    - RESIDENTIAL: all non-porte bays are standard windows (~1.2m sill)
    - MIXED: bays on one side of porte-cochère are shopfronts, other side
      residential; falls back to COMMERCIAL if no porte-cochère.

    When *door_bay_index* >= 0 it is used directly (pre-picked by the
    facade builder to ensure consistency with the layout strategy).
    Otherwise the variation system picks the bay.

    Rustication parameters and cornice are also set based on style.
    """
    if grammar is None:
        grammar = HaussmannGrammar()

    gf_spec = grammar.get_ground_floor_spec(style, has_porte_cochere)
    bay_count = len(bay_layout)

    # -- Porte-cochère placement -----------------------------------------------
    porte_bay_idx: int | None = None
    if has_porte_cochere and bay_count > 0:
        if door_bay_index >= 0:
            porte_bay_idx = door_bay_index
        else:
            porte_bay_idx = variation.pick_porte_cochere_bay(bay_count)
        ground_node.has_porte_cochere = True
        ground_node.porte_cochere_bay_index = porte_bay_idx
    else:
        ground_node.has_porte_cochere = False
        ground_node.porte_cochere_bay_index = None

    # -- Rustication -----------------------------------------------------------
    ground_node.has_rustication = gf_spec.has_rustication

    # -- Determine which bays are residential (MIXED logic) --------------------
    # For MIXED: one side of the porte-cochère is shopfront, other is residential.
    # Pick which side is which based on the variation RNG.
    residential_bays: set[int] = set()
    effective_type = ground_floor_type

    if effective_type == GroundFloorType.MIXED:
        if porte_bay_idx is None:
            # No door to split around — fall back to COMMERCIAL
            effective_type = GroundFloorType.COMMERCIAL
        elif porte_bay_idx == 0:
            # Door at left edge — all remaining bays are shopfronts
            effective_type = GroundFloorType.COMMERCIAL
        elif porte_bay_idx == bay_count - 1:
            # Door at right edge — all remaining bays are shopfronts
            effective_type = GroundFloorType.COMMERCIAL
        else:
            # Door in the middle — pick which side is residential
            shop_side = variation.rng.choice(["left", "right"])
            if shop_side == "left":
                residential_bays = set(range(porte_bay_idx + 1, bay_count))
            else:
                residential_bays = set(range(0, porte_bay_idx))

    if effective_type == GroundFloorType.RESIDENTIAL:
        residential_bays = set(range(bay_count))

    # -- Bay population --------------------------------------------------------
    for bay_spec in bay_layout:
        is_porte = bay_spec.index == porte_bay_idx

        if bay_spec.bay_type == BayType.CUSTOM:
            bay = _build_custom_ground_bay(
                bay_spec, ground_node.height, style, grammar,
                custom_bay_style=custom_bay_style,
            )
        elif is_porte:
            bay = _build_porte_cochere_bay(
                bay_spec, ground_node.height, gf_spec.porte_cochere_width,
                style, grammar, porte_style=porte_style,
            )
        elif bay_spec.index in residential_bays:
            bay = _build_residential_bay(
                bay_spec, ground_node.height, style, variation, grammar,
            )
        else:
            bay = _build_shopfront_bay(
                bay_spec, ground_node.height, gf_spec.shopfront_height,
                style, variation, grammar,
            )
        ground_node.children.append(bay)

    # -- Assign store types to consecutive shopfront groups --------------------
    _assign_store_types(ground_node)

    # -- Cornice above ground floor --------------------------------------------
    cornice = CorniceNode(
        transform=Transform(position=(0.0, ground_node.height, 0.0)),
        width=facade_width,
        profile_id="ground_cornice",
        projection=grammar.get_cornice_projection(is_roofline=False),
    )
    ground_node.children.append(cornice)


# ---------------------------------------------------------------------------
# Store type assignment
# ---------------------------------------------------------------------------

def _assign_store_types(ground_node: GroundFloorNode) -> None:
    """Group consecutive shopfront bays into stores and assign types.

    Groups of 1–2 consecutive SHOPFRONT bays become BOUTIQUE (small shop
    with a door + display window).  Groups of 3+ become CAFE (open terrace
    with folding doors and awning).
    """
    bays = [c for c in ground_node.children if isinstance(c, BayNode)]

    # Find groups of consecutive SHOPFRONT bays
    groups: list[list[BayNode]] = []
    current: list[BayNode] = []
    for bay in bays:
        if bay.bay_type == BayType.SHOPFRONT:
            current.append(bay)
        else:
            if current:
                groups.append(current)
                current = []
    if current:
        groups.append(current)

    # Assign store types
    for group in groups:
        if len(group) >= 3:
            st = StoreType.CAFE
            entry_idx = len(group) // 2  # center bay
        else:
            st = StoreType.BOUTIQUE
            entry_idx = 0  # first bay
        for i, bay in enumerate(group):
            bay.store_type = st
            bay.is_store_entry = (i == entry_idx)


# ---------------------------------------------------------------------------
# Individual bay construction
# ---------------------------------------------------------------------------

def _build_residential_bay(
    bay_spec: BaySpec,
    floor_height: float,
    style: StylePreset,
    variation: Variation,
    grammar: HaussmannGrammar,
) -> BayNode:
    """Build a residential ground-floor bay with a standard window.

    Residential ground floors have windows at ~1.2 m sill height (like
    upper floors), not the low shopfront sill (~0.15 m).  The window
    proportions follow the same ~60% rule as upper floors.
    """
    bay = BayNode(
        transform=Transform(position=(bay_spec.x_offset, 0.0, 0.0)),
        width=bay_spec.width,
        x_offset=bay_spec.x_offset,
        bay_type=BayType.WINDOW,
    )

    # Window width matches upper floors: window zone × width_ratio
    bp = grammar.profile.bays
    wp = grammar.profile.windows
    std_bay_window_w = bp.bay_width[1] * (1 - bp.pier_ratio)
    win_w = std_bay_window_w * wp.width_ratio
    win_w = max(0.5, min(win_w, bay_spec.width - 0.3))
    # Sill at 1.0m from ground
    sill_height = 1.0
    win_h = max(1.0, floor_height * 0.70 - sill_height)

    # Surround style based on richness
    if style == StylePreset.BOULEVARD:
        surround = SurroundStyle.PILASTERED
    elif style == StylePreset.RESIDENTIAL:
        surround = SurroundStyle.MOLDED
    else:
        surround = SurroundStyle.NONE

    window = WindowNode(
        transform=Transform(position=(0.0, sill_height, 0.0)),
        width=round(win_w, 3),
        height=round(win_h, 3),
        surround_style=surround,
        pediment=PedimentStyle.NONE,
        has_keystone=(style == StylePreset.BOULEVARD),
    )
    bay.children.append(window)

    # Keystone ornament on boulevard buildings
    if style == StylePreset.BOULEVARD:
        keystone = OrnamentNode(
            transform=Transform(
                position=(win_w / 2, sill_height + win_h, 0.0),
            ),
            ornament_id="keystone_ground",
            ornament_level=OrnamentLevel.RICH,
        )
        bay.children.append(keystone)

    return bay


def _build_shopfront_bay(
    bay_spec: BaySpec,
    floor_height: float,
    shopfront_height: float,
    style: StylePreset,
    variation: Variation,
    grammar: HaussmannGrammar,
) -> BayNode:
    """Build a commercial shopfront bay.

    Shopfronts have tall openings (~75% of floor height), typically with
    a transom window above.  On richer buildings, the opening is framed
    by rusticated stonework and topped with a heavy keystone.
    """
    bay = BayNode(
        transform=Transform(position=(bay_spec.x_offset, 0.0, 0.0)),
        width=bay_spec.width,
        x_offset=bay_spec.x_offset,
        bay_type=BayType.SHOPFRONT,
    )

    # Shopfront opening — wider than upper windows
    gfp = grammar.profile.ground_floor
    win_w = bay_spec.width * gfp.shopfront_width_ratio
    sill_height = gfp.shopfront_sill  # Nearly at ground level for shops

    # Surround style based on richness
    if style == StylePreset.BOULEVARD:
        surround = SurroundStyle.PILASTERED
    elif style == StylePreset.RESIDENTIAL:
        surround = SurroundStyle.MOLDED
    else:
        surround = SurroundStyle.NONE

    window = WindowNode(
        transform=Transform(position=(0.0, sill_height, 0.0)),
        width=round(win_w, 3),
        height=round(shopfront_height, 3),
        surround_style=surround,
        pediment=PedimentStyle.NONE,  # Ground floor openings don't have pediments
        has_keystone=(style != StylePreset.MODEST),
    )
    bay.children.append(window)

    # Keystone ornament above the opening
    if style != StylePreset.MODEST:
        keystone = OrnamentNode(
            transform=Transform(
                position=(win_w / 2, sill_height + shopfront_height, 0.0),
            ),
            ornament_id="keystone_ground",
            ornament_level=OrnamentLevel.RICH,
        )
        bay.children.append(keystone)

    # Rustication ornament on boulevard buildings
    if style == StylePreset.BOULEVARD:
        rustication = OrnamentNode(
            transform=Transform(position=(0.0, 0.0, 0.0)),
            ornament_id="rustication_bossage",
            ornament_level=OrnamentLevel.RICH,
        )
        bay.children.append(rustication)

    return bay


def _build_porte_cochere_bay(
    bay_spec: BaySpec,
    floor_height: float,
    porte_cochere_width: float,
    style: StylePreset,
    grammar: HaussmannGrammar,
    porte_style: PorteStyle = PorteStyle.ARCHED,
) -> BayNode:
    """Build the porte-cochère (carriage entrance) bay.

    The porte-cochère is wider than a standard shopfront, with a large
    arched or flat-topped opening.  Historically ~2.5-3.0 m wide and
    nearly full floor height to admit horse-drawn carriages.

    On rich buildings it features heavy rustication, a prominent keystone,
    and sometimes an arched surround.
    """
    bay = BayNode(
        transform=Transform(position=(bay_spec.x_offset, 0.0, 0.0)),
        width=bay_spec.width,
        x_offset=bay_spec.x_offset,
        bay_type=BayType.DOOR,
        porte_style=porte_style,
    )

    # Porte-cochère opening — tall, nearly full height
    opening_height = floor_height * grammar.profile.ground_floor.porte_cochere_height_ratio
    opening_width = min(porte_cochere_width, bay_spec.width * 0.95)

    # Arched surround on rich buildings, molded on others
    if style == StylePreset.BOULEVARD:
        surround = SurroundStyle.PILASTERED
        pediment = PedimentStyle.ARCHED
    elif style == StylePreset.RESIDENTIAL:
        surround = SurroundStyle.MOLDED
        pediment = PedimentStyle.ARCHED
    else:
        surround = SurroundStyle.NONE
        pediment = PedimentStyle.NONE

    door = WindowNode(
        transform=Transform(position=(0.0, 0.0, 0.0)),  # Starts at ground
        width=round(opening_width, 3),
        height=round(opening_height, 3),
        surround_style=surround,
        pediment=pediment,
        has_keystone=(style != StylePreset.MODEST),
    )
    bay.children.append(door)

    # Large keystone above the arch
    if style != StylePreset.MODEST:
        keystone = OrnamentNode(
            transform=Transform(
                position=(opening_width / 2, opening_height, 0.0),
            ),
            ornament_id="keystone_porte_cochere",
            ornament_level=OrnamentLevel.RICH,
        )
        bay.children.append(keystone)

    return bay


def _build_custom_ground_bay(
    bay_spec: BaySpec,
    floor_height: float,
    style: StylePreset,
    grammar: HaussmannGrammar,
    custom_bay_style: CustomBayStyle | None = None,
) -> BayNode:
    """Build a custom ground-floor bay — narrow residential window.

    Custom bays are too narrow for a shopfront, so they get a simple
    tall narrow window regardless of the custom_bay_style (which only
    affects upper floors).
    """
    bay = BayNode(
        transform=Transform(position=(bay_spec.x_offset, 0.0, 0.0)),
        width=bay_spec.width,
        x_offset=bay_spec.x_offset,
        bay_type=BayType.CUSTOM,
        custom_bay_style=custom_bay_style,
    )

    # Narrow window — same proportions as residential ground floor
    wp = grammar.profile.windows
    win_w = bay_spec.width * wp.width_ratio
    win_w = max(0.3, min(win_w, bay_spec.width - 0.1))
    sill_height = 1.0
    win_h = max(1.0, floor_height * 0.70 - sill_height)

    window = WindowNode(
        transform=Transform(position=(0.0, sill_height, 0.0)),
        width=round(win_w, 3),
        height=round(win_h, 3),
        surround_style=SurroundStyle.NONE,
        pediment=PedimentStyle.NONE,
        has_keystone=False,
    )
    bay.children.append(window)

    return bay
