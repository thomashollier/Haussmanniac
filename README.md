# Haussmann

Procedural generator for Parisian Haussmann-style building facades. Pure Python core, deterministic with seed, backend-agnostic IR output.

## What It Does

Given a seed, a style preset, and optional overrides, the generator produces a complete intermediate representation (IR) tree describing a Haussmann building — floors, bays, windows, balconies, ornament, mansard roof, dormers, chimneys. A backend adapter then renders the IR to a target format.

## Quick Start

```python
from core.generator import generate_building
from core.types import BuildingConfig

building = generate_building(BuildingConfig(seed=0, style_preset="MODEST"))

from backends.svg import render_svg
with open("building.svg", "w") as f:
    f.write(render_svg(building))
```

## Style Presets

| Preset | Floors | Character |
|---|---|---|
| `BOULEVARD` | 7 (with entresol) | Rich ornament, pilasters, tall noble floor |
| `RESIDENTIAL` | 6 (with entresol) | Moderate ornament, typical side street |
| `MODEST` | 5 (no entresol) | Minimal ornament, narrow lot, wider piers |

## Overrides

Take the output of a specific seed and override individual decisions:

```python
from core.types import BuildingConfig, BuildingOverrides, PorteStyle, DormerStyle

config = BuildingConfig(
    seed=0,
    style_preset="MODEST",
    overrides=BuildingOverrides(
        has_dormers=True,           # Force dormers on (seed 0 rolls short roof)
        porte_style=PorteStyle.FLAT,  # Square porte-cochere instead of arch
        dormer_style=DormerStyle.OVAL,
    ),
)
building = generate_building(config)
```

Available override fields: `bay_count`, `porte_cochere_bay`, `porte_style`, `ground_floor_type`, `mansard_height`, `has_dormers`, `break_ratio`, `lower_angle`, `upper_angle`, `dormer_placement`, `dormer_style`. All `None` by default — only set fields are overridden.

## Profile Variation

Each style preset maps to a `FacadeProfile` containing all proportions. Use `profile_variation` (0.0-1.0) to shift proportions coherently — building DNA:

```python
config = BuildingConfig(seed=42, style_preset="BOULEVARD", profile_variation=0.3)
```

## Architecture

```
core/           Pure Python, zero dependencies. Profile -> Grammar -> IR tree.
backends/       SVG renderer (Blender + USD planned).
tests/          pytest suite (193 tests).
```

## Running Tests

```bash
python -m pytest tests/ -x
```

Requires Python 3.10+. No external dependencies for the core.
