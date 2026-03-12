# Procedural Haussmann Building Generator

## Project Overview

A procedural system for generating buildings in the Parisian Haussmann style. A **backend-agnostic pure Python core** outputs an intermediate representation (IR) tree of typed dataclasses, consumed by backend adapters (SVG currently implemented; Blender and USD planned).

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  CORE (pure Python)              │
│  profile → grammar → generator → IR tree        │
└──────────────────┬──────────────────────────────┘
                   │  IR = tree of typed dataclasses
          ┌────────┼────────┐
          ▼        ▼        ▼
  ┌────────┐  ┌────────┐  ┌────────┐
  │  SVG   │  │Blender │  │  USD   │
  │Backend │  │Backend │  │Backend │
  └────────┘  └────────┘  └────────┘
```

### Layers

1. **Generative Core** (`core/`) — Pure Python, zero external dependencies. Contains Haussmann rules, proportions, profiles, and assembly logic. Outputs a tree of parameterized IR nodes.

2. **Backend Adapters** (`backends/`) — Consume the IR tree and produce output. `svg.py` renders 2D facade elevations. Blender/USD backends planned.

3. **Profile System** (`core/profile.py`) — All architectural proportions live in `FacadeProfile` dataclasses. Three presets: `GRAND_BOULEVARD`, `RESIDENTIAL`, `MODEST`. `vary_profile()` shifts proportions coherently by seed.

---

## Project Structure

```
haussmann/
├── CLAUDE.md              # This file — project context for Claude
├── pyproject.toml
├── core/
│   ├── __init__.py
│   ├── types.py           # IR dataclasses, enums, BuildingConfig, BuildingOverrides
│   ├── profile.py         # FacadeProfile dataclass, presets, vary_profile()
│   ├── grammar.py         # HaussmannGrammar — proportional rules from profile
│   ├── generator.py       # Top-level pipeline: config → IR tree
│   ├── facade.py          # Facade composition (bay layout, windows, ornament)
│   ├── floor.py           # Floor stacking logic
│   ├── roof.py            # Mansard roof, dormers, chimneys
│   ├── ground_floor.py    # Shopfronts, porte-cochere, rustication
│   └── variation.py       # Seeded RNG (Variation class)
├── backends/
│   ├── __init__.py
│   └── svg.py             # SVG 2D facade renderer
├── tests/
│   ├── __init__.py
│   ├── test_types.py
│   ├── test_grammar.py
│   ├── test_generator.py
│   ├── test_facade.py
│   ├── test_ground_floor.py
│   ├── test_roof.py
│   └── test_overrides.py
├── docs/
│   └── bay_layout_rules.md
├── examples/output/       # Reference SVGs and PNGs
└── output/                # Working output directory
```

---

## Haussmann Architectural Rules

### Vertical Zoning (floor types, bottom to top)

| Floor             | Typical Height | Character                                    |
|-------------------|---------------|----------------------------------------------|
| Ground (RDC)      | 3.15–3.80 m   | Commercial or residential. Rusticated stone.  |
| Entresol          | 1.70–2.30 m   | Low intermediate (omitted on MODEST).         |
| Etage Noble (2nd) | 2.88–3.40 m   | Tallest windows, richest ornament, continuous balcony. |
| 3rd Floor         | 2.83–2.95 m   | Slightly less ornate than noble floor.        |
| 4th Floor         | 2.60–2.75 m   | Simpler window surrounds.                     |
| 5th Floor         | 2.50 m        | Individual balconettes (GRAND only).          |
| Mansard           | 1.30–2.20 m   | Zinc-clad broken mansard. Dormers.            |

### Horizontal Rules

- **Bay** = half-pier + window zone + half-pier (centerline-to-centerline)
- **Interior piers**: ~48–51% of bay width (`pier_ratio`, varies by preset)
- **Window width**: ~92% of window zone (`width_ratio`)
- **Edge piers**: absorb leftover width
- **Custom bays**: when edge pier exceeds threshold, a single narrow custom bay is inserted on one side (asymmetric — placed opposite the door when off-center, random otherwise)
- **Custom bay styles**: PORTHOLE (oeil-de-boeuf, capped at 0.55m), NARROW_WINDOW, STONEWORK (rusticated panel), GEOMETRIC (diamond relief). Ground/entresol custom bays always render as STONEWORK.
- **Door bay**: 1.5x wider (GRAND_BOULEVARD + RESIDENTIAL)
- **Minimum 3 bays** enforced (solver narrows bays rather than dropping below 3)

### Balcony Rules

- **Noble**: continuous balcony spanning bay extent (pier-to-pier, not full facade width), windows touch balcony (sill=0)
- **3rd/4th**: no balconies
- **5th**: continuous balcony spanning bay extent (GRAND/RESIDENTIAL); probabilistic for MODEST
- **MODEST**: probabilistic per-building — noble: 40% none / 30% balconette / 30% continuous; 5th: 50% none / 50% balconette (capped at noble rank)

### Roof

- **Mansard type**: BROKEN (most common), STEEP (grand), SHALLOW (rear)
- **Dormers**: 6 styles (PEDIMENT_TRIANGLE, PEDIMENT_CURVED, POINTY_ROOF, OVAL, FLAT_SLOPE, ROUND_SLOPE)
- **Dormer variety**: GRAND/RESIDENTIAL swap to any of 6 styles per seed; MODEST constrained to FLAT_SLOPE/ROUND_SLOPE
- **Dormer placement**: EVERY_BAY, EVERY_OTHER, BETWEEN_BAYS, CENTER_ONLY
- **Chimneys**: edge (party-wall stacks) + ridge (between bays at mansard top)
- **Modest roofs**: 50/50 short (no dormers) / tall (with dormers)

---

## Profile System

All proportions live in `FacadeProfile` (defined in `core/profile.py`). Three built-in presets:

| Property | GRAND_BOULEVARD | RESIDENTIAL | MODEST |
|---|---|---|---|
| Typical floors | 6–7 (has entresol) | 6–7 (has entresol) | 5–6 (no entresol) |
| Lot width (RangeParam) | 21.0 ± 3.5 m | 15.0 ± 3.0 m | 10.0 ± 2.0 m |
| Bay width (RangeParam) | 2.60 ± 0.40 m | 2.30 ± 0.35 m | 2.15 ± 0.45 m |
| Pier ratio | 0.48 | 0.50 | 0.51 |
| Window width ratio | 0.92 | 0.92 | 0.92 |
| Noble bordered aspect | 2.16:1 | 2.12:1 | 2.01:1 |
| Mansard type | STEEP | BROKEN | BROKEN |
| Dormer style | PEDIMENT_CURVED | PEDIMENT_TRIANGLE | FLAT_SLOPE |

- `BuildingConfig.profile_name` overrides the style preset's default profile
- `BuildingConfig.profile_variation` (0.0–1.0) feeds `vary_profile()` for building DNA
- `Variation` class handles per-element noise (surrounds, chimneys, etc.)

---

## Override System

`BuildingOverrides` (in `core/types.py`) allows overriding individual RNG-driven decisions while keeping everything else deterministic for the seed.

### Available Overrides

| Field | Type | Controls |
|---|---|---|
| `bay_count` | `int` | Front facade bay count |
| `porte_cochere_bay` | `int` | Which bay index gets the door |
| `porte_style` | `PorteStyle` | ARCHED or FLAT |
| `ground_floor_type` | `GroundFloorType` | COMMERCIAL, RESIDENTIAL, or MIXED |
| `mansard_height` | `float` | Roof height in metres |
| `has_dormers` | `bool` | Force dormers on/off |
| `break_ratio` | `float` | Where the mansard slope breaks (0.70–0.95) |
| `lower_angle` | `float` | Steep section angle in degrees |
| `upper_angle` | `float` | Shallow section angle in degrees |
| `dormer_placement` | `str` | EVERY_BAY, EVERY_OTHER, BETWEEN_BAYS, CENTER_ONLY |
| `dormer_style` | `DormerStyle` | One of 6 dormer shapes |
| `has_custom_bays` | `bool` | Force custom edge bays on/off |
| `custom_bay_style` | `CustomBayStyle` | PORTHOLE, NARROW_WINDOW, STONEWORK, or GEOMETRIC |

### Design Principles

- All fields are `None` by default — `None` means "use the RNG value"
- Overrides are applied **after** each RNG call, so the RNG sequence is consumed identically regardless of overrides
- Downstream code uses the overridden value, keeping the building internally consistent
- `has_dormers` uses a special pattern: the conditional `vary_dormer_placement()` call is gated on the **RNG** decision (not the override) to preserve RNG sequence stability

### Usage

```python
from core.types import BuildingConfig, BuildingOverrides, DormerStyle, PorteStyle

