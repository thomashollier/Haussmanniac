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
import csv
import os
import random
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# RangeParam — unified clamped gaussian sampling
# ---------------------------------------------------------------------------

@dataclass
class RangeParam:
    """A parameter with central value, symmetric range, and gaussian spread.

    - ``typ``: central/desired value
    - ``variation``: symmetric half-range (min = typ - variation, max = typ + variation)
    - ``sigma``: normalised spread (0 = always typ, higher = wider gaussian)
    """
    typ: float = 0.0
    variation: float = 0.0
    sigma: float = 0.5

    @property
    def min(self) -> float:
        return self.typ - self.variation

    @property
    def max(self) -> float:
        return self.typ + self.variation


# ---------------------------------------------------------------------------
# Nested parameter groups
# ---------------------------------------------------------------------------

@dataclass
class FloorHeights:
    """Floor heights as RangeParam(typ, variation, sigma) in metres."""
    ground:   RangeParam = field(default_factory=lambda: RangeParam(4.0, 0.5, 0.4))
    entresol: RangeParam = field(default_factory=lambda: RangeParam(2.8, 0.2, 0.4))
    noble:    RangeParam = field(default_factory=lambda: RangeParam(3.75, 0.25, 0.4))
    third:    RangeParam = field(default_factory=lambda: RangeParam(3.4, 0.2, 0.4))
    fourth:   RangeParam = field(default_factory=lambda: RangeParam(3.15, 0.15, 0.4))
    fifth:    RangeParam = field(default_factory=lambda: RangeParam(2.9, 0.1, 0.4))
    mansard:  RangeParam = field(default_factory=lambda: RangeParam(2.2, 0.6, 0.4))


@dataclass
class BayProportions:
    """Bay and pier sizing.

    A **bay** is measured centerline-to-centerline of its piers:
    half bay-pier + bay window + half bay-pier.

    ``bay_width`` is this full repeating unit.
    ``pier_ratio`` is the fraction of ``bay_width`` occupied by the
    bay pier.  The remainder is the bay window (the opening).

    Historical Haussmann bays follow the ~1:1 plein/vide rule: the wall
    (le plein) is roughly equal to the window (le vide).  This gives
    pier_ratio ≈ 0.48–0.51 and width_ratio ≈ 0.92.

    **Edge piers** are separate — they sit between the outermost bays
    and the facade edges, absorbing all leftover width.
    """
    bay_width: RangeParam = field(default_factory=lambda: RangeParam(2.60, 0.40, 0.5))
    pier_ratio: float = 0.48           # bay pier width as fraction of bay width
    door_bay_width_ratio: float = 1.0  # door bay width as multiple of standard bay width (resolved per-building from variation)
    minimum_edge_pier: float = 1.30    # minimum edge buffer (trumeau de rive) in metres
    allow_even_bays: bool = False       # whether even bay counts (2, 4) are allowed
    # Custom bay parameters (narrow edge bays absorbing excess width)
    custom_bay_width_ratio: float = 0.55    # custom bay as fraction of standard bay width
    custom_pier_ratio: float = 0.20         # narrower piers on custom bays
    custom_bay_threshold: float = 0.75      # edge > this × bay_width triggers auto custom bay
    middle_floor_step: float = 0.93         # taper ratio between consecutive middle floors


@dataclass
class WindowProportions:
    """Window sizing relative to bay window and floor."""
    width_ratio: float = 0.92              # window frame width / bay window width
    noble_bordered_aspect: float = 2.16    # (win+border) height / (win+border) width
    upper_height_ratio: float = 0.73       # window height / floor height (3rd-4th)
    fifth_height_ratio: float = 0.71       # window height / floor height (5th)
    entresol_height_ratio: float = 0.62    # window height / floor height (entresol)
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
    shopfront_height_ratio: float = 0.75   # shopfront opening height / floor height
    residential_height_ratio: float = 0.70 # residential window top / floor height
    porte_cochere_width: float = 2.8       # porte-cochère opening width in metres


