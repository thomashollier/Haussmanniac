# Haussmann

Procedural generator for Parisian Haussmann-style building facades. Given a seed and a style preset, it produces a complete building — floors, bays, windows, balconies, ornament, mansard roof, ground floor commerce — that follows the proportional rules of the historical style while varying within those rules so no two buildings look alike.

Pure Python core, deterministic with seed, backend-agnostic intermediate representation.

![Grid of generated Haussmann buildings](examples/output/grid_residential_4x16.svg)

## How It Works

The generator doesn't draw buildings. It produces a tree of typed dataclasses — an intermediate representation (IR) — describing every architectural element with its dimensions and position in metres. A backend adapter then renders the IR to a target format (currently SVG; Blender and USD planned).

```
seed + preset ──→ profile ──→ grammar ──→ IR tree ──→ backend ──→ output
```

The pipeline has two levels of controlled randomness:

1. **Profile variation** shifts proportions coherently — building DNA. Bay width, floor heights, pier ratios all move together within historically correct bounds.
2. **Element variation** makes per-building random choices — dormer style, balcony type, ground floor commerce, custom bay treatment — sampling from weighted probability distributions that differ by preset.

Both are driven by a single seed through `random.Random(seed)`. Same seed, same building. Always.

## Layout System

A Haussmann facade is a grid. Vertically: floors stacked within a height budget (the gabarit). Horizontally: bays repeated at regular intervals with edge piers absorbing leftover width.

### Vertical: Gabarit and Floor Stacking

Paris building heights were regulated by street width. The generator reproduces this:

| Street Width | Gabarit (max height) |
|---|---|
| > 20 m | 20.0 m |
| ≥ 9.75 m | 17.55 m |
| ≥ 7.80 m | 14.60 m |
| < 7.80 m | 11.70 m |

Floors stack bottom-up within this budget. Each floor height is sampled from a truncated normal distribution centred on historical values — ground floor ~3.2–4.0 m, noble floor (étage noble) ~2.95–3.75 m, upper floors progressively shorter. The entresol (mezzanine) is included probabilistically: 85% for boulevard buildings, 70% for residential, never for modest. Floors that don't fit within the gabarit are dropped.

This means a boulevard building on a wide street gets 7 floors with an entresol, while a modest building on a narrow street might only get 5.

### Horizontal: Bay Solver

A **bay** is the repeating horizontal module: half pier + window opening + half pier, measured centerline to centerline. The pier-to-opening ratio follows the historical ~1:1 *plein/vide* rule — roughly equal parts solid stone and void.

```
|<-edge pier->|<hp>| window |<hp><hp>| window |<hp><hp>| window |<hp>|<-edge pier->|
              |<---------- bay --------->|<---------- bay --------->|
```

The solver fits as many bays as the lot width allows (always odd for symmetry, except modest buildings which allow even counts). Edge piers absorb leftover width. When an edge pier grows too wide, the solver inserts a single narrow **custom bay** on one side — an asymmetric element placed opposite the door. Custom bays get one of four treatments: oeil-de-boeuf (porthole), narrow window, rusticated stonework panel, or geometric diamond relief.

The porte-cochère (carriage entrance) occupies one bay, typically centre or near-centre, and is 1.5× wider than standard bays on boulevard and residential buildings.

### Ornament Hierarchy

Ornament follows floor rank. The noble floor (2nd) gets the richest treatment — continuous balcony, pilastered window surrounds, pediments. The 3rd and 4th floors are progressively simpler. The 5th floor gets a second continuous balcony (on grand and residential buildings) or probabilistic balconettes. Modest buildings may have no balconies at all — a per-building coin flip decides.

## Variation Strategy

Every random decision flows through `random.Random(seed)` with a fixed call sequence. Overrides are applied *after* each RNG call so the sequence is consumed identically regardless of overrides — changing one decision doesn't cascade into others.

### What Varies Per-Building

| Decision | Method | Distribution |
|---|---|---|
| Lot width | Truncated normal from preset range | GRAND: 21 ± 3.5 m, RES: 15 ± 3 m, MODEST: 10 ± 2 m |
| Bay width | Truncated normal | GRAND: 2.6 ± 0.4 m, RES: 2.3 ± 0.35 m, MODEST: 2.15 ± 0.45 m |
| Floor heights | Truncated normal per floor type | Peaked at historical values, ~±5–10% |
| Bay count | Probabilistic around width-derived count | 80% base, 15% ±2, 5% ±1 |
| Street width | Truncated normal from preset range | Determines gabarit → floor count |
| Entresol | Bernoulli per preset | 85% / 70% / 0% |
| Door placement | Centre-biased | 80% centre, 20% edge (boulevard); side-biased for modest |
| Door style | Arched vs flat | 50/50 default, preset-weighted |
| Ground floor type | Weighted categorical | Commercial / Mixed / Residential |
| Custom bay side | Opposite the door, or coin flip | Deterministic when door is off-centre |
| Custom bay style | 4-bucket weighted | Porthole 40%, narrow 25%, geometric 15%, stonework 20% |
| Balcony type | Per-floor Bernoulli (MODEST only) | Noble: 40% none / 30% balconette / 30% continuous |
| Dormer style | Uniform categorical | All 6 styles (GRAND/RES); 2 styles (MODEST) |
| Dormer placement | 4-bucket weighted | Between bays 50%, every bay 17%, every other 17%, centre 16% |
| Mansard height | Coin flip + jitter (MODEST) | 50% short (no dormers) / 50% tall (with dormers) |
| Cafe style | 9-bucket weighted per preset | Bistro, arched, recessed, knee wall, pilaster, + 4 open terrace |
| Storefront style | 5-bucket weighted per preset | Classic, display, recessed entry, pilastered, minimal |
| Door style | 5-bucket weighted per preset | Arched classic, flat panel, double leaf, glass topped, ornate |
| Balcony railing | 5-bucket weighted per preset | Classic scroll, geometric, simple bars, art nouveau, greek key |
| Awning | Bernoulli + 4-bucket | 30% chance, then flat box / retractable / scalloped / striped |

