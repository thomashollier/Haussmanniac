"""Generate 200m streets — one per preset — with per-building color variation."""

import os
import math
import random
import subprocess

from core.generator import generate_building
from core.types import (
    BuildingConfig, BuildingNode, FacadeNode, FloorNode,
    GroundFloorNode, MansardSlopeNode, Orientation, RoofNode,
)
from backends.svg import (
    SVGContext, COLORS, SCALE,
    _facade_height, _draw_ground_floor, _draw_upper_floor, _draw_cornice,
    _draw_roof, CorniceNode,
    apply_color_variation, restore_colors,
)

TARGET_WIDTH_M = 200.0
MARGIN_M = 1.5
SEED = 2026

LOT_RANGES = {
    "BOULEVARD":   (16.0, 22.0),
    "RESIDENTIAL": (11.0, 16.0),
    "MODEST":      (7.0, 11.0),
}

# ── Tree drawing ─────────────────────────────────────────────────────

def _draw_tree(elements: list[str], cx_px: float, ground_y_px: float,
               height_m: float, scale: float, rng: random.Random) -> None:
    """Draw a stylised deciduous street tree (trunk + leafy crown)."""
    trunk_h_m = height_m * 0.30
    crown_h_m = height_m * 0.70
    trunk_w_m = 0.35 + rng.uniform(-0.05, 0.05)
    crown_w_m = height_m * 0.45 + rng.uniform(-0.5, 0.5)

    # Trunk
    tx = cx_px - trunk_w_m / 2 * scale
    ty = ground_y_px - trunk_h_m * scale
    elements.append(
        f'<rect x="{tx:.1f}" y="{ty:.1f}" '
        f'width="{trunk_w_m * scale:.1f}" height="{trunk_h_m * scale:.1f}" '
        f'fill="#5A4A38" stroke="#4A3A28" stroke-width="0.8" rx="2"/>'
    )

    # Crown — stacked ellipses for organic shape
    crown_base_y = ground_y_px - trunk_h_m * scale
    crown_cx = cx_px + rng.uniform(-0.1, 0.1) * scale

    # Main crown body
    rx_main = crown_w_m / 2 * scale
    ry_main = crown_h_m / 2 * scale
    cy_main = crown_base_y - crown_h_m / 2 * scale
    green_h = rng.randint(75, 100)
    green_s = rng.randint(35, 55)
    green_l = rng.randint(28, 38)
    fill = f"hsl({green_h},{green_s}%,{green_l}%)"
    stroke = f"hsl({green_h},{green_s}%,{green_l - 8}%)"

    elements.append(
        f'<ellipse cx="{crown_cx:.1f}" cy="{cy_main:.1f}" '
        f'rx="{rx_main:.1f}" ry="{ry_main:.1f}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1.0"/>'
    )

    # Highlight lobe (upper-left, lighter)
    lobe_rx = rx_main * 0.65
    lobe_ry = ry_main * 0.55
    lobe_cx = crown_cx - rx_main * 0.15
    lobe_cy = cy_main - ry_main * 0.25
    light_fill = f"hsl({green_h},{green_s - 5}%,{green_l + 7}%)"
    elements.append(
        f'<ellipse cx="{lobe_cx:.1f}" cy="{lobe_cy:.1f}" '
        f'rx="{lobe_rx:.1f}" ry="{lobe_ry:.1f}" '
        f'fill="{light_fill}" stroke="none" opacity="0.6"/>'
    )


def _building_dims(b: BuildingNode) -> tuple[float, float, float]:
    facade = next(
        (c for c in b.children
         if isinstance(c, FacadeNode) and c.orientation == Orientation.SOUTH),
        None,
    )
    if not facade:
        return 0.0, 0.0, 0.0
    stone_h = _facade_height(facade)
    roof = next((c for c in b.children if isinstance(c, RoofNode)), None)
    roof_h = 0.0
    if roof:
        slopes = [c for c in roof.children if isinstance(c, MansardSlopeNode)]
        if slopes:
            roof_h = slopes[0].height
    return facade.width, stone_h, roof_h