@dataclass
class OrnamentParams:
    """Ornamental element dimensions."""
    pilaster_width: float = 0.10    # metres
    pilaster_depth: float = 0.08
    pilaster_offset: float = 0.05   # gap between pilaster and bay edge


@dataclass
class BalconyParams:
    """Balcony configuration."""
    continuous_floors: list[str] = field(default_factory=lambda: ["NOBLE", "FIFTH"])
    balconette_floors: list[str] = field(default_factory=list)
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
    # Per-mansard-type angle defaults
    broken_lower_angle_deg: float = 70.0    # BROKEN lower section angle
    broken_break_pct: float = 0.85          # BROKEN break point as fraction of height
    steep_upper_angle_deg: float = 15.0     # STEEP upper cap angle
    shallow_angle_deg: float = 65.0         # SHALLOW uniform angle
    mansard_height_jitter: float = 0.10     # ±jitter on height variation


@dataclass
class CorniceParams:
    """Cornice projections and ornament."""
    roofline_projection: float = 0.40     # how far roofline cornice projects (m)
    interfloor_projection: float = 0.12   # how far inter-floor cornices project (m)
    has_modillions: bool = True            # bracket ornaments under main cornice
    has_dentils: bool = True               # dentil molding under main cornice


@dataclass
class VariationParams:
    """RNG probabilities and ranges — intentional distributions, not proportions.

    These are NOT varied by ``vary_profile()`` — they define the probability
    space for element-level choices.
    """
    # Bay count distribution
    bay_count_base_pct: float = 0.80       # probability of width-determined count
    bay_count_adjust_pct: float = 0.15     # probability of ±2 bays
    # Ground floor type distribution
    ground_floor_commercial_pct: float = 0.70
    ground_floor_mixed_pct: float = 0.15
    # Porte-cochère
    porte_center_probability: float = 0.80  # probability of center door placement
    porte_arched_probability: float = 0.50  # probability of arched (vs flat) door
    # Mansard
    mansard_short_probability: float = 0.0  # probability of short roof (0 = always tall)
    break_ratio: RangeParam = field(default_factory=lambda: RangeParam(0.825, 0.125, 1.5))
    lower_angle: RangeParam = field(default_factory=lambda: RangeParam(83.0, 5.0, 0.5))
    upper_angle: RangeParam = field(default_factory=lambda: RangeParam(45.0, 10.0, 0.5))
    # Dormers
    dormer_between_bays_pct: float = 0.50
    dormer_every_bay_pct: float = 0.17
    dormer_every_other_pct: float = 0.17
    dormer_style_swap_pct: float = 0.20
    # Elements
    railing_swap_probability: float = 0.15
    custom_bay_porthole_pct: float = 0.40
    custom_bay_narrow_pct: float = 0.25
    custom_bay_geometric_pct: float = 0.15
    # Floor stacking
    entresol_include_pct: float = 0.70      # Probability of including entresol
    # Balcony type probabilities (remainder = continuous)
    noble_balcony_none_pct: float = 0.0     # Noble floor: probability of no balcony
    noble_balcony_balconette_pct: float = 0.0  # Noble floor: probability of balconette
    fifth_balcony_none_pct: float = 0.0     # Fifth floor: probability of no balcony
    fifth_balcony_balconette_pct: float = 0.0  # Fifth floor: probability of balconette
    # Door bay width ratio (sampled per-building, written into BayProportions before solving)
    door_bay_width_ratio: RangeParam = field(default_factory=lambda: RangeParam(1.5, 0.5, 0.5))


# ---------------------------------------------------------------------------
# FacadeProfile container
# ---------------------------------------------------------------------------