config = BuildingConfig(
    seed=0,
    style_preset="MODEST",
    overrides=BuildingOverrides(
        has_dormers=True,
        porte_style=PorteStyle.FLAT,
        dormer_style=DormerStyle.OVAL,
    ),
)
building = generate_building(config)
```

---

## Intermediate Representation (IR)

The IR is a tree of Python dataclasses. Every node has a `transform` (position/rotation/scale) and a `node_type` string.

```python
BuildingNode          # Root
├── FacadeNode        # One per building face (S, E, W, N)
│   ├── FloorNode     # One per storey
│   │   ├── BayNode   # One per vertical bay
│   │   │   ├── WindowNode
│   │   │   ├── BalconyNode
│   │   │   ├── PilasterNode
│   │   │   └── OrnamentNode
│   │   ├── CorniceNode
│   │   └── StringCourseNode
│   └── GroundFloorNode
├── RoofNode
│   ├── MansardSlopeNode
│   ├── DormerNode
│   └── ChimneyNode
└── CornerNode         # Pan coupe (optional)
```

---

## Implementation Status

### Phase 1: Foundation -- DONE
- [x] `core/types.py` — IR dataclasses, enums, Transform, BuildingConfig, BuildingOverrides
- [x] `core/grammar.py` — HaussmannGrammar with bay solver, floor specs, roof specs
- [x] `core/profile.py` — FacadeProfile dataclass, 3 presets, vary_profile()
- [x] `tests/test_grammar.py` — Grammar validation tests

### Phase 2: Generation Pipeline -- DONE
- [x] `core/floor.py` — Floor stacking with exact grammar heights
- [x] `core/facade.py` — Bay population, balconies, pilasters, surrounds
- [x] `core/generator.py` — Full pipeline: config -> profile -> grammar -> IR tree
- [x] `core/variation.py` — Seeded RNG, vary_mansard, vary_dormer_*, vary_bay_count

### Phase 3: Roof & Ground Floor -- DONE
- [x] `core/roof.py` — Mansard slopes, dormers (6 styles, 4 placements), edge + ridge chimneys
- [x] `core/ground_floor.py` — Store types (BOUTIQUE/CAFE), porte-cochere, shopfronts

### Phase 4: SVG Backend -- DONE
- [x] `backends/svg.py` — 2D facade elevation renderer

### Phase 5: Override System -- DONE
- [x] `BuildingOverrides` dataclass with 11 override fields
- [x] Override application in generator (after RNG, before downstream)
- [x] `dormer_style_override` threaded through roof.py
- [x] `tests/test_overrides.py` — 6 tests covering on/off, style, identity, determinism

### Phase 6: Custom Bays & Variation -- DONE
- [x] Asymmetric custom bays (single-sided, opposite door)
- [x] 4 custom bay styles: PORTHOLE, NARROW_WINDOW, STONEWORK, GEOMETRIC
- [x] Porthole diameter capped at min(floor_h * 0.25, 0.55m)
- [x] Ground/entresol custom bays forced to STONEWORK
- [x] Dormer variety: all 6 styles available for GRAND/RESIDENTIAL
- [x] Continuous balconies span bay pier-to-pier extent
- [x] Probabilistic balcony types for MODEST (via BuildingDecisions)

### Future
- [ ] Blender backend (`backends/blender/`)
- [ ] USD backend (`backends/usd/`)
- [ ] LOD system
- [ ] Street-level composition (multiple buildings along a polyline)

---

## Coding Conventions

- **Python 3.10+** — `dataclasses`, `enum.Enum`, type hints everywhere
- **No geometry in core** — `core/` has zero non-stdlib imports
- **Deterministic with seed** — All RNG via `random.Random(seed)`, never global
- **Units** — Metres. Origin at front-left-ground corner. Y is up.
- **Naming** — snake_case everywhere. IR node classes end in `Node`.
- **Testing** — Every core module has a corresponding test file. Test IR structure, not geometry.

---

## Style Presets

- **`BOULEVARD`** — Rich ornamentation, 7 floors, entresol, noble floor with pilasters. (Bd Haussmann, Av de l'Opera)
- **`RESIDENTIAL`** — Moderate ornament, 6 floors, entresol, simpler surrounds. (Typical side street)
- **`MODEST`** — Minimal ornament, 5 floors, no entresol, wider piers, squatter windows. (Back streets, upper arrondissements)

---

## Quick Start

```python
from core.generator import generate_building
from core.types import BuildingConfig

# Generate with defaults (RESIDENTIAL, seed 42)
building = generate_building(BuildingConfig())

# Modest building, seed 0, with overrides
from core.types import BuildingOverrides, PorteStyle
config = BuildingConfig(
    seed=0,
    style_preset="MODEST",
    overrides=BuildingOverrides(has_dormers=True, porte_style=PorteStyle.FLAT),
)
building = generate_building(config)

# Render to SVG
from backends.svg import render_svg
svg = render_svg(building)
```

### Running Tests

```bash
python -m pytest tests/ -x
```
