"""Generate an 8×6 grid of random Haussmann buildings as a single SVG."""

import random

from core.generator import generate_building
from core.types import BuildingConfig, BuildingNode, FacadeNode, FloorNode, GroundFloorNode, RoofNode, MansardSlopeNode, Orientation
from backends.svg import (
    SVGContext, COLORS, SCALE,
    _facade_height, _draw_ground_floor, _draw_upper_floor, _draw_cornice,
    _draw_roof, _draw_pier_lines,
    CorniceNode,
)

ROWS = 8
COLS = 6
GAP_X_M = 0.4    # horizontal gap between buildings (metres)
GAP_Y_M = 1.5    # vertical gap between rows
MARGIN_M = 1.5   # margin around the whole grid

rng = random.Random(2026)

# Generate buildings with varied presets, widths, and seeds
buildings: list[BuildingNode] = []
for i in range(ROWS * COLS):
    preset = rng.choice(["BOULEVARD", "RESIDENTIAL", "MODEST"])
    seed = rng.randint(0, 9999)
    variation = rng.uniform(0.0, 0.4)

    # Pick a lot width appropriate to the preset
    if preset == "BOULEVARD":
        lot_width = rng.uniform(16.0, 22.0)
    elif preset == "RESIDENTIAL":
        lot_width = rng.uniform(11.0, 16.0)
    else:
        lot_width = rng.uniform(7.0, 11.0)

    config = BuildingConfig(
        style_preset=preset,
        seed=seed,
        lot_width=round(lot_width, 1),
        profile_variation=round(variation, 2),
    )
    buildings.append(generate_building(config))


def _building_dims(b: BuildingNode) -> tuple[float, float, float]:
    """Return (facade_width, stone_height, roof_height)."""
    facade = next((c for c in b.children if isinstance(c, FacadeNode) and c.orientation == Orientation.SOUTH), None)
    if not facade:
        return 0, 0, 0
    stone_h = _facade_height(facade)
    roof = next((c for c in b.children if isinstance(c, RoofNode)), None)
    roof_h = 0.0
    if roof:
        slopes = [c for c in roof.children if isinstance(c, MansardSlopeNode)]
        if slopes:
            roof_h = slopes[0].height
    return facade.width, stone_h, roof_h


# Compute row layout: each row has COLS buildings side by side
# Normalize widths per row so buildings tile nicely
row_buildings = [buildings[r * COLS:(r + 1) * COLS] for r in range(ROWS)]

# Find the max total height across all buildings (for uniform row height)
all_dims = [_building_dims(b) for b in buildings]
max_total_h = max(sh + rh for _, sh, rh in all_dims)

# Target row width: widest row determines canvas width
TARGET_ROW_WIDTH = 90.0  # metres — fits nicely on screen

# Scale each row's buildings to fill the target width
row_configs: list[list[tuple[BuildingNode, float, float, float, float]]] = []
for r in range(ROWS):
    row = row_buildings[r]
    dims = [_building_dims(b) for b in row]
    raw_width = sum(d[0] for d in dims) + GAP_X_M * (COLS - 1)
    scale_factor = TARGET_ROW_WIDTH / raw_width if raw_width > 0 else 1.0
    # Don't scale — just use natural widths, we'll compute total
    configs = []
    for b, (fw, sh, rh) in zip(row, dims):
        configs.append((b, fw, sh, rh, 1.0))
    row_configs.append(configs)

# Compute actual row widths and total canvas size
row_widths = []
for configs in row_configs:
    w = sum(fw for _, fw, _, _, _ in configs) + GAP_X_M * (COLS - 1)
    row_widths.append(w)

canvas_w_m = max(row_widths) + MARGIN_M * 2
row_height_m = max_total_h + GAP_Y_M
canvas_h_m = row_height_m * ROWS + MARGIN_M * 2

canvas_w_px = canvas_w_m * SCALE
canvas_h_px = canvas_h_m * SCALE

# Start building SVG
elements: list[str] = []

# Sky background
elements.append(
    f'<rect x="0" y="0" width="{canvas_w_px:.0f}" height="{canvas_h_px:.0f}" fill="{COLORS["sky"]}"/>'
)

# Draw each building
for r, configs in enumerate(row_configs):
    # Center the row horizontally
    row_w = sum(fw for _, fw, _, _, _ in configs) + GAP_X_M * (COLS - 1)
    row_x_offset = (canvas_w_m - row_w) / 2

    x_cursor_m = row_x_offset
    for b, fw, sh, rh, _ in configs:
        facade = next((c for c in b.children if isinstance(c, FacadeNode) and c.orientation == Orientation.SOUTH), None)
        roof = next((c for c in b.children if isinstance(c, RoofNode)), None)
        if not facade:
            x_cursor_m += fw + GAP_X_M
            continue

        # Position: bottom of this building in the row
        # All buildings in a row share the same ground line
        ground_y_m = MARGIN_M + (r + 1) * row_height_m - GAP_Y_M * 0.3

        ctx = SVGContext(
            elements=elements,
            scale=SCALE,
            x_origin=x_cursor_m * SCALE,
            y_origin=ground_y_m * SCALE,
        )

        # Ground plane strip for this building
        ctx.elements.append(
            f'<rect x="{ctx.x(-0.1):.1f}" y="{ctx.y(0):.1f}" '
            f'width="{ctx.px(fw + 0.2):.1f}" height="{ctx.px(GAP_Y_M * 0.3):.1f}" '
            f'fill="{COLORS["ground"]}"/>'
        )

        # Wall background
        ctx.rect(0, 0, fw, sh, COLORS["wall"], stroke_w=0.8)

        # Render floors
        for child in facade.children:
            if isinstance(child, GroundFloorNode):
                _draw_ground_floor(ctx, child, fw, False)
            elif isinstance(child, FloorNode):
                _draw_upper_floor(ctx, child, fw, False)
            elif isinstance(child, CorniceNode):
                _draw_cornice(ctx, child)

        # Render roof
        if roof:
            cornice_band_h = 0.20
            _draw_roof(ctx, roof, fw, sh + cornice_band_h, rh)

        x_cursor_m += fw + GAP_X_M

# Assemble SVG
svg = (
    f'<svg xmlns="http://www.w3.org/2000/svg" '
    f'width="{canvas_w_px:.0f}" height="{canvas_h_px:.0f}" '
    f'viewBox="0 0 {canvas_w_px:.0f} {canvas_h_px:.0f}">\n'
    f'<style>text {{ font-family: "Helvetica Neue", Arial, sans-serif; }}</style>\n'
)
svg += "\n".join(elements)
svg += "\n</svg>"

out_path = "output/grid_48.svg"
with open(out_path, "w") as f:
    f.write(svg)
print(f"Wrote {out_path} ({len(svg) // 1024} KB, {canvas_w_px:.0f}×{canvas_h_px:.0f} px)")
