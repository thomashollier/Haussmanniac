"""Element-level variation system.

Provides a common context and dispatch mechanism for architectural element
variants (cafes, storefronts, doors, balconies, awnings).  Each element
category has multiple named styles that are selected per-building.

The ``ElementContext`` bundles all information relevant to the "cell" being
built.  The ``ElementPalette`` records per-building style choices made once
by ``vary_element_palette()`` and carried through the pipeline.

Extending: add a new enum value, then add a matching renderer in
``backends/svg_elements.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from random import Random
from typing import Optional


# ── Style enums ──────────────────────────────────────────────────────


class CafeStyle(Enum):
    """Per-bay cafe window treatment."""
    BISTRO_MULLIONS = auto()   # Glass panels with thin vertical mullions + transom
    ARCHED = auto()            # Semicircular arch tops with keystone
    RECESSED = auto()          # Deep shadow recess framing simple glass
    KNEE_WALL = auto()         # Low stone wall at bottom, tall glass above
    PILASTER_FRAME = auto()    # Stone pilasters between bays, lintel band
    # Open terrace layouts (glass to ground, spanning across bays)
    FULL_SPAN = auto()         # Full-span glass, thin metal mullions replace piers
    KICKPLATE_GLASS = auto()   # 15cm stone base, full glass above
    NARROW_PIERS = auto()      # Thin stone piers between glass bays
    OPEN_TERRACE = auto()      # Some panels open, some glazed


class StorefrontStyle(Enum):
    """Boutique / small-shop window treatment."""
    CLASSIC = auto()           # Traditional signage band + mullioned display
    DISPLAY_WINDOW = auto()    # Large plate glass with thin frame
    RECESSED_ENTRY = auto()    # Entry set back from facade plane
    PILASTERED = auto()        # Stone pilasters framing each bay
    MINIMAL = auto()           # Simple opening, minimal frame


class DoorStyle(Enum):
    """Porte-cochère / building entrance treatment."""
    ARCHED_CLASSIC = auto()    # Traditional stone arch with keystone
    FLAT_PANEL = auto()        # Flat lintel with wooden paneled door
    DOUBLE_LEAF = auto()       # Double doors with glass upper panels
    GLASS_TOPPED = auto()      # Solid lower half, fanlight above
    ORNATE_CARVED = auto()     # Heavy carved wood with iron studs


class BalconyStyle(Enum):
    """Wrought-iron railing motif for balconies and balconettes."""
    CLASSIC_SCROLL = auto()    # Ornate scrollwork (Haussmann standard)
    GEOMETRIC = auto()         # Rectilinear Art Deco-influenced
    SIMPLE_BARS = auto()       # Vertical bars only
    ART_NOUVEAU = auto()       # Organic flowing curves
    GREEK_KEY = auto()         # Meander pattern


class AwningStyle(Enum):
    """Awning/canopy treatment above commercial ground floors."""
    NONE = auto()              # No awning
    FLAT_BOX = auto()          # Flat rectangular box (with optional text)
    RETRACTABLE = auto()       # Angled fabric canopy
    SCALLOPED = auto()         # Curved scalloped valance
    STRIPED = auto()           # Striped retractable


# ── Element context ──────────────────────────────────────────────────


@dataclass
class ElementContext:
    """All information available when building a single element cell.

    Gathered by the dispatcher before handing off to the element renderer.
    Every element variant receives the same context — use what you need.
    """
    # Geometry
    width: float = 0.0            # Bay width (metres)
    height: float = 0.0           # Floor height (metres)

    # Building identity
    style_preset: str = "RESIDENTIAL"   # BOULEVARD / RESIDENTIAL / MODEST
    floor_type: str = "GROUND"          # FloorType name
    ornament_level: int = 2             # 0=NONE, 1=SIMPLE, 2=MODERATE, 3=RICH

    # Position context
    bay_index: int = 0
    bay_count: int = 1
    is_front: bool = True

    # Element-specific
    is_store_entry: bool = False

    # Deterministic sub-variation
    seed: int = 0

    # Future extensions (prepared but not yet used)
    # era: str = "middle"  # early / middle / late Haussmann


# ── Element palette (per-building style choices) ─────────────────────


@dataclass
class ElementPalette:
    """Per-building element style selections.

    Chosen once per building by ``vary_element_palette()`` and carried
    through the pipeline.  Every commercial bay, door, and balcony on the
    building uses these styles for visual consistency.
    """
    cafe_style: CafeStyle = CafeStyle.BISTRO_MULLIONS
    storefront_style: StorefrontStyle = StorefrontStyle.CLASSIC
    door_style: DoorStyle = DoorStyle.ARCHED_CLASSIC
    balcony_style: BalconyStyle = BalconyStyle.CLASSIC_SCROLL
    awning_style: AwningStyle = AwningStyle.NONE
    has_awning: bool = False


# ── Style weights per preset ─────────────────────────────────────────

# Each dict maps style_preset → list of weights (same order as enum values).

_CAFE_WEIGHTS: dict[str, list[float]] = {
    #                bistro arch  recess knee  pilas  full  kick  piers open
    "BOULEVARD":   [0.12, 0.18, 0.08, 0.15, 0.22, 0.08, 0.07, 0.05, 0.05],
    "RESIDENTIAL": [0.22, 0.12, 0.15, 0.15, 0.12, 0.08, 0.06, 0.05, 0.05],
    "MODEST":      [0.20, 0.08, 0.18, 0.18, 0.10, 0.08, 0.06, 0.06, 0.06],
}

_STOREFRONT_WEIGHTS: dict[str, list[float]] = {
    "BOULEVARD":   [0.20, 0.20, 0.15, 0.30, 0.15],
    "RESIDENTIAL": [0.30, 0.25, 0.20, 0.10, 0.15],
    "MODEST":      [0.15, 0.20, 0.15, 0.10, 0.40],
}

_DOOR_WEIGHTS: dict[str, list[float]] = {
    "BOULEVARD":   [0.30, 0.10, 0.20, 0.15, 0.25],
    "RESIDENTIAL": [0.25, 0.25, 0.20, 0.15, 0.15],
    "MODEST":      [0.10, 0.35, 0.20, 0.20, 0.15],
}

_BALCONY_WEIGHTS: dict[str, list[float]] = {
    "BOULEVARD":   [0.35, 0.15, 0.05, 0.25, 0.20],
    "RESIDENTIAL": [0.25, 0.25, 0.15, 0.15, 0.20],
    "MODEST":      [0.10, 0.30, 0.40, 0.10, 0.10],
}

_AWNING_WEIGHTS: list[float] = [0.30, 0.30, 0.15, 0.25]  # flat, retract, scallop, stripe

_AWNING_PROBABILITY: dict[str, float] = {
    "BOULEVARD":   0.30,
    "RESIDENTIAL": 0.30,
    "MODEST":      0.30,
}


def _weighted_pick(rng: Random, items: list, weights: list[float]):
    """Pick an item using cumulative weights."""
    r = rng.random()
    cumulative = 0.0
    for item, w in zip(items, weights):
        cumulative += w
        if r < cumulative:
            return item
    return items[-1]


def vary_element_palette(rng: Random, style_preset: str) -> ElementPalette:
    """Pick element styles for a building based on style and RNG.

    Consumes exactly 6 RNG calls (cafe, storefront, door, balcony,
    has_awning, awning_style) for sequence stability.
    """
    preset = style_preset if style_preset in _CAFE_WEIGHTS else "RESIDENTIAL"

    cafe = _weighted_pick(rng, list(CafeStyle), _CAFE_WEIGHTS[preset])
    storefront = _weighted_pick(rng, list(StorefrontStyle), _STOREFRONT_WEIGHTS[preset])
    door = _weighted_pick(rng, list(DoorStyle), _DOOR_WEIGHTS[preset])
    balcony = _weighted_pick(rng, list(BalconyStyle), _BALCONY_WEIGHTS[preset])

    has_awning = rng.random() < _AWNING_PROBABILITY.get(preset, 0.30)
    awning_styles = [s for s in AwningStyle if s != AwningStyle.NONE]
    awning = _weighted_pick(rng, awning_styles, _AWNING_WEIGHTS)
    if not has_awning:
        awning = AwningStyle.NONE

    return ElementPalette(
        cafe_style=cafe,
        storefront_style=storefront,
        door_style=door,
        balcony_style=balcony,
        awning_style=awning,
        has_awning=has_awning,
    )