@dataclass
class FacadeProfile:
    """Complete set of proportional parameters for a Haussmann facade."""
    name: str = "custom"
    typical_lot_width: RangeParam = field(default_factory=lambda: RangeParam(21.0, 3.5, 0.5))
    typical_lot_depth: float = 12.0     # default lot depth for this style
    typical_street_width: RangeParam = field(default_factory=lambda: RangeParam(12.0, 4.0, 0.4))
    has_entresol: bool = True           # whether this style includes an entresol
    chamfer_width: float = 3.0          # pan-coupé width in metres
    has_rustication: bool = True        # ground floor rusticated stonework
    floors: FloorHeights = field(default_factory=FloorHeights)
    bays: BayProportions = field(default_factory=BayProportions)
    windows: WindowProportions = field(default_factory=WindowProportions)
    ground_floor: GroundFloorProportions = field(default_factory=GroundFloorProportions)
    ornament: OrnamentParams = field(default_factory=OrnamentParams)
    balconies: BalconyParams = field(default_factory=BalconyParams)
    roof: RoofParams = field(default_factory=RoofParams)
    cornice: CorniceParams = field(default_factory=CorniceParams)
    variation: VariationParams = field(default_factory=VariationParams)


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

# Grand boulevard — tuned to historical measurements.
GRAND_BOULEVARD = FacadeProfile(
    name="grand_boulevard",
    typical_lot_width=RangeParam(21.0, 3.5, 0.5),
    typical_street_width=RangeParam(30.0, 10.0, 0.4),  # → gabarit 20.0m (mostly)
    chamfer_width=3.0,
    has_rustication=True,
    bays=BayProportions(
        bay_width=RangeParam(2.60, 0.40, 0.5),
        pier_ratio=0.48,
        door_bay_width_ratio=1.5,
        minimum_edge_pier=1.50,
    ),
    windows=WindowProportions(
        width_ratio=0.92,
        noble_bordered_aspect=2.16,
        upper_height_ratio=0.73,
        fifth_height_ratio=0.71,
        entresol_height_ratio=0.62,
    ),
    cornice=CorniceParams(
        roofline_projection=0.40,
        interfloor_projection=0.12,
        has_modillions=True,
        has_dentils=True,
    ),
    variation=VariationParams(
        ground_floor_commercial_pct=0.70,
        ground_floor_mixed_pct=0.15,
        porte_center_probability=0.80,
        dormer_style_swap_pct=0.20,
        entresol_include_pct=0.85,
        door_bay_width_ratio=RangeParam(1.5, 0.5, 0.5),
    ),
)

RESIDENTIAL = FacadeProfile(
    name="residential",
    typical_lot_width=RangeParam(15.0, 3.0, 0.5),
    typical_street_width=RangeParam(12.0, 4.0, 0.4),  # → gabarit 17.55m (mostly)
    chamfer_width=3.0,
    has_rustication=True,
    roof=RoofParams(chimney_height=1.2),
    floors=FloorHeights(
        ground=RangeParam(3.35, 0.45, 0.4),
        entresol=RangeParam(2.5, 0.3, 0.4),
        noble=RangeParam(3.2, 0.3, 0.4),
        third=RangeParam(2.95, 0.25, 0.4),
        fourth=RangeParam(2.85, 0.15, 0.4),
        fifth=RangeParam(2.7, 0.2, 0.4),
    ),
    bays=BayProportions(
        bay_width=RangeParam(2.30, 0.35, 0.5),
        pier_ratio=0.50,
        door_bay_width_ratio=1.5,
        minimum_edge_pier=1.30,
    ),
    windows=WindowProportions(
        width_ratio=0.92,
        noble_bordered_aspect=2.12,
        upper_height_ratio=0.70,
        fifth_height_ratio=0.68,
        entresol_height_ratio=0.62,
    ),
    ornament=OrnamentParams(pilaster_width=0.08),
    balconies=BalconyParams(balcony_depth=0.35),
    cornice=CorniceParams(
        roofline_projection=0.40,
        interfloor_projection=0.12,
        has_modillions=False,
        has_dentils=True,
    ),
    variation=VariationParams(
        ground_floor_commercial_pct=0.40,
        ground_floor_mixed_pct=0.30,
        porte_center_probability=0.80,
        dormer_style_swap_pct=0.20,
        door_bay_width_ratio=RangeParam(1.5, 0.5, 0.5),
    ),
)

