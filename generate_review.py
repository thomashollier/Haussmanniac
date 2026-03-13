"""Generate 128 RESIDENTIAL buildings for review.

Each building gets a unique seed and random profile_variation.
Outputs individual PNGs + a CSV catalogue with descriptions.
"""

import csv
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cairosvg

from core.generator import generate_building
from core.types import (
    BalconyNode,
    BayNode,
    BayType,
    BuildingConfig,
    ChimneyNode,
    CustomBayStyle,
    DormerNode,
    FacadeNode,
    FloorNode,
    FloorType,
    GroundFloorNode,
    GroundFloorType,
    Orientation,
    PorteStyle,
    RoofNode,
    MansardSlopeNode,
)
from backends.svg import render_svg

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review")
N = 128


def describe_building(building, config):
    """Build a short human-readable description of key decisions."""
    front = next(c for c in building.children
                 if isinstance(c, FacadeNode) and c.orientation == Orientation.SOUTH)
    roof = next(c for c in building.children if isinstance(c, RoofNode))

    floors = [c for c in front.children if isinstance(c, FloorNode)]
    gf_list = [c for c in front.children if isinstance(c, GroundFloorNode)]
    dormers = [c for c in roof.children if isinstance(c, DormerNode)]
    chimneys = [c for c in roof.children if isinstance(c, ChimneyNode)]
    slopes = [c for c in roof.children if isinstance(c, MansardSlopeNode)]

    # Bay count + custom bays from first regular floor
    all_bays = []
    custom_bays = []
    if floors:
        all_bays = [c for c in floors[0].children if isinstance(c, BayNode)]
        custom_bays = [b for b in all_bays if b.bay_type == BayType.CUSTOM]
    n_bays = len(all_bays)

    # Porte info
    has_porte = gf_list[0].has_porte_cochere if gf_list else False
    porte_idx = gf_list[0].porte_cochere_bay_index if gf_list and has_porte else None

    # Door bay — find porte style from ground floor bays
    porte_style_str = ""
    if has_porte and gf_list:
        gf_bays = [c for c in gf_list[0].children if isinstance(c, BayNode)]
        door_bays = [b for b in gf_bays if b.bay_type == BayType.DOOR]
        if door_bays:
            porte_style_str = door_bays[0].porte_style.name.lower()

    # Ground floor type — infer from bay types
    gf_type = "residential"
    if gf_list:
        gf_bays = [c for c in gf_list[0].children if isinstance(c, BayNode)]
        shop_bays = [b for b in gf_bays if b.bay_type == BayType.SHOPFRONT]
        win_bays = [b for b in gf_bays if b.bay_type == BayType.WINDOW]
        if shop_bays and win_bays:
            gf_type = "mixed"
        elif shop_bays:
            gf_type = "commercial"

    # Balconies — check noble and fifth floors
    balcony_desc = []
    for fl in floors:
        if fl.floor_type in (FloorType.NOBLE, FloorType.FIFTH):
            bal_nodes = [c for c in fl.children if isinstance(c, BalconyNode)]
            if bal_nodes:
                continuous = any(b.is_continuous for b in bal_nodes)
                if continuous:
                    balcony_desc.append(f"{fl.floor_type.name.lower()}=continuous")
                else:
                    balcony_desc.append(f"{fl.floor_type.name.lower()}=balconette")
            else:
                balcony_desc.append(f"{fl.floor_type.name.lower()}=none")

    # Entresol
    has_entresol = any(f.floor_type == FloorType.ENTRESOL for f in floors)

    # Mansard info
    mansard_h = roof.transform.position[1]  # cornice height
    roof_h = slopes[0].height if slopes else 0

    parts = []
    parts.append(f"{building.num_floors}fl")
    parts.append(f"w={building.lot_width:.1f}m")
    parts.append(f"{n_bays}bays")
    if has_entresol:
        parts.append("entresol")
    parts.append(f"gf={gf_type}")
    if has_porte:
        s = f"porte({porte_style_str},bay{porte_idx})" if porte_idx is not None else f"porte({porte_style_str})"
        parts.append(s)
    if custom_bays:
        styles = set(b.custom_bay_style.name.lower() for b in custom_bays if b.custom_bay_style)
        side = "left" if custom_bays[0].x_offset < building.lot_width / 2 else "right"
        parts.append(f"custom={','.join(styles)}({side})")
    if balcony_desc:
        parts.append("bal:" + ",".join(balcony_desc))
    if dormers:
        parts.append(f"{len(dormers)}dorm({dormers[0].style.name.lower()})")
    else:
        parts.append("no_dormers")
    parts.append(f"{len(chimneys)}chim")
    parts.append(f"roof_h={roof_h:.1f}m")

    return "; ".join(parts)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # Deterministic but spread-out seeds and variations
    rng = random.Random(2026)
    configs = []
    for i in range(N):
        seed = rng.randint(0, 99999)
        variation = round(rng.uniform(0.0, 1.0), 2)
        configs.append((i, seed, variation))

    rows = []
    for i, seed, variation in configs:
        filename = f"{i+1:03d}_s{seed}_v{variation:.2f}.png"
        print(f"[{i+1}/{N}] seed={seed} var={variation:.2f} -> {filename}")

        config = BuildingConfig(
            seed=seed,
            style_preset="RESIDENTIAL",
            profile_variation=variation,
        )
        building = generate_building(config)
        svg_str = render_svg(building, show_labels=False)

        # Convert SVG -> PNG
        png_path = os.path.join(OUT_DIR, filename)
        cairosvg.svg2png(bytestring=svg_str.encode("utf-8"), write_to=png_path,
                         output_width=600)

        desc = describe_building(building, config)
        rows.append({
            "filename": filename,
            "seed": seed,
            "variation": variation,
            "description": desc,
            "feedback": "",
        })

    # Write CSV
    csv_path = os.path.join(OUT_DIR, "review.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "seed", "variation", "description", "feedback"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone! {N} buildings in {OUT_DIR}/")
    print(f"CSV catalogue: {csv_path}")


if __name__ == "__main__":
    main()
