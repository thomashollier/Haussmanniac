"""Seeded randomization system for controlled architectural variation.

All randomness flows through ``random.Random(seed)`` instances — never the
global ``random`` module.  Given the same seed and the same
``BuildingConfig``, the system produces an identical IR tree.

The Variation class wraps a seeded RNG and provides methods that vary
individual architectural parameters within the bounds defined by the grammar.
"""

from __future__ import annotations

import random

from .grammar import HaussmannGrammar
from .types import (
    DormerStyle,
    FloorType,
    GroundFloorType,
    PedimentStyle,
    PorteStyle,
    RailingPattern,
    StylePreset,
    SurroundStyle,
)


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

    # -- Bay count -------------------------------------------------------------

    def vary_bay_count(
        self,
        facade_width: float,
        grammar: HaussmannGrammar,
    ) -> int:
        """Pick a bay count with probabilistic variation around the width-based count.

        Distribution centred on the width-determined base count:
        - 80%: base count (always odd)
        - 15%: ±2 bays (stays odd).  BOULEVARD favours +2, MODEST favours -2,
                RESIDENTIAL is symmetric.
        - 5%:  rare even count (±1 from base)

        All results clamped to [3, max_feasible], then passed through
        smart_bay_count() for min-edge safety.
        """
        base = grammar.compute_bay_count(facade_width, self.style)
        max_bays = grammar.max_feasible_bays(facade_width)

        roll = self.rng.random()
        if roll < 0.80:
            # 80%: width-determined count
            count = base
        elif roll < 0.95:
            # 15%: ±2 bays (stays odd), biased by style
            if self.style == StylePreset.BOULEVARD:
                count = base + 2
            elif self.style == StylePreset.MODEST:
                count = base - 2
            else:
                # RESIDENTIAL: symmetric ±2
                count = base + self.rng.choice([-2, 2])
        else:
            # 5%: rare even count (±1 from base)
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
        mn, mx = grammar.get_floor_height_range(floor_type)
        typical = grammar.get_floor_height(floor_type)
        # Bias toward the typical value with a triangular distribution
        h = self.rng.triangular(mn, mx, typical)
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

    def vary_railing_pattern(self, floor_type: FloorType) -> RailingPattern:
        """Slight variation on the railing motif."""
        base = HaussmannGrammar.get_railing_pattern(floor_type)
        # Small chance to swap classic ↔ geometric on noble/fifth floors
        if base == RailingPattern.CLASSIC and self.rng.random() < 0.15:
            return RailingPattern.GEOMETRIC
        if base == RailingPattern.GEOMETRIC and self.rng.random() < 0.15:
            return RailingPattern.CLASSIC
        return base

    # -- Dormer style ----------------------------------------------------------

    def vary_dormer_style(self, grammar: HaussmannGrammar, bay_count: int) -> DormerStyle:
        """Pick dormer style with controlled variation.

        Each style preset has a base dormer style; variation allows occasional
        swaps to related styles for variety along a street.
        """
        roof_spec = grammar.get_roof_spec(bay_count, self.style)
        base = roof_spec.dormer_style
        roll = self.rng.random()
        if base == DormerStyle.PEDIMENT_TRIANGLE and roll < 0.2:
            return DormerStyle.PEDIMENT_CURVED
        if base == DormerStyle.PEDIMENT_CURVED and roll < 0.15:
            return DormerStyle.POINTY_ROOF
        return base

    # -- Porte-cochère placement -----------------------------------------------

    def pick_porte_cochere_bay(self, bay_count: int) -> int:
        """Choose which bay becomes the porte-cochère.

        Boulevard/Residential: center door is canonical (80%), side rare.
        Modest: side door is canonical (right side default), matching the
        typical narrow Parisian lot where the entrance is to one side.
        """
        center = bay_count // 2
        if self.style == StylePreset.MODEST:
            # Modest: right side default, occasionally left
            if self.rng.random() > 0.7:
                return 0  # left side
            return bay_count - 1  # right side
        # Boulevard/Residential: center default
        if self.rng.random() > 0.8:
            return self.rng.choice([0, bay_count - 1])
        return center

    def pick_porte_style(self) -> PorteStyle:
        """Choose the porte-cochère opening style.

        50/50 split between arched and flat-top.
        """
        if self.rng.random() < 0.5:
            return PorteStyle.ARCHED
        return PorteStyle.FLAT

    # -- Chimney positioning ---------------------------------------------------

    def vary_chimney_count(self, grammar: HaussmannGrammar, bay_count: int) -> int:
        """Vary chimney count slightly around the grammar's value."""
        base = grammar.get_roof_spec(bay_count, self.style).chimney_count
        delta = self.rng.choice([-1, 0, 0, 1])  # Slight bias toward no change
        return max(2, base + delta)

    # -- Ground floor type -----------------------------------------------------

    def vary_ground_floor_type(self, has_porte_cochere: bool) -> GroundFloorType:
        """Pick a ground floor type for AUTO mode.

        Distribution by style preset:
        - BOULEVARD:    70% COMMERCIAL / 15% MIXED / 15% RESIDENTIAL
        - RESIDENTIAL:  40% COMMERCIAL / 30% MIXED / 30% RESIDENTIAL
        - MODEST:       30% COMMERCIAL / 20% MIXED / 50% RESIDENTIAL

        MIXED requires has_porte_cochere; falls back to COMMERCIAL if no door.
        """
        roll = self.rng.random()

        if self.style == StylePreset.BOULEVARD:
            if roll < 0.70:
                chosen = GroundFloorType.COMMERCIAL
            elif roll < 0.85:
                chosen = GroundFloorType.MIXED
            else:
                chosen = GroundFloorType.RESIDENTIAL
        elif self.style == StylePreset.RESIDENTIAL:
            if roll < 0.40:
                chosen = GroundFloorType.COMMERCIAL
            elif roll < 0.70:
                chosen = GroundFloorType.MIXED
            else:
                chosen = GroundFloorType.RESIDENTIAL
        else:  # MODEST
            if roll < 0.30:
                chosen = GroundFloorType.COMMERCIAL
            elif roll < 0.50:
                chosen = GroundFloorType.MIXED
            else:
                chosen = GroundFloorType.RESIDENTIAL

        # MIXED needs a porte-cochère to split around
        if chosen == GroundFloorType.MIXED and not has_porte_cochere:
            chosen = GroundFloorType.COMMERCIAL

        return chosen

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