MODEST = FacadeProfile(
    name="modest",
    typical_lot_width=RangeParam(10.0, 2.0, 0.5),
    typical_lot_depth=10.0,
    typical_street_width=RangeParam(8.0, 2.0, 0.4),   # → gabarit 14.6m or 11.7m
    has_entresol=False,
    chamfer_width=3.0,
    has_rustication=False,
    roof=RoofParams(
        mansard_height=2.65,           # tall roof (with dormers)
        mansard_height_short=1.725,    # short roof (no dormers)
        dormer_width_ratio=0.25,
        dormer_max_height=1.1,
        chimney_height=1.2,
        ridge_to_edge_ratio=2.0,       # 2:1 ridge-to-edge chimney ratio
        broken_lower_angle_deg=80.0,   # near-vertical for modest
        broken_break_pct=0.95,         # break at 95% of total height
    ),
    floors=FloorHeights(
        ground=RangeParam(3.2, 0.2, 0.4),
        entresol=RangeParam(0.0, 0.0, 0.0),  # no entresol
        noble=RangeParam(2.95, 0.15, 0.4),
        third=RangeParam(2.8, 0.1, 0.4),
        fourth=RangeParam(2.7, 0.1, 0.4),
        fifth=RangeParam(2.6, 0.1, 0.4),
        mansard=RangeParam(1.8, 0.5, 0.4),
    ),
    bays=BayProportions(
        bay_width=RangeParam(2.15, 0.45, 0.5),
        pier_ratio=0.51,
        minimum_edge_pier=1.10,
        allow_even_bays=True,
    ),
    windows=WindowProportions(
        width_ratio=0.92,
        noble_bordered_aspect=2.01,
        upper_height_ratio=0.66,
        fifth_height_ratio=0.63,
        surround_pad=0.05,
        sill_position_ratio=0.62,
        noble_max_height_ratio=0.78,
    ),
    ornament=OrnamentParams(pilaster_width=0.0),
    balconies=BalconyParams(
        balcony_depth=0.325,
        balconette_depth=0.245,
    ),
    cornice=CorniceParams(
        roofline_projection=0.40,
        interfloor_projection=0.12,
        has_modillions=False,
        has_dentils=False,
    ),
    variation=VariationParams(
        ground_floor_commercial_pct=0.30,
        ground_floor_mixed_pct=0.20,
        porte_center_probability=0.30,
        mansard_short_probability=0.50,
        dormer_style_swap_pct=0.30,
        entresol_include_pct=0.00,
        noble_balcony_none_pct=0.40,
        noble_balcony_balconette_pct=0.30,
        fifth_balcony_none_pct=0.50,
        fifth_balcony_balconette_pct=0.50,
        door_bay_width_ratio=RangeParam(1.15, 0.15, 0.5),
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
# CSV loading — makes the CSV the source of truth for profiles
# ---------------------------------------------------------------------------

# Column name → preset key mapping
_CSV_COLUMNS = {
    "grand_boulevard": "grand_boulevard",
    "residential": "residential",
    "modest": "modest",
}


def load_profiles_from_csv(csv_path: str) -> dict[str, FacadeProfile]:
    """Load all three profiles from a CSV file.

    The CSV has columns: group, parameter, unit, grand_boulevard, residential, modest.
    Tuple fields (min/typ/max) are stored as three separate rows with suffixes
    ``_min``, ``_typ``, ``_max``.  List fields use semicolon separators.

    Returns a dict of ``{name: FacadeProfile}`` ready to replace ``PRESETS``.
    """
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Collect raw values: {preset: {(group, param): str_value}}
    raw: dict[str, dict[tuple[str, str], str]] = {
        k: {} for k in _CSV_COLUMNS
    }
    for row in rows:
        group = row["group"].strip()
        param = row["parameter"].strip()
        for csv_col, preset_key in _CSV_COLUMNS.items():
            raw[preset_key][(group, param)] = row[csv_col].strip()

    profiles: dict[str, FacadeProfile] = {}
    for preset_key in _CSV_COLUMNS.values():
        profiles[preset_key] = _build_profile_from_raw(preset_key, raw[preset_key])
    return profiles


def _parse_val(s: str, unit: str = "") -> object:
    """Parse a single CSV cell into a Python value."""
    if s == "":
        return None
    if s in ("True", "true"):
        return True
    if s in ("False", "false"):
        return False
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


def _build_profile_from_raw(
    name: str,
    data: dict[tuple[str, str], str],
) -> FacadeProfile:
    """Construct a FacadeProfile from raw CSV key-value pairs."""
    def _get(group: str, param: str, default=None):
        v = data.get((group, param), "")
        if v == "":
            # Backward compat: try 'profile' if 'envelope' not found
            if group == "envelope":
                v = data.get(("profile", param), "")
            if v == "":
                return default
        return _parse_val(v)

    def _get_range(group: str, base: str, default_sigma: float = 0.5) -> RangeParam:
        typ = _get(group, f"{base}_typ", 0.0)
        var = _get(group, f"{base}_var", 0.0)
        sig = _get(group, f"{base}_sig", default_sigma)
        return RangeParam(float(typ), float(var), float(sig))

    def _get_list(group: str, param: str) -> list[str]:
        v = data.get((group, param), "")
        if not v:
            return []
        return [x.strip() for x in v.split(";") if x.strip()]

    # 'envelope' group (backward compat: falls back to 'profile')
    _env = "envelope"
    return FacadeProfile(
        name=name,
        typical_lot_width=_get_range(_env, "typical_lot_width"),
        typical_lot_depth=float(_get(_env, "typical_lot_depth", 12.0)),
        typical_street_width=_get_range(_env, "typical_street_width", 0.4),
        has_entresol=bool(_get(_env, "has_entresol", True)),
        chamfer_width=float(_get(_env, "chamfer_width", 3.0)),
        has_rustication=bool(_get(_env, "has_rustication", True)),
        floors=FloorHeights(
            ground=_get_range("floors", "ground", 0.4),
            entresol=_get_range("floors", "entresol", 0.4),
            noble=_get_range("floors", "noble", 0.4),
            third=_get_range("floors", "third", 0.4),
            fourth=_get_range("floors", "fourth", 0.4),
            fifth=_get_range("floors", "fifth", 0.4),
            mansard=_get_range("floors", "mansard", 0.4),
        ),
        bays=BayProportions(
            bay_width=_get_range("bays", "bay_width"),
            pier_ratio=float(_get("bays", "pier_ratio", 0.48)),
            door_bay_width_ratio=float(_get("bays", "door_bay_width_ratio", 1.0)),
            minimum_edge_pier=float(_get("bays", "minimum_edge_pier", 1.30)),
            allow_even_bays=bool(_get("bays", "allow_even_bays", False)),
            custom_bay_width_ratio=float(_get("bays", "custom_bay_width_ratio", 0.55)),
            custom_pier_ratio=float(_get("bays", "custom_pier_ratio", 0.20)),
            custom_bay_threshold=float(_get("bays", "custom_bay_threshold", 0.75)),
            middle_floor_step=float(_get("bays", "middle_floor_step", 0.93)),
        ),
        windows=WindowProportions(
            width_ratio=float(_get("windows", "width_ratio", 0.92)),
            noble_bordered_aspect=float(_get("windows", "noble_bordered_aspect", 2.16)),
            upper_height_ratio=float(_get("windows", "upper_height_ratio", 0.73)),
            fifth_height_ratio=float(_get("windows", "fifth_height_ratio", 0.71)),
            entresol_height_ratio=float(_get("windows", "entresol_height_ratio", 0.62)),
            surround_pad=float(_get("windows", "surround_pad", 0.05)),
            sill_position_ratio=float(_get("windows", "sill_position_ratio", 0.55)),
            noble_max_height_ratio=float(_get("windows", "noble_max_height_ratio", 0.78)),
        ),
        ground_floor=GroundFloorProportions(
            shopfront_sill=float(_get("ground_floor", "shopfront_sill", 0.15)),
            residential_sill=float(_get("ground_floor", "residential_sill", 1.0)),
            shopfront_width_ratio=float(_get("ground_floor", "shopfront_width_ratio", 0.85)),
            residential_width_ratio=float(_get("ground_floor", "residential_width_ratio", 0.40)),
            porte_cochere_height_ratio=float(_get("ground_floor", "porte_cochere_height_ratio", 0.80)),
            shopfront_height_ratio=float(_get("ground_floor", "shopfront_height_ratio", 0.75)),
            residential_height_ratio=float(_get("ground_floor", "residential_height_ratio", 0.70)),
            porte_cochere_width=float(_get("ground_floor", "porte_cochere_width", 2.8)),
        ),
        ornament=OrnamentParams(
            pilaster_width=float(_get("ornament", "pilaster_width", 0.10)),
            pilaster_depth=float(_get("ornament", "pilaster_depth", 0.08)),
            pilaster_offset=float(_get("ornament", "pilaster_offset", 0.05)),
        ),
        balconies=BalconyParams(
            continuous_floors=_get_list("balconies", "continuous_floors"),
            balconette_floors=_get_list("balconies", "balconette_floors"),
            railing_height=float(_get("balconies", "railing_height", 1.0)),
            balcony_depth=float(_get("balconies", "balcony_depth", 0.40)),
            balconette_depth=float(_get("balconies", "balconette_depth", 0.25)),
            noble_sill_at_floor=bool(_get("balconies", "noble_sill_at_floor", True)),
        ),
        roof=RoofParams(
            mansard_height=float(_get("roof", "mansard_height", 2.5)),
            mansard_height_short=float(_get("roof", "mansard_height_short", 0.0)),
            lower_angle_deg=float(_get("roof", "lower_angle_deg", 80.0)),
            upper_angle_deg=float(_get("roof", "upper_angle_deg", 20.0)),
            dormer_width_ratio=float(_get("roof", "dormer_width_ratio", 0.35)),
            dormer_max_height=float(_get("roof", "dormer_max_height", 1.6)),
            chimney_height=float(_get("roof", "chimney_height", 2.0)),
            ridge_to_edge_ratio=float(_get("roof", "ridge_to_edge_ratio", 1.0)),
            broken_lower_angle_deg=float(_get("roof", "broken_lower_angle_deg", 70.0)),
            broken_break_pct=float(_get("roof", "broken_break_pct", 0.85)),
            steep_upper_angle_deg=float(_get("roof", "steep_upper_angle_deg", 15.0)),
            shallow_angle_deg=float(_get("roof", "shallow_angle_deg", 65.0)),
            mansard_height_jitter=float(_get("roof", "mansard_height_jitter", 0.10)),
        ),
        cornice=CorniceParams(
            roofline_projection=float(_get("cornice", "roofline_projection", 0.40)),
            interfloor_projection=float(_get("cornice", "interfloor_projection", 0.12)),
            has_modillions=bool(_get("cornice", "has_modillions", True)),
            has_dentils=bool(_get("cornice", "has_dentils", True)),
        ),
        variation=VariationParams(
            bay_count_base_pct=float(_get("variation", "bay_count_base_pct", 0.80)),
            bay_count_adjust_pct=float(_get("variation", "bay_count_adjust_pct", 0.15)),
            ground_floor_commercial_pct=float(_get("variation", "ground_floor_commercial_pct", 0.70)),
            ground_floor_mixed_pct=float(_get("variation", "ground_floor_mixed_pct", 0.15)),
            porte_center_probability=float(_get("variation", "porte_center_probability", 0.80)),
            porte_arched_probability=float(_get("variation", "porte_arched_probability", 0.50)),
            mansard_short_probability=float(_get("variation", "mansard_short_probability", 0.0)),
            break_ratio=_get_range("variation", "break_ratio", 1.5),
            lower_angle=_get_range("variation", "lower_angle", 1.5),
            upper_angle=_get_range("variation", "upper_angle", 1.5),
            dormer_between_bays_pct=float(_get("variation", "dormer_between_bays_pct", 0.50)),
            dormer_every_bay_pct=float(_get("variation", "dormer_every_bay_pct", 0.17)),
            dormer_every_other_pct=float(_get("variation", "dormer_every_other_pct", 0.17)),
            dormer_style_swap_pct=float(_get("variation", "dormer_style_swap_pct", 0.20)),
            railing_swap_probability=float(_get("variation", "railing_swap_probability", 0.15)),
            custom_bay_porthole_pct=float(_get("variation", "custom_bay_porthole_pct", 0.40)),
            custom_bay_narrow_pct=float(_get("variation", "custom_bay_narrow_pct", 0.25)),
            custom_bay_geometric_pct=float(_get("variation", "custom_bay_geometric_pct", 0.15)),
            entresol_include_pct=float(_get("variation", "entresol_include_pct", 0.70)),
            noble_balcony_none_pct=float(_get("variation", "noble_balcony_none_pct", 0.0)),
            noble_balcony_balconette_pct=float(_get("variation", "noble_balcony_balconette_pct", 0.0)),
            fifth_balcony_none_pct=float(_get("variation", "fifth_balcony_none_pct", 0.0)),
            fifth_balcony_balconette_pct=float(_get("variation", "fifth_balcony_balconette_pct", 0.0)),
            door_bay_width_ratio=_get_range("variation", "door_bay_width_ratio", 0.5),
        ),
    )


def reload_presets_from_csv(csv_path: str | None = None) -> None:
    """Reload ``PRESETS`` from a CSV file.

    If *csv_path* is None, looks for ``profiles.csv`` in the project root
    (two levels up from this file).
    """
    if csv_path is None:
        csv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "profiles.csv",
        )
    if not os.path.exists(csv_path):
        return  # No CSV → keep built-in defaults
    loaded = load_profiles_from_csv(csv_path)
    PRESETS.update(loaded)


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

    # VariationParams are intentional distributions — never shifted.
    # CorniceParams, chamfer_width, has_rustication are
    # structural/stylistic — also not varied.
    # Floor heights are NOT varied here — the stacking system
    # (vary_floor_stacking) owns floor height selection.

    # -- Lot width: shift typ within range ------------------------------------
    lw = new.typical_lot_width
    drift = rng.uniform(-1, 1) * amount * lw.variation
    new_typ = round(max(lw.min, min(lw.max, lw.typ + drift)), 2)
    new.typical_lot_width = RangeParam(new_typ, lw.variation, lw.sigma)

    # -- Bay width: shift typ within range ----------------------------------
    bw = new.bays.bay_width
    drift = rng.uniform(-1, 1) * amount * bw.variation
    new_typ = round(max(bw.min, min(bw.max, bw.typ + drift)), 3)
    new.bays.bay_width = RangeParam(new_typ, bw.variation, bw.sigma)

    # -- Ratios: vary within sensible bounds --------------------------------
    # Drift multipliers sized so amount=0.5 produces clearly visible change.
    def _vary_ratio(current: float, max_drift: float, lo: float, hi: float) -> float:
        v = current + rng.uniform(-1, 1) * amount * max_drift
        return round(max(lo, min(hi, v)), 4)

    new.windows.width_ratio = _vary_ratio(
        new.windows.width_ratio, 0.06, 0.85, 0.98)
    new.bays.pier_ratio = _vary_ratio(
        new.bays.pier_ratio, 0.06, 0.43, 0.55)
    new.windows.noble_bordered_aspect = _vary_ratio(
        new.windows.noble_bordered_aspect, 0.2, 1.85, 2.30)
    new.windows.upper_height_ratio = _vary_ratio(
        new.windows.upper_height_ratio, 0.10, 0.60, 0.80)
    new.windows.sill_position_ratio = _vary_ratio(
        new.windows.sill_position_ratio, 0.15, 0.25, 0.65)
    new.balconies.balcony_depth = _vary_ratio(
        new.balconies.balcony_depth, 0.15, 0.20, 0.60)
    new.balconies.balconette_depth = _vary_ratio(
        new.balconies.balconette_depth, 0.12, 0.10, 0.45)

    new.name = f"{profile.name}_v{seed}"
    return new
