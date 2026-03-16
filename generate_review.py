"""Generate 128 buildings per category (BOULEVARD, RESIDENTIAL, MODEST) as PNGs in review/."""

import csv
import os
import random
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.generator import generate_building
from core.types import (
    BalconyNode, BayNode, BayType, BuildingConfig, ChimneyNode,
    CustomBayStyle, DormerNode, FacadeNode, FloorNode, FloorType,
    GroundFloorNode, GroundFloorType, MansardSlopeNode, Orientation,
    PorteStyle, RoofNode,
)
from backends.svg import render_svg

REVIEW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review")
CATEGORIES = ["boulevard", "residential", "modest"]
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

    all_bays, custom_bays = [], []
    if floors:
        all_bays = [c for c in floors[0].children if isinstance(c, BayNode)]
        custom_bays = [b for b in all_bays if b.bay_type == BayType.CUSTOM]
    n_bays = len(all_bays)

    has_porte = gf_list[0].has_porte_cochere if gf_list else False
    porte_idx = gf_list[0].porte_cochere_bay_index if gf_list and has_porte else None

    porte_style_str = ""
    if has_porte and gf_list:
        gf_bays = [c for c in gf_list[0].children if isinstance(c, BayNode)]
        door_bays = [b for b in gf_bays if b.bay_type == BayType.DOOR]
        if door_bays:
            porte_style_str = door_bays[0].porte_style.name.lower()

    gf_type = "residential"
    if gf_list:
        gf_bays = [c for c in gf_list[0].children if isinstance(c, BayNode)]
        shop_bays = [b for b in gf_bays if b.bay_type == BayType.SHOPFRONT]
        win_bays = [b for b in gf_bays if b.bay_type == BayType.WINDOW]
        if shop_bays and win_bays:
            gf_type = "mixed"
        elif shop_bays:
            gf_type = "commercial"

    balcony_desc = []
    for fl in floors:
        if fl.floor_type in (FloorType.NOBLE, FloorType.FIFTH):
            bal_nodes = [c for c in fl.children if isinstance(c, BalconyNode)]
            if bal_nodes:
                continuous = any(b.is_continuous for b in bal_nodes)
                balcony_desc.append(f"{fl.floor_type.name.lower()}={'continuous' if continuous else 'balconette'}")
            else:
                balcony_desc.append(f"{fl.floor_type.name.lower()}=none")

    has_entresol = any(f.floor_type == FloorType.ENTRESOL for f in floors)
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

    # Element palette info
    ep = building.element_palette
    if ep:
        parts.append(f"cafe={ep.cafe_style.name.lower()}")
        parts.append(f"store={ep.storefront_style.name.lower()}")
        parts.append(f"door={ep.door_style.name.lower()}")
        parts.append(f"awning={ep.awning_style.name.lower()}")

    return "; ".join(parts)


def clear_directory(path):
    """Remove all files in a directory."""
    if not os.path.exists(path):
        return 0
    count = 0
    for f in os.listdir(path):
        fp = os.path.join(path, f)
        if os.path.isfile(fp):
            os.remove(fp)
            count += 1
    return count


def main():
    # Clear existing files
    for cat in CATEGORIES:
        cat_dir = os.path.join(REVIEW_DIR, cat)
        n_removed = clear_directory(cat_dir)
        os.makedirs(cat_dir, exist_ok=True)
        if n_removed:
            print(f"  Cleared {n_removed} files from {cat}/")

    # Clear root review PNGs
    n_root = clear_directory_pngs(REVIEW_DIR)
    if n_root:
        print(f"  Cleared {n_root} PNGs from review/")

    # Generate per category
    for cat in CATEGORIES:
        preset = cat.upper()
        cat_dir = os.path.join(REVIEW_DIR, cat)
        rng = random.Random(2026)

        rows = []
        for i in range(N):
            seed = rng.randint(0, 99999)
            variation = round(rng.uniform(0.0, 1.0), 2)

            if preset == "BOULEVARD":
                lot_width = round(rng.uniform(16.0, 24.0), 1)
            elif preset == "RESIDENTIAL":
                lot_width = round(rng.uniform(11.0, 18.0), 1)
            else:
                lot_width = round(rng.uniform(7.0, 12.0), 1)

            config = BuildingConfig(
                style_preset=preset,
                seed=seed,
                lot_width=lot_width,
                profile_variation=variation,
            )
            building = generate_building(config)
            svg_str = render_svg(building, show_labels=False)

            base = f"{i:03d}_s{seed}_v{variation:.2f}"
            svg_path = os.path.join(cat_dir, f"{base}.svg")
            png_path = os.path.join(cat_dir, f"{base}.png")

            with open(svg_path, "w") as f:
                f.write(svg_str)

            subprocess.run(
                ["rsvg-convert", "-o", png_path, svg_path],
                check=True,
            )

            desc = describe_building(building, config)
            rows.append({
                "filename": f"{base}.png",
                "seed": seed,
                "variation": variation,
                "lot_width": lot_width,
                "description": desc,
            })

            if (i + 1) % 32 == 0:
                print(f"  {preset}: {i + 1}/{N}")

        # Write CSV
        csv_path = os.path.join(cat_dir, "review.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["filename", "seed", "variation", "lot_width", "description"])
            writer.writeheader()
            writer.writerows(rows)

        print(f"  {preset}: {N} buildings -> {cat}/")

    print("\nDone!")


def clear_directory_pngs(path):
    """Remove only PNG files from a directory (not subdirs)."""
    if not os.path.exists(path):
        return 0
    count = 0
    for f in os.listdir(path):
        fp = os.path.join(path, f)
        if os.path.isfile(fp) and f.endswith(".png"):
            os.remove(fp)
            count += 1
    return count


if __name__ == "__main__":
    main()
