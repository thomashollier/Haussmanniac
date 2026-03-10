# Procedural Haussmann Building Generator

## Project Overview

A procedural system for generating 3D buildings in the Parisian Haussmann style. The architecture uses a **backend-agnostic pure Python core** that outputs an intermediate representation (IR), consumed by **Blender** and **USD** backend adapters to produce actual geometry.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  CORE (pure Python)              │
│  grammar → generator → intermediate repr (IR)   │
└──────────────────┬──────────────────────────────┘
                   │  IR = tree of typed dataclasses
          ┌────────┴────────┐
          ▼                 ▼
  ┌──────────────┐  ┌──────────────┐
  │   Blender    │  │     USD      │
  │   Adapter    │  │   Adapter    │
  │  bpy/bmesh   │  │  pxr.Usd*   │
  └──────────────┘  └──────────────┘
```

### Three Layers

1. **Generative Core** (`core/`) — Pure Python, zero external dependencies. Contains all Haussmann rules, proportions, and assembly logic. Outputs a tree of parameterized nodes (the IR). No geometry lives here — only descriptions like "place a noble-floor window bay at (x,y,z) with width=1.2m, pediment='triangular'."

2. **Backend Adapters** (`backends/`) — Consume the IR tree and emit real geometry. Blender adapter uses `bpy`/`bmesh`. USD adapter uses `pxr.UsdGeom`/`pxr.UsdShade`. Each adapter walks the same IR tree but produces output native to its target.

3. **Asset Library** (`assets/`) — Pre-modeled ornamental pieces and 2D profile curves for extrusion. Referenced by ID in the IR; resolved to geometry by each backend.

---

## Project Structure

```
haussmann/
├── CLAUDE.md              # This file — project context for Claude
├── core/
│   ├── __init__.py
│   ├── types.py           # Dataclasses for intermediate representation
│   ├── grammar.py         # Haussmann architectural rules & proportions
│   ├── generator.py       # Top-level building generation pipeline
│   ├── facade.py          # Facade composition (bay layout, symmetry)
│   ├── floor.py           # Floor stacking logic
│   ├── roof.py            # Mansard roof generation
│   ├── ground_floor.py    # Shopfronts, porte-cochère, rustication
│   └── variation.py       # Controlled randomization & style params
├── backends/
│   ├── __init__.py
│   ├── base.py            # Abstract base adapter interface
│   ├── blender/
│   │   ├── __init__.py
│   │   ├── adapter.py     # IR → Blender geometry
│   │   ├── materials.py   # Shader node setup
│   │   ├── profiles.py    # Curve-based molding extrusion
│   │   └── operators.py   # Optional Blender UI panel/operators
│   └── usd/
│       ├── __init__.py
│       ├── adapter.py     # IR → USD prims
│       ├── materials.py   # UsdShade material setup
│       └── instancing.py  # Point instancer for repeated elements
├── assets/
│   ├── profiles/          # 2D SVG/curves for cornice moldings etc.
│   └── meshes/            # Pre-modeled ornamental .usd/.blend files
├── tests/
│   ├── test_types.py
│   ├── test_grammar.py
│   ├── test_generator.py
│   └── test_facade.py
├── examples/
│   ├── single_building.py # Generate one building, dump IR
│   ├── street_block.py    # Generate a row of buildings
│   └── export_usd.py      # Full pipeline to .usda output
└── pyproject.toml
```

---

## Haussmann Architectural Rules

These are the core constraints the system must encode. All values are typical ranges — the variation system picks within these bounds.

### Vertical Zoning (floor types, bottom to top)

| Floor             | Typical Height | Character                                    |
|-------------------|---------------|----------------------------------------------|
| Ground (RDC)      | 4.0–5.0 m     | Commercial. Tall openings, rusticated stone.  |
| Entresol          | 2.5–3.0 m     | Low intermediate. Small windows, sometimes omitted. |
| Étage Noble (2nd) | 3.2–3.8 m     | Tallest windows, richest ornament, continuous balcony. |
| 3rd Floor         | 3.0–3.5 m     | Slightly less ornate than noble floor.        |
| 4th Floor         | 2.8–3.2 m     | Simpler window surrounds.                     |
| 5th Floor         | 2.8–3.0 m     | Continuous balcony (second balcony line). Simpler ornament. |
| 6th (Mansard)     | 2.5–3.0 m     | Zinc-clad 45° roof slope. Dormers.            |

### Horizontal Rules

- **Bay width**: 1.0–1.8 m (window) with 0.4–0.8 m piers between
- **Bay count**: Typically 3–7 bays per facade, must be odd for symmetry
- **Alignment**: All openings align vertically across floors
- **Corner treatment**: 45° chamfer (pan coupé) at street intersections, ~3 m wide

### Balcony Rules

- **Floor 2 (noble)**: Continuous wrought-iron balcony spanning full facade
- **Floor 5**: Second continuous balcony
- **Other floors**: Individual balconettes per window, or none
- **Railing height**: ~1.0 m, decorative cast-iron patterns

### Ornament Hierarchy (decreasing with height)

- **Ground**: Rustication (bossage), large keystones, heavy cornice above
- **Noble floor**: Pilasters or engaged columns flanking windows, triangular/segmental pediments, elaborate window surrounds
- **Middle floors**: Simpler molded surrounds, cornices between floors
- **Upper floors**: Plain surrounds or just a lintel
- **Roof cornice**: Heavy projecting cornice with modillions/dentils at roofline

### Roof

- **Mansard angle**: ~45° lower slope, ~20° upper slope (often hidden)
- **Material**: Zinc cladding (grey)
- **Dormers**: One per bay or every other bay, stone or zinc surrounds
- **Chimneys**: Tall terracotta/stone chimney stacks, grouped

---

## Intermediate Representation (IR) Specification

The IR is a tree of Python dataclasses. Every node has a `transform` (local position/rotation/scale relative to parent) and a `node_type` string.

### Node Types

```python
BuildingNode          # Root. Contains metadata + child facades/roof.
├── FacadeNode        # One per building face. Has orientation, width.
│   ├── FloorNode     # One per storey on this facade.
│   │   ├── BayNode   # One per vertical bay on this floor.
│   │   │   ├── WindowNode
│   │   │   ├── BalconyNode
│   │   │   ├── PilasterNode
│   │   │   └── OrnamentNode  # Keystone, pediment, cornice segment
│   │   ├── CorniceNode       # Horizontal band between floors
│   │   └── StringCourseNode
│   └── GroundFloorNode        # Special: shopfronts, porte-cochère
├── RoofNode
│   ├── MansardSlopeNode
│   ├── DormerNode
│   └── ChimneyNode
└── CornerNode                 # Pan coupé chamfer treatment
```

### Key Dataclass Fields

- `BuildingNode`: lot_width, lot_depth, num_floors, style_params, seed
- `FacadeNode`: orientation (N/S/E/W), width, depth_offset
- `FloorNode`: floor_type (enum), height, y_offset, ornament_level (0–3)
- `BayNode`: width, x_offset, bay_type (window/door/blank)
- `WindowNode`: width, height, surround_style, pediment (none/triangular/segmental/arched), has_keystone
- `BalconyNode`: style, is_continuous, railing_pattern_id
- `RoofNode`: mansard_lower_angle, mansard_upper_angle, dormer_specs, chimney_positions

---

## Implementation Plan (ordered tasks)

Work through these sequentially. Each is a self-contained session.

### Phase 1: Foundation
- [ ] **Task 1**: `core/types.py` — Define all IR dataclasses with full type hints and defaults. Include a `Transform` dataclass (position, rotation, scale). Include enums for floor types, ornament levels, pediment styles, bay types.
- [ ] **Task 2**: `core/grammar.py` — Encode all Haussmann proportional rules as a `HaussmannGrammar` class. Methods like `get_floor_heights(num_floors) -> list[FloorSpec]`, `get_bay_layout(facade_width) -> list[BaySpec]`, `get_ornament_level(floor_type) -> int`. All magic numbers here, well-documented.
- [ ] **Task 3**: `tests/test_grammar.py` — Validate grammar outputs against real measurements from documented Haussmann buildings.

### Phase 2: Generation Pipeline
- [ ] **Task 4**: `core/floor.py` — Floor stacking: given building height + grammar, produce a list of `FloorNode` with correct heights and y-offsets.
- [ ] **Task 5**: `core/facade.py` — Bay distribution: given facade width + grammar, produce `BayNode` list with symmetry enforcement (odd count, optional center emphasis).
- [ ] **Task 6**: `core/generator.py` — Top-level pipeline: accept a `BuildingConfig`, run floor stacking → facade composition → ornament assignment → roof. Return complete `BuildingNode` tree.
- [ ] **Task 7**: `core/variation.py` — Seeded randomization system. Given a seed + style parameters, produce controlled variation in ornament density, pediment styles, color, dormer count.

### Phase 3: Roof & Ground Floor
- [ ] **Task 8**: `core/roof.py` — Mansard roof generation: compute slope geometry from footprint, place dormers per bay rhythm, position chimneys.
- [ ] **Task 9**: `core/ground_floor.py` — Ground floor logic: shopfront opening placement, porte-cochère detection (one per building, usually center or side), rustication parameters.

### Phase 4: Blender Backend
- [ ] **Task 10**: `backends/base.py` — Abstract `BackendAdapter` with `build(building_node) -> None` and per-node visitor methods.
- [ ] **Task 11**: `backends/blender/adapter.py` — Walk the IR tree, create Blender mesh objects. Start with box geometry per bay (no detail), get transforms right.
- [ ] **Task 12**: `backends/blender/adapter.py` — Add window boolean cutouts or inset geometry.
- [ ] **Task 13**: `backends/blender/profiles.py` — Cornice and molding generation via curve extrusion along facade edges.
- [ ] **Task 14**: `backends/blender/materials.py` — Principled BSDF setup: limestone for walls (warm cream), zinc for roof, cast iron for balconies, glass for windows.
- [ ] **Task 15**: `backends/blender/operators.py` — Simple Blender panel: seed, lot width, lot depth, style preset. Button to generate.

### Phase 5: USD Backend
- [ ] **Task 16**: `backends/usd/adapter.py` — Walk IR, emit `UsdGeom.Mesh` and `UsdGeom.Xform` hierarchy. Write `.usda` files.
- [ ] **Task 17**: `backends/usd/instancing.py` — Use `UsdGeom.PointInstancer` for repeated elements (windows, balcony rails, dormers) across a street.
- [ ] **Task 18**: `backends/usd/materials.py` — `UsdShade` material bindings with `UsdPreviewSurface`.

### Phase 6: Polish & Scale
- [ ] **Task 19**: LOD system — Generate 3 detail levels (far: extruded footprint, mid: windowed box, close: full ornament).
- [ ] **Task 20**: Street-level composition — Place multiple buildings along a polyline with shared party walls, varying widths, consistent cornice heights.

---

## Coding Conventions

- **Python 3.10+** — Use `dataclasses`, `enum.Enum`, type hints everywhere.
- **No geometry in core** — The `core/` package must have zero imports from `bpy`, `pxr`, `numpy`, or any non-stdlib package. It only uses stdlib (`dataclasses`, `enum`, `math`, `random`, `typing`).
- **Deterministic with seed** — All randomization uses `random.Random(seed)` instances, never the global `random`. Same seed + same config = identical IR tree.
- **Units** — All dimensions in meters. Origin at building front-left-ground corner. Y is up.
- **Naming** — snake_case for everything. IR node classes end in `Node`. Backend methods named `_build_<node_type>`.
- **Testing** — Every core module gets a corresponding test file. Test IR structure, not geometry.

---

## Style Presets

Define a few presets to make generation easy:

- **`BOULEVARD`** — Rich ornamentation, 7 bays, noble floor with full pilasters, triangular pediments. (Bd Haussmann, Av de l'Opéra)
- **`RESIDENTIAL`** — Moderate ornament, 5 bays, simpler surrounds. (Typical side street)
- **`MODEST`** — Minimal ornament, 3 bays, no entresol. (Back streets, upper arrondissements)

---

## Example Usage (target API)

```python
from haussmann.core.generator import generate_building
from haussmann.core.types import BuildingConfig

config = BuildingConfig(
    lot_width=15.0,
    lot_depth=12.0,
    num_floors=6,
    style_preset="BOULEVARD",
    seed=42,
)

# Pure IR — no geometry, no dependencies
building = generate_building(config)

# Blender backend
from haussmann.backends.blender.adapter import BlenderAdapter
adapter = BlenderAdapter()
adapter.build(building)

# USD backend
from haussmann.backends.usd.adapter import UsdAdapter
adapter = UsdAdapter(output_path="building.usda")
adapter.build(building)
```

---

## Getting Started

To begin implementation, start with Task 1:

```bash
claude "Read CLAUDE.md, then implement Task 1: create core/types.py with all IR dataclasses, Transform, and enums. Follow the coding conventions strictly."
```

Then proceed sequentially:

```bash
claude "Read CLAUDE.md, then implement Task 2: create core/grammar.py with the HaussmannGrammar class encoding all proportional rules from the architectural spec."
```

Each task is scoped to roughly one file and one session.
