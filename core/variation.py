"""Seeded randomization system for controlled architectural variation.

All randomness flows through ``random.Random(seed)`` instances — never the
global ``random`` module.  Given the same seed and the same
``BuildingConfig``, the system produces an identical IR tree.

The Variation class wraps a seeded RNG and provides methods that vary
individual architectural parameters within the bounds defined by the grammar.
"""

from __future__ import annotations

import hashlib
import random
from statistics import NormalDist

from .grammar import HaussmannGrammar, compute_gabarit
from .profile import RangeParam

_NORM = NormalDist(0, 1)
from .types import (
    BalconyType,
    CustomBayStyle,
    DormerStyle,
    FloorType,
    GroundFloorType,
    PedimentStyle,
    PorteStyle,
    RailingPattern,
    StylePreset,
    SurroundStyle,
)

# Balcony prominence ranking for hierarchy cap
_BALCONY_RANK: dict[BalconyType, int] = {
    BalconyType.NONE: 0,
    BalconyType.BALCONETTE: 1,
    BalconyType.CONTINUOUS: 2,
}


class Variation:
    """Controlled randomization driven by a single seed.

    Usage::

        v = Variation(seed=42, style=StylePreset.BOULEVARD)
        height = v.vary_floor_height(FloorType.NOBLE, grammar)
    """

    def __init__(self, seed: int, style: StylePreset = StylePreset.RESIDENTIAL) -> None:
        self.seed = seed
        self.style = style
        self.rng = random.Random(seed)

    def derive_child_rng(self, component: str) -> "Variation":
        """Create an independent child Variation for a pipeline stage.

        The child seed is deterministically derived from the master seed
        and a component name.  Each child has its own RNG stream —
        adding calls to one stage can never shift another.
        """
        key = f"{self.seed}:{component}".encode()
        child_seed = int.from_bytes(hashlib.sha256(key).digest()[:4], "little")
        return Variation(seed=child_seed, style=self.style)

    # -- Truncated normal sampling ---------------------------------------------

    def sample_range(self, rp: RangeParam) -> float:
        """Truncated normal sample from a RangeParam. Exactly 1 RNG call."""
        u = self.rng.random()
        if rp.variation == 0 or rp.sigma == 0:
            return rp.typ
        effective_sigma = rp.sigma * rp.variation
        a = (rp.min - rp.typ) / effective_sigma
        b = (rp.max - rp.typ) / effective_sigma
        cdf_a = _NORM.cdf(a)
        cdf_b = _NORM.cdf(b)
        u_mapped = cdf_a + u * (cdf_b - cdf_a)
        u_mapped = max(1e-10, min(1 - 1e-10, u_mapped))
        z = _NORM.inv_cdf(u_mapped)
        return rp.typ + z * effective_sigma

    # -- Bay count -------------------------------------------------------------

    def vary_bay_count(
        self,
        facade_width: float,
        grammar: HaussmannGrammar,
    ) -> int:
        """Pick a bay count with probabilistic variation around the width-based count.

        Distribution centred on the width-determined base count:
        - base_pct: base count (always odd)
        - adjust_pct: ±2 bays (stays odd).  BOULEVARD favours +2, MODEST
          favours -2, RESIDENTIAL is symmetric.
        - remaining: rare even count (±1 from base)

        All results clamped to [3, max_feasible], then passed through
        smart_bay_count() for min-edge safety.
        """
        vp = grammar.profile.variation
        base = grammar.compute_bay_count(facade_width, self.style)
        max_bays = grammar.max_feasible_bays(facade_width)

        roll = self.rng.random()
        if roll < vp.bay_count_base_pct:
            count = base
        elif roll < vp.bay_count_base_pct + vp.bay_count_adjust_pct:
            if self.style == StylePreset.BOULEVARD:
                count = base + 2
            elif self.style == StylePreset.MODEST:
                count = base - 2
            else:
                count = base + self.rng.choice([-2, 2])
        else:
            count = base + self.rng.choice([-1, 1])

        count = max(3, min(count, max_bays))
        return grammar.smart_bay_count(facade_width, count, self.style)

    # -- Floor heights ---------------------------------------------------------

    def vary_floor_height(
        self,
        floor_type: FloorType,
        grammar: HaussmannGrammar,
    ) -> float:
        """Return a floor height varied within the grammar's valid range."""
        rp = grammar.get_floor_range(floor_type)
        h = self.sample_range(rp)
        return round(h, 3)

    def vary_middle_floor_height(self, base_height: float) -> float:
        """Small perturbation around a budget-computed middle floor height.

        The base height already varies building-to-building (because the
        fixed floor heights that feed into the budget are varied).  This
        adds a tiny jitter so adjacent middle floors aren't perfectly
        mechanical.
        """
        delta = self.rng.uniform(-0.05, 0.05)
        return round(base_height + delta, 3)

    # -- Pediment style --------------------------------------------------------

    def vary_pediment(
        self,
        floor_type: FloorType,
        grammar: HaussmannGrammar,
    ) -> PedimentStyle:
        """Pick a pediment style with variation depending on floor and style.

        Noble floors always get a pediment; the *shape* varies.
        Third floors may or may not get one.  Others never do.
        """
        if floor_type == FloorType.NOBLE:
            if self.style == StylePreset.BOULEVARD:
                # Rich buildings: mix of triangular and segmental
                return self.rng.choice([
                    PedimentStyle.TRIANGULAR,
                    PedimentStyle.SEGMENTAL,
                ])
            return PedimentStyle.TRIANGULAR

        if floor_type == FloorType.THIRD:
            if self.style in (StylePreset.BOULEVARD, StylePreset.RESIDENTIAL):
                # 50/50 segmental or none
                return self.rng.choice([PedimentStyle.SEGMENTAL, PedimentStyle.NONE])
            return PedimentStyle.NONE

        return PedimentStyle.NONE

    # -- Surround style --------------------------------------------------------

    def vary_surround(
        self,
        floor_type: FloorType,
        grammar: HaussmannGrammar,
    ) -> SurroundStyle:
        """Pick a window surround style with slight variation."""
        base = grammar.get_ornament_level(floor_type)
        spec = grammar.get_window_spec(floor_type, base, 1.3, 3.0)
        base_style = spec.surround_style

        # Consume the RNG to keep seed sequence stable
        self.rng.random()
        return base_style

    # -- Railing pattern -------------------------------------------------------

    def vary_railing_pattern(
        self,
        floor_type: FloorType,
        grammar: HaussmannGrammar | None = None,
    ) -> RailingPattern:
        """Slight variation on the railing motif."""
        swap_prob = 0.15
        if grammar is not None:
            swap_prob = grammar.profile.variation.railing_swap_probability
        base = HaussmannGrammar.get_railing_pattern(floor_type)
        if base == RailingPattern.CLASSIC and self.rng.random() < swap_prob:
            return RailingPattern.GEOMETRIC
        if base == RailingPattern.GEOMETRIC and self.rng.random() < swap_prob:
            return RailingPattern.CLASSIC
        return base

    # -- Mansard height --------------------------------------------------------

    def vary_mansard(self, grammar: HaussmannGrammar) -> tuple[float, bool, float, float, float]:
        """Pick mansard height, dormers, break ratio, and angles.

        Returns ``(height, has_dormers, break_ratio, lower_angle_deg, upper_angle_deg)``.

        Always samples break ratio, lower/upper angles, and mansard height
        (5 RNG calls for sequence stability).  When mansard_height_short > 0
        (e.g. modest), the short/tall coin flip determines dormers and which
        height base to use.
        """
        rp = grammar.profile.roof
        vp = grammar.profile.variation
        jitter = rp.mansard_height_jitter

        # Always sample these (3 RNG calls)
        break_ratio = round(self.sample_range(vp.break_ratio), 3)
        lower_angle = round(min(self.sample_range(vp.lower_angle), 88.0), 1)
        upper_angle = round(self.sample_range(vp.upper_angle), 1)

        # Short/tall coin flip (1 RNG call — consumed even when short=0)
        short_roll = self.rng.random()

        # Mansard height with jitter (1 RNG call)
        if rp.mansard_height_short > 0 and short_roll < vp.mansard_short_probability:
            base_h = rp.mansard_height_short
            has_dormers = False
        else:
            base_h = rp.mansard_height
            has_dormers = True
        h = self.rng.uniform(base_h * (1 - jitter), base_h * (1 + jitter))

        return (round(h, 3), has_dormers, break_ratio, lower_angle, upper_angle)

    # -- Dormer placement ------------------------------------------------------

    def vary_dormer_placement(
        self,
        grammar: HaussmannGrammar | None = None,
    ) -> str:
        """Pick a dormer placement rule.

        - ``EVERY_BAY``:    one dormer centered above each bay
        - ``EVERY_OTHER``:  one dormer above every other bay
        - ``BETWEEN_BAYS``: one dormer at each pier gap between adjacent bays
        - ``CENTER_ONLY``:  one dormer above the center bay only

        Probabilities read from variation params.
        """
        if grammar is not None:
            vp = grammar.profile.variation
            between = vp.dormer_between_bays_pct
            every = vp.dormer_every_bay_pct
            other = vp.dormer_every_other_pct
        else:
            between, every, other = 0.50, 0.17, 0.17
        roll = self.rng.random()
        if roll < between:
            return "BETWEEN_BAYS"
        elif roll < between + every:
            return "EVERY_BAY"
        elif roll < between + every + other:
            return "EVERY_OTHER"
        else:
            return "CENTER_ONLY"

    # -- Dormer style ----------------------------------------------------------

    def vary_dormer_style(self, grammar: HaussmannGrammar, bay_count: int) -> DormerStyle:
        """Pick dormer style with uniform probability.

        BOULEVARD/RESIDENTIAL: equal chance of any of 6 styles.
        MODEST: equal chance of FLAT_SLOPE or ROUND_SLOPE.
        Always consumes 1 RNG call.
        """
        if self.style == StylePreset.MODEST:
            return self.rng.choice([DormerStyle.FLAT_SLOPE, DormerStyle.ROUND_SLOPE])
        return self.rng.choice(list(DormerStyle))

    # -- Custom bay style ------------------------------------------------------

    def vary_custom_bay_style(
        self,
        grammar: HaussmannGrammar | None = None,
    ) -> CustomBayStyle:
        """Pick custom bay window treatment.

        Four styles with probabilities from variation params.
        Remainder after porthole + narrow + geometric = STONEWORK.
        """
        if grammar is not None:
            vp = grammar.profile.variation
            porthole = vp.custom_bay_porthole_pct
            narrow = vp.custom_bay_narrow_pct
            geometric = vp.custom_bay_geometric_pct
        else:
            porthole, narrow, geometric = 0.40, 0.25, 0.15
        roll = self.rng.random()
        if roll < porthole:
            return CustomBayStyle.PORTHOLE
        elif roll < porthole + narrow:
            return CustomBayStyle.NARROW_WINDOW
        elif roll < porthole + narrow + geometric:
            return CustomBayStyle.GEOMETRIC
        else:
            return CustomBayStyle.STONEWORK

    def vary_custom_bay_side(
        self,
        door_bay_index: int,
        bay_count: int,
    ) -> int:
        """Pick which side gets a custom bay (0=left, 1=right).

        Always consumes 1 RNG call.  When door is off-center,
        custom bay goes on the opposite side.  Otherwise random.
        """
        roll = self.rng.random()
        if door_bay_index >= 0 and bay_count > 0:
            center = bay_count // 2
            if door_bay_index < center:
                return 1   # door on left → custom on right
            elif door_bay_index > center:
                return 0   # door on right → custom on left
        # Center door or no door: coin flip
        return 0 if roll < 0.5 else 1

    # -- Porte-cochère placement -----------------------------------------------

    def pick_porte_cochere_bay(
        self,
        bay_count: int,
        grammar: HaussmannGrammar | None = None,
    ) -> int:
        """Choose which bay becomes the porte-cochère.

        Center probability read from variation params.
        """
        center_prob = 0.80
        if grammar is not None:
            center_prob = grammar.profile.variation.porte_center_probability
        center = bay_count // 2
        if center_prob < 0.5:
            # Low center probability → side door style (modest)
            if self.rng.random() > (1 - center_prob):
                return 0  # left side
            return bay_count - 1  # right side
        # High center probability → center door style
        if self.rng.random() > center_prob:
            return self.rng.choice([0, bay_count - 1])
        return center

    def pick_porte_style(
        self,
        grammar: HaussmannGrammar | None = None,
    ) -> PorteStyle:
        """Choose the porte-cochère opening style.

        Arched probability read from variation params.
        """
        arched_prob = 0.50
        if grammar is not None:
            arched_prob = grammar.profile.variation.porte_arched_probability
        if self.rng.random() < arched_prob:
            return PorteStyle.ARCHED
        return PorteStyle.FLAT

    # -- Chimney positioning ---------------------------------------------------

    def vary_chimney_count(self, grammar: HaussmannGrammar, bay_count: int) -> int:
        """Vary chimney count slightly around the grammar's value."""
        base = grammar.get_roof_spec(bay_count, self.style).chimney_count
        delta = self.rng.choice([-1, 0, 0, 1])  # Slight bias toward no change
        return max(2, base + delta)

    # -- Ground floor type -----------------------------------------------------

    def vary_ground_floor_type(
        self,
        has_porte_cochere: bool,
        grammar: HaussmannGrammar | None = None,
    ) -> GroundFloorType:
        """Pick a ground floor type for AUTO mode.

        Probabilities read from variation params.
        MIXED requires has_porte_cochere; falls back to COMMERCIAL if no door.
        """
        if grammar is not None:
            vp = grammar.profile.variation
            commercial_pct = vp.ground_floor_commercial_pct
            mixed_pct = vp.ground_floor_mixed_pct
        else:
            # Fallback to BOULEVARD defaults
            commercial_pct = 0.70
            mixed_pct = 0.15

        roll = self.rng.random()
        if roll < commercial_pct:
            chosen = GroundFloorType.COMMERCIAL
        elif roll < commercial_pct + mixed_pct:
            chosen = GroundFloorType.MIXED
        else:
            chosen = GroundFloorType.RESIDENTIAL

        # MIXED needs a porte-cochère to split around
        if chosen == GroundFloorType.MIXED and not has_porte_cochere:
            chosen = GroundFloorType.COMMERCIAL

        return chosen

    # -- Floor stacking ---------------------------------------------------------

    def vary_floor_stacking(
        self,
        grammar: HaussmannGrammar,
        gabarit: float | None,
        street_width_range: RangeParam | None = None,
        has_entresol_override: bool | None = None,
    ) -> tuple[int, bool, dict[FloorType, float]]:
        """Stack floors bottom-up within gabarit budget.

        Returns ``(num_floors, has_entresol, effective_heights)``.
        Always consumes exactly 8 RNG calls for sequence stability
        (1 street width + 6 floor heights + 1 entresol roll).

        When *gabarit* is provided (caller computed it from an explicit
        ``config.street_width``), the street-width RNG call is consumed
        as a no-op.  When *gabarit* is None, a street width is picked
        from *street_width_range* via truncated normal sampling and
        gabarit is computed internally.
        """
        # 1. Pick street width (always 1 RNG call)
        swr = street_width_range or RangeParam(12.0, 4.0, 0.4)
        street_roll = self.sample_range(swr)
        if gabarit is None:
            gabarit = compute_gabarit(street_roll)

        # 2. Pick effective height for each of 6 floor types (always 6 RNG calls)
        floor_order = [
            FloorType.GROUND, FloorType.ENTRESOL, FloorType.NOBLE,
            FloorType.THIRD, FloorType.FOURTH, FloorType.FIFTH,
        ]
        effective: dict[FloorType, float] = {}
        for ft in floor_order:
            rp = grammar.get_floor_range(ft)
            h = self.sample_range(rp)
            effective[ft] = round(h, 3)

        # 3. Roll entresol inclusion (always 1 RNG call)
        entresol_roll = self.rng.random()
        if has_entresol_override is not None:
            include_entresol = has_entresol_override
        elif grammar.profile.has_entresol:
            include_entresol = entresol_roll < grammar.profile.variation.entresol_include_pct
        else:
            include_entresol = False

        # 4. Stack bottom-up against gabarit budget (small epsilon for float rounding)
        _EPS = 1e-9
        budget = gabarit
        floors_included: list[FloorType] = []

        # GROUND — mandatory
        budget -= effective[FloorType.GROUND]
        floors_included.append(FloorType.GROUND)

        # ENTRESOL — if included and fits
        if include_entresol and effective[FloorType.ENTRESOL] <= budget + _EPS:
            budget -= effective[FloorType.ENTRESOL]
            floors_included.append(FloorType.ENTRESOL)
        else:
            include_entresol = False

        # NOBLE, THIRD, FOURTH, FIFTH — if fits
        for ft in (FloorType.NOBLE, FloorType.THIRD, FloorType.FOURTH, FloorType.FIFTH):
            if effective[ft] <= budget + _EPS:
                budget -= effective[ft]
                floors_included.append(ft)

        # MANSARD always on top (not counted against gabarit)
        floors_included.append(FloorType.MANSARD)
        num_floors = len(floors_included)

        return num_floors, include_entresol, effective

    # -- Balcony types ---------------------------------------------------------

    def vary_balcony_types(
        self,
        grammar: HaussmannGrammar,
    ) -> dict[FloorType, BalconyType]:
        """Pick balcony type for noble and fifth floors.

        Always consumes exactly 2 RNG calls (1 noble + 1 fifth).
        Fifth floor is capped at noble's prominence rank.

        When all probabilities are 0 (GRAND/RESIDENTIAL defaults),
        both floors get CONTINUOUS — unchanged from prior behaviour.
        """
        vp = grammar.profile.variation

        # Noble floor roll
        noble_roll = self.rng.random()
        if noble_roll < vp.noble_balcony_none_pct:
            noble = BalconyType.NONE
        elif noble_roll < vp.noble_balcony_none_pct + vp.noble_balcony_balconette_pct:
            noble = BalconyType.BALCONETTE
        else:
            noble = BalconyType.CONTINUOUS

        # Fifth floor roll
        fifth_roll = self.rng.random()
        if fifth_roll < vp.fifth_balcony_none_pct:
            fifth = BalconyType.NONE
        elif fifth_roll < vp.fifth_balcony_none_pct + vp.fifth_balcony_balconette_pct:
            fifth = BalconyType.BALCONETTE
        else:
            fifth = BalconyType.CONTINUOUS

        # Hierarchy cap: fifth never exceeds noble
        if _BALCONY_RANK[fifth] > _BALCONY_RANK[noble]:
            fifth = noble

        return {FloorType.NOBLE: noble, FloorType.FIFTH: fifth}

    # -- Boolean coin flips ----------------------------------------------------

    def coin(self, probability: float = 0.5) -> bool:
        """Biased coin flip."""
        return self.rng.random() < probability

    # -- Uniform helpers -------------------------------------------------------

    def uniform(self, low: float, high: float) -> float:
        """Uniform random float in [low, high]."""
        return round(self.rng.uniform(low, high), 3)

    def choice(self, options: list) -> object:
        """Random choice from a list."""
        return self.rng.choice(options)
