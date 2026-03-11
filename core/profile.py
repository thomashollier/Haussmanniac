"""Facade profile — parameterised building proportions.

A ``FacadeProfile`` bundles every tunable proportion of a Haussmann facade
into a single, copyable, serialisable object.  The grammar reads from
a profile instead of module-level constants, making it easy to define
presets and generate controlled variations.

**Ratios vs absolutes**: profile stores ratios for things that scale
(window width = 65 % of bay) and absolute values for physically
constrained things (railing height = 1.0 m).  Derived values are
computed at call-time by grammar methods.

**Two levels of randomness**:

1. ``vary_profile()`` shifts proportions coherently — building DNA.
2. ``Variation`` (in variation.py) makes per-element random choices
   during IR generation — element-level noise.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Nested parameter groups
# ---------------------------------------------------------------------------

@dataclass
class FloorHeights:
    """Floor heights as (min, typical, max) tuples in metres."""
    ground:   tuple[float, float, float] = (3.2, 3.8, 4.5)
    entresol: tuple[float, float, float] = (1.8, 2.3, 2.8)
    noble:    tuple[float, float, float] = (2.8, 3.3, 4.0)
    third:    tuple[float, float, float] = (2.4, 2.95, 3.5)
    fourth:   tuple[float, float, float] = (2.2, 2.75, 3.3)
    fifth:    tuple[float, float, float] = (2.0, 2.35, 3.0)
    mansard:  tuple[float, float, float] = (1.8, 2.2, 2.8)


@dataclass
class BayProportions:
    """Bay and pier sizing.

    A **bay** is measured centerline-to-centerline of its piers:
    half bay-pier + bay window + half bay-pier.

    ``bay_width`` is this full repeating unit.
    ``pier_ratio`` is the fraction of ``bay_width`` occupied by the
    bay pier.  The remainder is the bay window (the opening).

    **Edge piers** are separate — they sit between the outermost bays
    and the facade edges, absorbing all leftover width.
    """
    bay_width: tuple[float, float, float] = (1.50, 2.00, 2.50)
    pier_ratio: float = 0.30           # bay pier width as fraction of bay width
    door_bay_width_ratio: float = 1.0  # door bay width as multiple of standard bay width
    # Bay count thresholds (facade width breakpoints)
    threshold_5_bays: float = 8.0
    threshold_7_bays: float = 13.0
    threshold_9_bays: float = 18.0


@dataclass
class WindowProportions:
    """Window sizing relative to bay window and floor."""
    width_ratio: float = 0.65              # window frame width / bay window width
    noble_bordered_aspect: float = 2.575   # (win+border) height / (win+border) width
    upper_height_ratio: float = 0.64       # window height / floor height (3rd-4th)
    fifth_height_ratio: float = 0.65       # window height / floor height (5th)
    entresol_height_ratio: float = 0.60    # window height / floor height (entresol)
    surround_pad: float = 0.05            # border thickness (metres)
    sill_position_ratio: float = 0.55      # sill position in remaining space below window
    noble_max_height_ratio: float = 0.78   # cap noble window at this fraction of floor height


@dataclass
class GroundFloorProportions:
    """Ground floor openings."""
    shopfront_sill: float = 0.15           # metres above ground
    residential_sill: float = 1.0          # metres above ground
    shopfront_width_ratio: float = 0.85    # opening width / bay width
    residential_width_ratio: float = 0.40  # window width / bay width
    porte_cochere_height_ratio: float = 0.80  # opening height / floor height


@dataclass
class OrnamentParams:
    """Ornamental element dimensions."""
    pilaster_width: float = 0.10    # metres
    pilaster_depth: float = 0.08
    pilaster_offset: float = 0.05   # gap between pilaster and bay edge
    has_pediments: bool = False
    pediment_width_ratio: float = 0.80   # pediment width / bay width
    pediment_height: float = 0.20        # metres


@dataclass
class BalconyParams:
    """Balcony configuration."""
    continuous_floors: list[str] = field(default_factory=lambda: ["NOBLE"])
    balconette_floors: list[str] = field(default_factory=lambda: ["FIFTH"])
    railing_height: float = 1.0
    balcony_depth: float = 0.40
    balconette_depth: float = 0.25
    noble_sill_at_floor: bool = True   # windows touch balcony on noble floor


@dataclass
class RoofParams:
    """Mansard roof parameters."""
    mansard_height: float = 2.5
    mansard_height_short: float = 0.0  # when > 0, variation picks between short/tall
    lower_angle_deg: float = 80.0
    upper_angle_deg: float = 20.0
    dormer_width_ratio: float = 0.35
    dormer_max_height: float = 1.6    # metres — cap on dormer height
    chimney_height: float = 2.0
    ridge_to_edge_ratio: float = 1.0  # ridge chimney count multiplier vs edge


@dataclass
class RenderParams:
    """SVG rendering parameters (not architectural, but visual)."""
    ground_cornice_height: float = 0.15
    ground_cornice_dentil_spacing: float = 0.12
    awning_height: float = 0.30
    awning_projection: float = 0.12
    string_course_height: float = 0.06


# ---------------------------------------------------------------------------
# FacadeProfile container
# ---------------------------------------------------------------------------

@dataclass
class FacadeProfile:
    """Complete set of proportional parameters for a Haussmann facade."""
    name: str = "custom"
    typical_lot_width: tuple[float, float, float] = (12.75, 15.0, 18.0)  # (min, typical, max) metres
    typical_lot_depth: float = 12.0     # default lot depth for this style
    typical_num_floors: int = 7         # default floor count for this style
    has_entresol: bool = True           # whether this style includes an entresol
    floors: FloorHeights = field(default_factory=FloorHeights)
    bays: BayProportions = field(default_factory=BayProportions)
    windows: WindowProportions = field(default_factory=WindowProportions)
    ground_floor: GroundFloorProportions = field(default_factory=GroundFloorProportions)
    ornament: OrnamentParams = field(default_factory=OrnamentParams)
    balconies: BalconyParams = field(default_factory=BalconyParams)
    roof: RoofParams = field(default_factory=RoofParams)
    render: RenderParams = field(default_factory=RenderParams)


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

# Grand boulevard — tuned to the "perfect standard".
GRAND_BOULEVARD = FacadeProfile(
    name="grand_boulevard",
    typical_lot_width=(13.75, 16.0, 19.0),
    bays=BayProportions(door_bay_width_ratio=1.5),
    windows=WindowProportions(upper_height_ratio=0.675),
)

RESIDENTIAL = FacadeProfile(
    name="residential",
    typical_lot_width=(10.0, 12.0, 14.5),  # 5 bays + wide door bay
    typical_num_floors=6,       # no 5th floor
    roof=RoofParams(chimney_height=1.2),
    floors=FloorHeights(
        ground=(2.8, 3.5, 4.2),
        entresol=(1.4, 1.7, 2.1),
        noble=(2.4, 3.0, 3.6),
        third=(2.2, 2.8, 3.4),
        fourth=(2.0, 2.6, 3.2),
        fifth=(1.8, 2.4, 3.0),
    ),
    bays=BayProportions(door_bay_width_ratio=1.5),
    windows=WindowProportions(
        width_ratio=0.60,
        noble_bordered_aspect=2.3,
    ),
    ornament=OrnamentParams(pilaster_width=0.08),
    balconies=BalconyParams(balcony_depth=0.35),
)

MODEST = FacadeProfile(
    name="modest",
    typical_lot_width=(7.0, 7.45, 10.0),
    typical_lot_depth=10.0,
    typical_num_floors=5,       # no entresol, no 5th floor
    has_entresol=False,
    roof=RoofParams(
        mansard_height=2.65,           # tall roof (with dormers)
        mansard_height_short=1.725,    # short roof (no dormers)
        dormer_width_ratio=0.25,
        dormer_max_height=1.1,
        chimney_height=1.2,
        ridge_to_edge_ratio=2.0,       # 2:1 ridge-to-edge chimney ratio
    ),
    floors=FloorHeights(
        ground=(2.4, 3.15, 3.6),
        entresol=(0, 0, 0),  # no entresol
        noble=(2.1, 2.875, 3.2),
        third=(1.9, 2.83, 3.0),
        fourth=(1.8, 2.6, 2.8),
    ),
    bays=BayProportions(
        bay_width=(1.5, 2.1, 2.5),
        pier_ratio=0.315,
    ),
    windows=WindowProportions(
        width_ratio=0.55,
        noble_bordered_aspect=1.575,
        upper_height_ratio=0.54,
        fifth_height_ratio=0.52,
        surround_pad=0.03,
        sill_position_ratio=0.62,
        noble_max_height_ratio=0.78,
    ),
    ornament=OrnamentParams(pilaster_width=0.0, has_pediments=False),
    balconies=BalconyParams(
        continuous_floors=[],
        balconette_floors=["FIFTH"],
        balcony_depth=0.325,
        balconette_depth=0.245,
    ),
)

PRESETS: dict[str, FacadeProfile] = {
    "grand_boulevard": GRAND_BOULEVARD,
    "residential": RESIDENTIAL,
    "modest": MODEST,
}


def get_profile(name: str) -> FacadeProfile:
    """Return a deep copy of a named preset profile."""
    if name not in PRESETS:
        raise KeyError(f"Unknown profile preset: {name!r}. "
                       f"Available: {', '.join(PRESETS)}")
    return copy.deepcopy(PRESETS[name])


# ---------------------------------------------------------------------------
# Profile variation
# ---------------------------------------------------------------------------

def vary_profile(
    profile: FacadeProfile,
    seed: int,
    amount: float = 0.1,
) -> FacadeProfile:
    """Create a new profile with random perturbations.

    *amount* = 0.0 returns an exact copy; *amount* = 1.0 gives maximum
    drift.  Each parameter varies within its (min, max) range scaled by
    *amount*.  Ratios are clamped to sensible bounds.

    This produces a different building *archetype* — coherent proportional
    shifts — not per-element noise (that's handled by ``Variation``).
    """
    rng = random.Random(seed)
    new = copy.deepcopy(profile)

    # -- Floor height tuples: shift typical toward min or max ----------------
    # Ground, entresol, noble, mansard vary independently (distinct character).
    for attr in ("ground", "entresol", "noble", "mansard"):
        mn, typ, mx = getattr(new.floors, attr)
        if typ > 0:
            drift = rng.uniform(-1, 1) * amount * (mx - mn)
            new_typ = round(typ + drift, 3)
            setattr(new.floors, attr, (mn, max(mn, min(mx, new_typ)), mx))

    # Upper floors (3rd, 4th, 5th) share one drift factor so the
    # gradual taper is preserved — they all scale together.
    upper_drift = rng.uniform(-1, 1) * amount
    for attr in ("third", "fourth", "fifth"):
        mn, typ, mx = getattr(new.floors, attr)
        if typ > 0:
            drift = upper_drift * (mx - mn)
            new_typ = round(typ + drift, 3)
            setattr(new.floors, attr, (mn, max(mn, min(mx, new_typ)), mx))

    # -- Lot width tuple: shift typical toward min or max --------------------
    mn, typ, mx = new.typical_lot_width
    drift = rng.uniform(-1, 1) * amount * (mx - mn)
    new_typ = round(max(mn, min(mx, typ + drift)), 2)
    new.typical_lot_width = (mn, new_typ, mx)

    # -- Bay width tuple ----------------------------------------------------
    mn, typ, mx = new.bays.bay_width
    drift = rng.uniform(-1, 1) * amount * (mx - mn)
    new_typ = round(typ + drift, 3)
    new.bays.bay_width = (mn, max(mn, min(mx, new_typ)), mx)

    # -- Ratios: vary within sensible bounds --------------------------------
    # Drift multipliers sized so amount=0.5 produces clearly visible change.
    def _vary_ratio(current: float, max_drift: float, lo: float, hi: float) -> float:
        v = current + rng.uniform(-1, 1) * amount * max_drift
        return round(max(lo, min(hi, v)), 4)

    new.windows.width_ratio = _vary_ratio(
        new.windows.width_ratio, 0.20, 0.40, 0.80)
    new.bays.pier_ratio = _vary_ratio(
        new.bays.pier_ratio, 0.10, 0.15, 0.40)
    new.windows.noble_bordered_aspect = _vary_ratio(
        new.windows.noble_bordered_aspect, 0.6, 1.5, 3.2)
    new.windows.upper_height_ratio = _vary_ratio(
        new.windows.upper_height_ratio, 0.15, 0.50, 0.85)
    new.windows.sill_position_ratio = _vary_ratio(
        new.windows.sill_position_ratio, 0.15, 0.25, 0.65)
    new.balconies.balcony_depth = _vary_ratio(
        new.balconies.balcony_depth, 0.15, 0.20, 0.60)
    new.balconies.balconette_depth = _vary_ratio(
        new.balconies.balconette_depth, 0.12, 0.10, 0.45)

    new.name = f"{profile.name}_v{seed}"
    return new