def generate_street(preset: str, seed: int, trees: bool = False,
                    tree_spacing_m: float = 30.0,
                    tree_height_range: tuple[float, float] = (15.0, 20.0)) -> None:
    rng = random.Random(seed)
    lo, hi = LOT_RANGES[preset]

    # Generate buildings until we fill target width
    buildings: list[BuildingNode] = []
    total_w = 0.0
    while total_w < TARGET_WIDTH_M:
        s = rng.randint(0, 99999)
        variation = rng.uniform(0.0, 0.5)
        lot_width = round(rng.uniform(lo, hi), 1)
        config = BuildingConfig(
            style_preset=preset,
            seed=s,
            lot_width=lot_width,
            profile_variation=round(variation, 2),
        )
        b = generate_building(config)
        buildings.append(b)
        fw, _, _ = _building_dims(b)
        total_w += fw

    dims = [_building_dims(b) for b in buildings]
    total_width_m = sum(d[0] for d in dims)
    max_total_h = max(sh + rh for _, sh, rh in dims)

    canvas_w_m = total_width_m + MARGIN_M * 2
    canvas_h_m = max_total_h + MARGIN_M * 2 + 1.0
    canvas_w_px = canvas_w_m * SCALE
    canvas_h_px = canvas_h_m * SCALE

    elements: list[str] = []
    elements.append(
        f'<rect x="0" y="0" width="{canvas_w_px:.0f}" height="{canvas_h_px:.0f}" '
        f'fill="{COLORS["sky"]}"/>'
    )

    ground_y_m = MARGIN_M + max_total_h + 0.5
    elements.append(
        f'<rect x="0" y="{ground_y_m * SCALE:.1f}" '
        f'width="{canvas_w_px:.0f}" height="{1.0 * SCALE:.1f}" '
        f'fill="{COLORS["ground"]}"/>'
    )

    x_cursor_m = MARGIN_M
    for b, (fw, sh, rh) in zip(buildings, dims):
        facade = next(
            (c for c in b.children
             if isinstance(c, FacadeNode) and c.orientation == Orientation.SOUTH),
            None,
        )
        roof = next((c for c in b.children if isinstance(c, RoofNode)), None)
        if not facade:
            x_cursor_m += fw
            continue

        apply_color_variation(b.seed, 0.05)

        ctx = SVGContext(
            elements=elements,
            scale=SCALE,
            x_origin=x_cursor_m * SCALE,
            y_origin=ground_y_m * SCALE,
            palette=b.element_palette,
        )

        ctx.rect(0, 0, fw, sh, COLORS["wall"], stroke_w=0.8)
        gf_node = next((c for c in facade.children if isinstance(c, GroundFloorNode)), None)
        if gf_node:
            ctx.rect(0, 0, fw, gf_node.height, COLORS.get("wall_ground", COLORS["wall"]), stroke_w=0)

        for child in facade.children:
            if isinstance(child, GroundFloorNode):
                _draw_ground_floor(ctx, child, fw, False)
            elif isinstance(child, FloorNode):
                _draw_upper_floor(ctx, child, fw, False)
            elif isinstance(child, CorniceNode):
                _draw_cornice(ctx, child)

        if roof:
            _draw_roof(ctx, roof, fw, sh + 0.20, rh)

        restore_colors()

        if x_cursor_m > MARGIN_M:
            wall_top = ground_y_m - sh
            elements.append(
                f'<line x1="{x_cursor_m * SCALE:.1f}" y1="{wall_top * SCALE:.1f}" '
                f'x2="{x_cursor_m * SCALE:.1f}" y2="{ground_y_m * SCALE:.1f}" '
                f'stroke="#8A8070" stroke-width="1.5" opacity="0.6"/>'
            )

        x_cursor_m += fw

    # Trees in front of buildings (boulevard only)
    if trees:
        tree_rng = random.Random(seed + 7777)
        x_tree = MARGIN_M + tree_spacing_m / 2
        while x_tree < MARGIN_M + total_width_m:
            th = tree_rng.uniform(tree_height_range[0], tree_height_range[1])
            _draw_tree(elements, x_tree * SCALE, ground_y_m * SCALE,
                       th, SCALE, tree_rng)
            x_tree += tree_spacing_m

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{canvas_w_px:.0f}" height="{canvas_h_px:.0f}" '
        f'viewBox="0 0 {canvas_w_px:.0f} {canvas_h_px:.0f}">\n'
        f'<style>text {{ font-family: "Helvetica Neue", Arial, sans-serif; }}</style>\n'
    )
    svg += "\n".join(elements)
    svg += "\n</svg>"

    os.makedirs("output", exist_ok=True)
    name = f"street_{preset.lower()}"
    svg_path = f"output/{name}.svg"
    png_path = f"output/{name}.png"

    with open(svg_path, "w") as f:
        f.write(svg)
    subprocess.run(["rsvg-convert", "-o", png_path, svg_path], check=True)

    print(f"  {preset}: {len(buildings)} buildings, {total_width_m:.0f}m -> {png_path}")


if __name__ == "__main__":
    generate_street("BOULEVARD", SEED, trees=True, tree_height_range=(16.0, 18.0))
    generate_street("RESIDENTIAL", SEED)
    generate_street("MODEST", SEED)
    print("Done.")
