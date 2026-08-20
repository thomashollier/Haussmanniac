# Procedural Haussmann Building Generator

## Project Overview

A procedural system for generating buildings in the Parisian Haussmann style. A **backend-agnostic pure Python core** outputs an intermediate representation (IR) tree of typed dataclasses, consumed by backend adapters (SVG currently implemented; Blender and USD planned).

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  CORE (pure Python)              │
│  reglement → profile → grammar → generator → IR │
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

0. **Regulation** (`core/reglement.py`) — The building code as data. Street width and the decree in force determine the cornice line and the shape of the roof above it; a separate ordinance determines where balconies may go. Everything vertical derives from here rather than being sampled.

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
│   ├── reglement.py       # Era, Reglement, GabaritEnvelope, balcony + oriel rules
│   ├── types.py           # IR dataclasses, enums, BuildingConfig, BuildingOverrides
│   ├── profile.py         # FacadeProfile dataclass, presets, vary_profile()
│   ├── grammar.py         # HaussmannGrammar — proportional rules from profile
│   ├── generator.py       # Top-level pipeline: config → IR tree
│   ├── facade.py          # Facade composition (bay layout, windows, ornament)
│   ├── floor.py           # Floor stacking logic
│   ├── oriel.py           # Projecting bay windows (1882 onward)
│   ├── roof.py            # Mansard roof, dormers, chimneys
│   ├── ground_floor.py    # Shopfronts, porte-cochere, rustication
│   └── variation.py       # Seeded RNG (Variation class)
├── backends/
│   ├── __init__.py
│   └── svg.py             # SVG 2D facade renderer
├── tests/
│   ├── __init__.py
│   ├── test_reglement.py  # Height tables, envelope geometry, balcony rule
│   ├── test_oriel.py      # Oriel legality, placement, and geometry
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

## The Regulatory Model

The haussmannian building is the residue of a legal envelope, not a chosen style. Two inputs — **street width** and **the decree in force** — fix the whole vertical composition. `core/reglement.py` encodes this; the generator derives from it instead of sampling.

### Eras

`Era` selects which decree applies. Set it directly (`era="ALPHAND"`) or give a `year` and let it resolve (`year=1868`).

| Era | Decree | Facade height by street width | Comble envelope |
|---|---|---|---|
| `ROYAL` (1784–1859) | Déclaration royale 1783 / lettres patentes 1784 | <7.80→11.70, <9.75→14.62, else 17.55 | 45° diagonal from the eaves |
| `SECOND_EMPIRE` (1859–1884) | Règlement 27 juillet 1859 | as above, **+ >20 m → 20.00** | 45° diagonal |
| `ALPHAND` (1884–1902) | Décret 23 juillet 1884 | 12 / 15 / 18 / 20 | **circular arc**, radius by street width |
| `BONNIER` (1902–1914) | Décret 13 août 1902 | 12 / 15 / 18 / 20 | **eighth-of-circle arc, then a 45° oblique** |

**Default is `SECOND_EMPIRE`** — Haussmann's own period.

### The comble is not a free parameter

Before 1884 the roof had to be inscribed below a 45° diagonal springing from the eaves, so a near-vertical mansard was *illegal*. The 1884 decree replaced that diagonal with a circular arc — vertical at the eaves, flattening over the top — which is what let builders add a storey set back from the facade, and where the familiar steep Parisian silhouette comes from. 20 m of facade plus an 8.50 m comble is the documented 28.50 m ceiling, which `compute_envelope` reproduces exactly.

`GabaritEnvelope.slope_profile()` returns the silhouette as `(inset, height)` points; the front `MansardSlopeNode` carries it in `envelope_profile` and backends draw that polyline directly. `mansard_angles()` gives the same curve as the classic `(lower, upper, break_pct)` triple.

The decree sets a ceiling, not a target. Two builder-side constraints bring the comble back to what was actually built: `RoofParams.roof_fill` (fraction of the legal maximum) and `RoofParams.comble_storeys` (how many floors of chambres de bonne the programme needs). `legal_ridge_height` records what the decree would have allowed.

### Balconies follow the 1823 ordinance

Balconies may project at most **0.80 m** and only at **6 m or more** above the pavement — never relaxed under Haussmann, which is exactly why these facades have so little relief and run to *balcons filants*. `balcony_rule()` takes the floor levels and returns which floors carry them:

- The **first floor clearing 6 m** takes the lower continuous balcony. With an entresol that lands on the étage noble; without one it moves up a storey — which is why modest buildings have their balcony higher, and it now falls out of the rule rather than being faked with probabilities.
- The **topmost eligible floor** takes the second continuous line.
- **Individual balconettes** on the floors between appear only under `ALPHAND`/`BONNIER`, matching the balcons individuels of the late period.

Balcony depths are clamped to the 0.80 m legal maximum in `facade.py`.

### Oriels — the 1882 relaxation