### What Stays Fixed

The proportional *rules* never change — they define the style:

- Pier-to-opening ratio (~0.48–0.51)
- Window width as fraction of opening (~0.92)
- Noble floor is always the tallest and most ornate
- Floors get shorter and simpler as you go up
- Mansard roof always sits on top
- Ground floor is always rusticated on boulevard buildings
- Edge piers always absorb leftover width
- Adjacent shopfront groups on opposite sides of the door always get different treatments (cafe vs boutique)

## Style Presets

| Preset | Character | Typical | Bay Width | Floors |
|---|---|---|---|---|
| `BOULEVARD` | Rich ornament, pilasters, tall noble floor, entresol | Bd Haussmann, Av de l'Opéra | 2.6 m | 6–7 |
| `RESIDENTIAL` | Moderate ornament, typical side street | Rue de Rivoli side streets | 2.3 m | 6–7 |
| `MODEST` | Minimal ornament, wider piers, no entresol | Upper arrondissements | 2.15 m | 5–6 |

## Ground Floor Commerce

Ground floors are split into shopfront groups by the porte-cochère. Consecutive commercial bays form stores: groups of 3+ bays become cafes, groups of 2 become boutiques. When two groups flank the door, the larger gets cafe treatment and the smaller gets boutique treatment, ensuring visual variety.

Each building picks a single cafe style and a single storefront style from its element palette — 9 cafe styles and 5 storefront styles, weighted by preset. Awnings are added with ~30% probability in 4 styles.

**Per-bay cafe styles** (raised kickplate, individual bay treatment):
- Bistro mullions — glass panels with vertical mullions and transom
- Arched — semicircular arch tops with keystone
- Recessed — deep shadow recess framing glass
- Knee wall — low stone wall with tall glass above
- Pilaster frame — stone pilasters between bays with lintel band

**Open terrace styles** (glass closer to ground, spanning across bays):
- Full span — full-height glass with thin metal mullions replacing piers
- Kickplate glass — 15 cm stone base, full glass above
- Narrow piers — thin stone piers between glass bays
- Open terrace — alternating open and glazed panels

## Quick Start

```python
from core.generator import generate_building
from core.types import BuildingConfig

building = generate_building(BuildingConfig(seed=42, style_preset="BOULEVARD"))

from backends.svg import render_svg
with open("building.svg", "w") as f:
    f.write(render_svg(building))
```

### Profile Variation

Use `profile_variation` (0.0–1.0) to shift proportions coherently across the building:

```python
config = BuildingConfig(seed=42, style_preset="BOULEVARD", profile_variation=0.3)
```

### Overrides

Override individual RNG-driven decisions while keeping everything else deterministic:

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
```

Available: `bay_count`, `porte_cochere_bay`, `porte_style`, `ground_floor_type`, `mansard_height`, `has_dormers`, `break_ratio`, `lower_angle`, `upper_angle`, `dormer_placement`, `dormer_style`, `has_custom_bays`, `custom_bay_style`.

### Batch Generation

```bash
python generate_review.py    # 128 buildings × 3 presets → review/{boulevard,residential,modest}/
python generate_grid.py      # 8×6 mixed grid → output/grid_48.svg
```

## Architecture

```
core/           Pure Python, zero dependencies. Profile → Grammar → IR tree.
  profile.py      All proportions as parameterised dataclasses (RangeParam)
  grammar.py      Bay solver, floor specs, ornament rules
  generator.py    Top-level pipeline: config → IR tree
  variation.py    Seeded RNG with truncated normal sampling
  elements.py     Element palette: cafe/storefront/door/balcony/awning styles
  facade.py       Bay population, windows, balconies, surrounds
  floor.py        Floor stacking within gabarit budget
  ground_floor.py Shopfronts, porte-cochère, store type assignment
  roof.py         Mansard slopes, dormers (6 styles), chimneys

backends/       Consume IR tree, produce output.
  svg.py          2D facade elevation renderer
  svg_elements.py Element-level SVG renderers (cafes, storefronts, doors, awnings)

tests/          pytest suite (242 tests)
```

## Running Tests

```bash
python -m pytest tests/ -x
```

Requires Python 3.10+. No external dependencies for the core. SVG-to-PNG conversion requires `rsvg-convert` (from librsvg).
