"""Haussmann architectural grammar — proportional rules and constraints.

Every magic number in this module comes from the regulatory and stylistic
conventions of the Haussmann renovation of Paris (1853-1870s) and the
subsequent construction that followed the same vocabulary through ~1914.

References:
- François Loyer, *Paris XIXe siècle: l'immeuble et la rue* (1987)
- Règlement de voirie, Préfecture de la Seine (1859, 1882, 1902)
- Measured surveys of buildings on Bd Haussmann, Rue de Rivoli, Av de l'Opéra

All dimensions in metres.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from .profile import FacadeProfile, GRAND_BOULEVARD
from .types import (
    BayType,
    DormerStyle,
    FloorType,
    LayoutStrategy,
    MansardType,
    OrnamentLevel,
    PedimentStyle,
    RailingPattern,
    StylePreset,
    SurroundStyle,
)


# ---------------------------------------------------------------------------
# Spec dataclasses (grammar outputs)
# ---------------------------------------------------------------------------

@dataclass
class FloorSpec:
    """Specification for one storey produced by the grammar."""
    floor_type: FloorType
    height: float             # Floor-to-floor height in metres
    ornament_level: OrnamentLevel
    has_balcony: bool         # Continuous balcony on this floor?
    has_balconette: bool      # Individual balconettes per bay?


@dataclass
class BaySpec:
    """Specification for one vertical bay.

    ``width`` is the **bay window** width (the opening between bay piers).
    ``x_offset`` is the left edge of the bay window relative to the facade.
    """
    index: int
    x_offset: float           # Left edge of bay window, relative to facade origin
    width: float              # Bay window width (opening between bay piers)
    bay_type: BayType
    is_center: bool = False   # Deprecated — kept for backward compat


@dataclass
class WindowSpec:
    """Window specification derived from floor type and ornament level."""
    width: float
    height: float
    surround_style: SurroundStyle
    pediment: PedimentStyle
    has_keystone: bool


@dataclass
class RoofSpec:
    """Roof parameters derived from the grammar."""
    mansard_type: MansardType
    mansard_lower_angle_deg: float  # Steep section angle
    mansard_upper_angle_deg: float  # Flat section angle (BROKEN/SHALLOW)
    mansard_height: float           # Total mansard height
    break_height: float             # Height of steep-to-flat transition (BROKEN only)
    dormer_style: DormerStyle
    dormer_every_n_bays: int        # 1 = one per bay, 2 = every other, etc.
    chimney_count: int
    chimney_height: float


@dataclass
class GroundFloorSpec:
    """Ground-floor parameters."""
    height: float
    has_rustication: bool
    shopfront_height: float      # Height of commercial openings
    porte_cochere_width: float   # Width of carriage entrance (0 if none)


# ---------------------------------------------------------------------------
# Floor-type ↔ profile attribute mapping
# ---------------------------------------------------------------------------

_FLOOR_ATTR: dict[FloorType, str] = {
    FloorType.GROUND:   "ground",
    FloorType.ENTRESOL: "entresol",
    FloorType.NOBLE:    "noble",
    FloorType.THIRD:    "third",
    FloorType.FOURTH:   "fourth",
    FloorType.FIFTH:    "fifth",
    FloorType.MANSARD:  "mansard",
}

# ---------------------------------------------------------------------------
# Non-profile constants (style-level, not proportional)
# ---------------------------------------------------------------------------

# Cornice height targets by style (the regulated wall height *below* the
# mansard).  The mansard attic sits above this line and is not counted.
# Based on the 1859/1882/1902 décrets préfectoraux tying max cornice
# height to street width.
_CORNICE_TARGET: dict[StylePreset, float] = {
    StylePreset.BOULEVARD:   18.0,   # Wide boulevard (20m+ street)
    StylePreset.RESIDENTIAL: 15.5,   # Medium street (~15m)
    StylePreset.MODEST:      12.0,   # Narrow street (~12m)
}

# Step-down ratio between consecutive middle floors (3rd → 4th → 5th).
# Each floor is ~93% of the one below it, creating the characteristic
# Haussmann taper.
_MIDDLE_FLOOR_STEP = 0.93

# Corner chamfer (pan coupé)
_CHAMFER_WIDTH = 3.0                 # metres — standard 45° cut


# ---------------------------------------------------------------------------
# Grammar class
# ---------------------------------------------------------------------------

class HaussmannGrammar:
    """Encodes the proportional and compositional rules of Haussmann buildings.

    All methods are deterministic given the same inputs.  Randomisation is
    handled separately by the variation system — the grammar only defines
    *typical* values and valid ranges.
    """

    def __init__(self, profile: FacadeProfile | None = None) -> None:
        self.profile = profile if profile is not None else GRAND_BOULEVARD

    # -- Floor stacking -------------------------------------------------------

    @staticmethod
    def floor_sequence(num_floors: int, has_entresol: bool = True) -> list[FloorType]:
        """Return the ordered sequence of floor types for *num_floors* storeys.

        The sequence always starts with GROUND and ends with MANSARD.
        The entresol is included only when *has_entresol* is True and there
        are enough floors.  Middle floors are filled in order:
        NOBLE → THIRD → FOURTH → FIFTH.

        Typical Haussmann buildings have 6-7 storeys (including mansard).
        """
        if num_floors < 3:
            # Minimal: ground + mansard (+ optionally one middle)
            seq = [FloorType.GROUND]
            if num_floors >= 2:
                seq.append(FloorType.MANSARD)
            return seq

        seq: list[FloorType] = [FloorType.GROUND]
        remaining = num_floors - 2  # Reserve ground + mansard

        if has_entresol and remaining >= 2:
            # Only add entresol if we still have room for at least the noble floor
            seq.append(FloorType.ENTRESOL)
            remaining -= 1

        # Fill middle floors in canonical order
        middle_order = [FloorType.NOBLE, FloorType.THIRD, FloorType.FOURTH, FloorType.FIFTH]
        for ft in middle_order:
            if remaining <= 0:
                break
            seq.append(ft)
            remaining -= 1

        # If there are *still* remaining floors (very tall building), repeat FOURTH
        while remaining > 0:
            seq.append(FloorType.FOURTH)
            remaining -= 1

        seq.append(FloorType.MANSARD)
        return seq

    def get_floor_height(self, floor_type: FloorType) -> float:
        """Return the typical floor-to-floor height for *floor_type*."""
        attr = _FLOOR_ATTR[floor_type]
        return getattr(self.profile.floors, attr)[1]  # [1] = typical

    def get_floor_height_range(self, floor_type: FloorType) -> tuple[float, float]:
        """Return (min, max) height for *floor_type*."""
        attr = _FLOOR_ATTR[floor_type]
        mn, _, mx = getattr(self.profile.floors, attr)
        return (mn, mx)

    def get_floor_specs(
        self,
        num_floors: int,
        has_entresol: bool = True,
    ) -> list[FloorSpec]:
        """Produce a full vertical stack of FloorSpec for the building."""
        sequence = self.floor_sequence(num_floors, has_entresol)
        specs: list[FloorSpec] = []
        for ft in sequence:
            specs.append(FloorSpec(
                floor_type=ft,
                height=self.get_floor_height(ft),
                ornament_level=self.get_ornament_level(ft),
                has_balcony=self.has_continuous_balcony(ft),
                has_balconette=self.has_balconette(ft),
            ))
        return specs

    # -- Cornice budget --------------------------------------------------------

    @staticmethod
    def get_cornice_target(style: StylePreset) -> float:
        """Target cornice height (wall top, below mansard) for a style preset."""
        return _CORNICE_TARGET[style]

    def compute_middle_floor_heights(
        self,
        remaining_budget: float,
        middle_count: int,
    ) -> list[float]:
        """Distribute remaining cornice budget to middle floors with step-down.

        Middle floors (3rd, 4th, 5th) share whatever height remains after
        the fixed floors (ground, entresol, noble) are subtracted from the
        cornice target.  Each successive floor is ~93% of the one below,
        creating the characteristic Haussmann taper.

        Returns heights in order (3rd first, then 4th, 5th…), clamped
        to [2.4, 3.2] m.
        """
        if middle_count <= 0:
            return []

        r = _MIDDLE_FLOOR_STEP
        geo_sum = sum(r ** i for i in range(middle_count))
        h_first = remaining_budget / geo_sum

        # Cap below noble floor — each successive floor shorter than the last
        noble_h = self.get_floor_height(FloorType.NOBLE)
        cap = noble_h - 0.15  # first middle floor at least 15 cm below noble

        heights: list[float] = []
        for i in range(middle_count):
            h = h_first * (r ** i)
            h = max(2.4, min(h, cap))
            heights.append(round(h, 3))
            cap = h - 0.10  # next floor must be shorter

        return heights

    # -- Bay layout ------------------------------------------------------------

    def max_feasible_bays(self, facade_width: float) -> int:
        """Maximum number of bays that fit using minimum bay width."""
        bay_min = self.profile.bays.bay_width[0]
        return max(1, int(facade_width / bay_min))

    def compute_bay_count(self, facade_width: float, style: StylePreset = StylePreset.RESIDENTIAL) -> int:
        """Determine the typical number of bays from facade width.

        Bay count follows historical Parisian parcel structure, always odd
        (central bay is the organizing spine of the facade):
        - < threshold_5:  3 bays (narrow — minimum Haussmann program)
        - < threshold_7:  5 bays (typical ~15m investment frontage)
        - < threshold_9:  7 bays (grand boulevard / consolidated lots)
        - >= threshold_9: 9 bays (exceptional / institutional)
        """
        thresholds = self.profile.bays
        if facade_width < thresholds.threshold_5_bays:
            return 3
        elif facade_width < thresholds.threshold_7_bays:
            return 5
        elif facade_width < thresholds.threshold_9_bays:
            return 7
        else:
            return 9

    def compute_edge_pier(self, facade_width: float, bay_count: int) -> float:
        """Compute edge pier width for a given facade width and bay count.

        The edge pier sits between the outermost bay and the facade edge.
        It includes a half bay-pier on the inner side plus any remaining
        wall width.
        """
        bay_w = self.profile.bays.bay_width[1]
        return max(0.0, (facade_width - bay_count * bay_w) / 2.0)

    def smart_bay_count(
        self,
        facade_width: float,
        desired: int,
        style: StylePreset = StylePreset.RESIDENTIAL,
    ) -> int:
        """Ensure edge piers are at least 0.5 m.  Reduces count if too narrow."""
        bay_w = self.profile.bays.bay_width[1]
        min_edge = 0.5

        for count in range(desired, 0, -1):
            edge = (facade_width - count * bay_w) / 2.0
            if edge >= min_edge:
                return count

        return 3  # safe fallback

    def get_bay_layout(
        self,
        facade_width: float,
        style: StylePreset = StylePreset.RESIDENTIAL,
        bay_count: Optional[int] = None,
        strategy: LayoutStrategy = LayoutStrategy.UNIFORM,
        door_bay_index: int = -1,
    ) -> list[BaySpec]:
        """Distribute bays across *facade_width*.

        Backward-compatible wrapper around :meth:`solve_bay_layout`.
        The *strategy* and *door_bay_index* parameters are accepted but
        ignored — the solver uses uniform bays with edge pier absorption.
        """
        return self.solve_bay_layout(
            facade_width=facade_width,
            bay_count=bay_count,
        )

    # -- Bay layout solver ------------------------------------------------------

    def solve_bay_layout(
        self,
        facade_width: float,
        bay_count: Optional[int] = None,
        has_door: bool = False,
        door_bay_index: int = -1,
        rng: random.Random | None = None,
    ) -> list[BaySpec]:
        """Fit bays into *facade_width*.

        A **bay** is half bay-pier + bay window + half bay-pier, measured
        centerline-to-centerline.  All bays are the same width (from the
        profile's typical ``bay_width``).  **Edge piers** absorb all
        remaining width between the outermost bays and the facade edges.

        When *has_door* is True and *door_bay_index* >= 0, the door bay
        is ``door_bay_width_ratio`` times wider than a standard bay.  The
        door bay has the same pier width as other bays — only the window
        zone is wider.  ``door_bay_index`` is clamped to the center bay
        if it exceeds the final bay count.

        If edge piers come out too narrow (< 0.1 m), ``bay_count`` is
        reduced by 2 until they fit.

        BaySpec.width is the **bay window** width (the opening between
        bay piers), and BaySpec.x_offset is its left edge.
        """
        bp = self.profile.bays

        if bay_count is None:
            bay_count = self.compute_bay_count(facade_width)
        if bay_count % 2 == 0:
            bay_count += 1

        bay_w = bp.bay_width[1]       # full bay: half bay-pier + bay window + half bay-pier
        bay_pier_w = bay_w * bp.pier_ratio
        half_pier = bay_pier_w / 2.0
        bay_window_w = bay_w - bay_pier_w

        # Door bay sizing
        use_door = has_door and door_bay_index >= 0 and bp.door_bay_width_ratio > 1.0
        door_bay_w = bay_w * bp.door_bay_width_ratio if use_door else bay_w
        door_window_w = door_bay_w - bay_pier_w if use_door else bay_window_w

        # Compute interior width (all bays combined)
        def _interior(n: int, door_idx: int) -> float:
            if use_door and 0 <= door_idx < n:
                return (n - 1) * bay_w + door_bay_w
            return n * bay_w

        # Clamp door bay index
        if use_door:
            door_bay_index = min(door_bay_index, bay_count - 1)

        # Reduce bay count if edge piers too narrow
        min_edge = 0.1
        while bay_count >= 3:
            interior = _interior(bay_count, door_bay_index)
            edge = (facade_width - interior) / 2.0
            if edge >= min_edge:
                break
            bay_count -= 2
            # Re-clamp door index after reducing bay count
            if use_door:
                door_bay_index = min(door_bay_index, bay_count - 1)

        interior = _interior(bay_count, door_bay_index)
        edge = max(0.0, (facade_width - interior) / 2.0)

        # Build specs with cumulative x positioning
        specs: list[BaySpec] = []
        x_cursor = edge  # left edge of first full bay (including half-pier)
        for i in range(bay_count):
            is_door = use_door and i == door_bay_index
            this_bay_w = door_bay_w if is_door else bay_w
            this_window_w = door_window_w if is_door else bay_window_w

            x = x_cursor + half_pier  # left edge of bay window
            specs.append(BaySpec(
                index=i,
                x_offset=round(x, 4),
                width=round(this_window_w, 4),
                bay_type=BayType.DOOR if is_door else BayType.WINDOW,
            ))
            x_cursor += this_bay_w
        return specs

    # -- Ornament rules --------------------------------------------------------

    @staticmethod
    def get_ornament_level(floor_type: FloorType) -> OrnamentLevel:
        """Return the ornament level for a given floor type.

        Ground and noble floors are richest; ornament decreases upward.
        """
        mapping = {
            FloorType.GROUND:   OrnamentLevel.RICH,
            FloorType.ENTRESOL: OrnamentLevel.SIMPLE,
            FloorType.NOBLE:    OrnamentLevel.RICH,
            FloorType.THIRD:    OrnamentLevel.MODERATE,
            FloorType.FOURTH:   OrnamentLevel.SIMPLE,
            FloorType.FIFTH:    OrnamentLevel.SIMPLE,
            FloorType.MANSARD:  OrnamentLevel.NONE,
        }
        return mapping.get(floor_type, OrnamentLevel.NONE)

    def get_window_spec(
        self,
        floor_type: FloorType,
        ornament_level: OrnamentLevel,
        bay_width: float,
        floor_height: float,
    ) -> WindowSpec:
        """Derive window dimensions and decoration from floor context.

        Window height is proportional to floor height (≈60 %).
        Surround and pediment complexity follow ornament level.
        """
        wp = self.profile.windows

        # Window width: ratio of bay width
        win_w = bay_width * wp.width_ratio
        win_w = max(0.5, min(win_w, bay_width - 0.3))

        # Window height depends on floor type
        surround_pad = wp.surround_pad
        bordered_w = win_w + 2 * surround_pad
        if floor_type == FloorType.ENTRESOL:
            win_h = floor_height * wp.entresol_height_ratio
        elif floor_type == FloorType.FIFTH:
            win_h = floor_height * wp.fifth_height_ratio
        elif floor_type == FloorType.NOBLE:
            # bordered aspect ratio, no bottom border
            win_h = wp.noble_bordered_aspect * bordered_w - surround_pad
            # Noble windows must never be shorter than upper floor windows
            min_noble_h = floor_height * wp.upper_height_ratio
            win_h = max(win_h, min_noble_h)
        else:
            # Floors above noble: windows cover upper_height_ratio of floor height
            win_h = floor_height * wp.upper_height_ratio
        win_h = max(1.0, win_h)

        # Surround style by ornament level
        if ornament_level == OrnamentLevel.RICH:
            surround = SurroundStyle.PILASTERED
        elif ornament_level == OrnamentLevel.MODERATE:
            surround = SurroundStyle.MOLDED
        elif ornament_level == OrnamentLevel.SIMPLE:
            surround = SurroundStyle.EARED
        else:
            surround = SurroundStyle.NONE

        # Pediment: only on noble and sometimes third floor
        pediment = PedimentStyle.NONE
        if floor_type == FloorType.NOBLE:
            pediment = PedimentStyle.TRIANGULAR
        elif floor_type == FloorType.THIRD and ornament_level.value >= OrnamentLevel.MODERATE.value:
            pediment = PedimentStyle.SEGMENTAL

        # Keystone: only on rich ornament
        has_keystone = ornament_level == OrnamentLevel.RICH and floor_type != FloorType.ENTRESOL

        return WindowSpec(
            width=round(win_w, 3),
            height=round(win_h, 3),
            surround_style=surround,
            pediment=pediment,
            has_keystone=has_keystone,
        )

    # -- Balcony rules ---------------------------------------------------------

    def has_continuous_balcony(self, floor_type: FloorType) -> bool:
        """Continuous wrought-iron balcony on configured floors."""
        return floor_type.name in self.profile.balconies.continuous_floors

    def has_balconette(self, floor_type: FloorType) -> bool:
        """Individual balconettes on configured floors."""
        return floor_type.name in self.profile.balconies.balconette_floors

    def get_railing_height(self) -> float:
        """Regulatory minimum railing height."""
        return self.profile.balconies.railing_height

    @staticmethod
    def get_railing_pattern(floor_type: FloorType) -> RailingPattern:
        """Railing pattern varies by floor richness."""
        if floor_type == FloorType.NOBLE:
            return RailingPattern.CLASSIC
        elif floor_type == FloorType.FIFTH:
            return RailingPattern.GEOMETRIC
        return RailingPattern.SIMPLE

    # -- Roof rules ------------------------------------------------------------

    def get_roof_spec(
        self,
        bay_count: int,
        style: StylePreset = StylePreset.RESIDENTIAL,
        is_front: bool = True,
    ) -> RoofSpec:
        """Derive roof parameters from bay count and style preset.

        Mansard types by style and orientation:
        - BOULEVARD front:    STEEP  (75°, near-vertical, full dormer zone)
        - RESIDENTIAL front:  BROKEN (70° lower breaking to 20° above dormers)
        - MODEST front:       BROKEN (65° lower, dormers every other bay)
        - All rear facades:   SHALLOW (no dormers)
        """
        rp = self.profile.roof

        # -- Mansard type and angles ----------------------------------------
        if not is_front:
            mansard_type = MansardType.SHALLOW
        elif style == StylePreset.RESIDENTIAL:
            mansard_type = MansardType.BROKEN
        else:
            # BOULEVARD and MODEST: steep near-vertical mansard
            mansard_type = MansardType.STEEP

        if mansard_type == MansardType.STEEP:
            lower_angle = rp.lower_angle_deg   # Near-vertical
            upper_angle = 15.0                 # Nearly flat cap (barely visible)
            break_h = 0.0                      # No break — single steep face
        elif mansard_type == MansardType.BROKEN:
            lower_angle = 70.0                 # Very steep lower section
            upper_angle = rp.upper_angle_deg   # Flatter upper section
            break_h = 2.0                      # Break at 2m — just above dormer heads
        else:  # SHALLOW
            lower_angle = 65.0     # 25° from vertical
            upper_angle = 65.0     # Same angle (no break)
            break_h = 0.0

        # -- Dormers -------------------------------------------------------
        if mansard_type == MansardType.SHALLOW:
            dormer_every = 0       # No dormers on rear/side slopes
            dormer_style = DormerStyle.FLAT_SLOPE
        elif style == StylePreset.BOULEVARD:
            dormer_every = 1       # Every bay — curved pediment cap
            dormer_style = DormerStyle.PEDIMENT_CURVED
        elif style == StylePreset.MODEST:
            dormer_every = 2       # Every other bay — curved pediment
            dormer_style = DormerStyle.PEDIMENT_CURVED
        else:
            dormer_every = 1       # Every bay — triangular pediment
            dormer_style = DormerStyle.PEDIMENT_TRIANGLE

        # Chimney stacks: roughly 1 per 2 bays, minimum 2
        chimney_count = max(2, (bay_count + 1) // 2)

        return RoofSpec(
            mansard_type=mansard_type,
            mansard_lower_angle_deg=lower_angle,
            mansard_upper_angle_deg=upper_angle,
            mansard_height=rp.mansard_height,
            break_height=break_h,
            dormer_style=dormer_style,
            dormer_every_n_bays=dormer_every,
            chimney_count=chimney_count,
            chimney_height=rp.chimney_height,
        )

    # -- Ground floor rules ----------------------------------------------------

    def get_ground_floor_spec(
        self,
        style: StylePreset = StylePreset.RESIDENTIAL,
        has_porte_cochere: bool = True,
    ) -> GroundFloorSpec:
        """Ground-floor proportions: commercial openings and carriage entrance."""
        height = self.get_floor_height(FloorType.GROUND)

        # Shopfront opening ≈ 75% of ground floor height
        shopfront_h = round(height * 0.75, 2)

        # Porte-cochère width: ~2.5-3.0 m (enough for a carriage / car)
        porte_w = 2.8 if has_porte_cochere else 0.0

        # Rustication on all but the most modest buildings
        has_rust = style != StylePreset.MODEST

        return GroundFloorSpec(
            height=height,
            has_rustication=has_rust,
            shopfront_height=shopfront_h,
            porte_cochere_width=porte_w,
        )

    # -- Cornice rules ---------------------------------------------------------

    @staticmethod
    def get_cornice_projection(is_roofline: bool = False) -> float:
        """How far a cornice projects from the wall face.

        The roofline cornice is heavier (~0.4 m); inter-floor cornices
        are lighter (~0.12 m).
        """
        return 0.40 if is_roofline else 0.12

    @staticmethod
    def has_roofline_modillions(style: StylePreset) -> bool:
        """Modillions (bracket-like ornaments) under the main cornice."""
        return style == StylePreset.BOULEVARD

    @staticmethod
    def has_roofline_dentils(style: StylePreset) -> bool:
        """Dentil molding under the main cornice."""
        return style in (StylePreset.BOULEVARD, StylePreset.RESIDENTIAL)

    # -- Corner chamfer --------------------------------------------------------

    @staticmethod
    def get_chamfer_width() -> float:
        """Standard pan coupé width at street intersections."""
        return _CHAMFER_WIDTH