Paris banned projections over the street from the edicts of **1607** and **1667** until the decree of **22 July 1882**. That ban is why the haussmannian facade is flat, and it's the same instinct as the 0.80 m balcony cap. An oriel is therefore the clearest date-stamp on a Paris facade: a flat wall reads pre-1882, a rippling one reads Belle Époque.

`core/oriel.py` builds them; `oriel_rule()` in `reglement.py` decides whether they're allowed and within what limits:

| Provision | Rule |
|---|---|
| Earliest date | 1882 (`ALPHAND` onward) — never on `ROYAL`/`SECOND_EMPIRE` |
| Start floor | the étage noble (`oriel_start_floor`) |
| Projection | ≤ 0.40 m |
| Above the cornice | forbidden until 1902, permitted from `BONNIER` |
| Materials | metal/wood only under 1882's demountability rule; stone from 1902 |

`OrielNode` hangs off the `FacadeNode` (it spans several storeys) and carries a `WindowNode` per storey as its front glazing, so backends don't re-derive it. `OrielStyle` is `SQUARE` / `CANTED` / `BOWED`; placement is `CENTER`, `PAIR`, or `EVERY_BAY`, and never lands on the porte-cochère bay.

Frequency is a class marker — `VariationParams.oriel_probability` is 0.55 on `BOULEVARD`, 0.35 `RESIDENTIAL`, 0.12 `MODEST`.

Oriels run on their own `derive_child_rng("oriel")` stream, so adding them left every pre-1882 seed's output untouched.

**Note on 1893:** masonry oriels became legal mid-way through the Alphand era, which the four-way era split can't express; masonry is modelled as arriving with the 1902 règlement.

### Other encoded provisions

- **Minimum storey height 2.60 m** (1859, hygiene) — enforced during floor stacking. The entresol is exempt: it was a low mezzanine for offices, storage, and the concierge.
- **Courtyards ≥ 30 m²** (1884) — recorded, not yet used.

### Documented vs. modelled

Height tables, the 0.80 m / 6 m balcony rule, the 2.60 m minimum, the three envelope geometries, and the 8.50 m arc radius are all documented. Two values are inferred and marked `MODELLED` in the source: the arc radius for streets narrower than 20 m (scaled from the 8.50 m anchor) and the cap on the pre-1884 comble, where the text says only "avec une hauteur maximale".

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

Which floors carry balconies is decided by the 1823 ordinance (see **The Regulatory Model** above), not by a fixed floor list. The RNG still decides *how prominent* each of the two lines is:

- **Lower line**: the first floor clearing 6 m — the étage noble when there is an entresol, a storey higher when there isn't
- **Upper line**: the topmost eligible floor
- **Floors between**: individual balconettes under `ALPHAND`/`BONNIER` only
- **MODEST**: probabilistic prominence per building — 40% none / 30% balconette / 30% continuous on the lower line; the upper line is capped at the lower line's rank
- Continuous balconies span the bay extent (pier-to-pier, not full facade width); noble windows touch the balcony (sill=0)

### Roof

- **Shape**: derived from the gabarit envelope — see **The Regulatory Model**. `MansardType.DIAGONAL` for the pre-1884 45° comble, `BROKEN` for the post-1884 arc; `SHALLOW` on rear/side slopes. `STEEP` remains for envelope-free use.
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

### Phase 7: Regulatory Model -- DONE
- [x] `core/reglement.py` — Era, Reglement, height tables for 4 decrees
- [x] `GabaritEnvelope` — three roof envelope geometries (45° diagonal, circular arc, eighth-arc + oblique)
- [x] Comble height, angles and break point derived from the envelope, not sampled
- [x] `envelope_profile` polyline on `MansardSlopeNode`; SVG draws it directly
- [x] Balcony floors derived from the 1823 ordinance (6 m minimum, 0.80 m cap)
- [x] 1859 minimum storey height enforced in floor stacking (entresol exempt)
- [x] `HaussmannGrammar` copies its profile — no more mutation of shared presets
- [x] `tests/test_reglement.py` — 57 tests over the tables, geometry, and rules

### Phase 8: Oriels -- DONE
- [x] `oriel_rule()` — legality, start floor, projection cap, cornice limit, materials
- [x] `core/oriel.py` — placement patterns, spans, per-storey front glazing
- [x] `OrielNode` + `OrielStyle` in the IR; SVG renders body, returns, corbels, cap, crown
- [x] Isolated `oriel` RNG stream — pre-1882 seeds produce identical output
- [x] `tests/test_oriel.py` — 23 tests, including the negative case for every pre-1882 facade

### Future
- [ ] Street-level cornice and balcony alignment (circulaire du 21 septembre 1855)
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

# Generate with defaults (RESIDENTIAL, seed 42, Second Empire)
building = generate_building(BuildingConfig())

# The same building under each decree — 45° comble vs. curved comble
for era in ("SECOND_EMPIRE", "ALPHAND", "BONNIER"):
    b = generate_building(BuildingConfig(seed=42, era=era, street_width=30.0))

# Or give it a date and let the era resolve
b = generate_building(BuildingConfig(seed=42, year=1868))

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
