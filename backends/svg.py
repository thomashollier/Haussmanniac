"""Simple SVG renderer for Haussmann building facades.

Produces a 2D elevation drawing of one or more facades as an SVG file.
Useful for quick visualization and validation of the IR tree before
committing to full 3D backends (Blender, USD).

Usage::

    from core.generator import generate_building
    from core.types import BuildingConfig
    from backends.svg import render_svg

    building = generate_building(BuildingConfig(seed=42, style_preset="BOULEVARD"))
    svg = render_svg(building)
    with open("facade.svg", "w") as f:
        f.write(svg)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.types import (
    BalconyNode,
    BayNode,
    BayType,
    BuildingNode,
    ChimneyNode,
    CorniceNode,
    CustomBayStyle,
    DormerNode,
    FacadeNode,
    FloorNode,
    FloorType,
    GroundFloorNode,
    IRNode,
    MansardSlopeNode,
    MansardType,
    OrnamentLevel,
    OrnamentNode,
    Orientation,
    PedimentStyle,
    PilasterNode,
    PorteStyle,
    RoofNode,
    StoreType,
    StringCourseNode,
    SurroundStyle,
    WindowNode,
)


# ---------------------------------------------------------------------------
# Colour palette — Haussmann cream stone, zinc grey, iron black
# ---------------------------------------------------------------------------

COLORS = {
    "wall": "#E8DCC8",           # Warm cream limestone
    "wall_ground": "#D4C9B5",    # Slightly darker for rustication
    "window": "#4A6078",         # Dark glass
    "window_frame": "#8B8070",   # Stone frame
    "surround_molded": "#D8CCBA",
    "surround_pilastered": "#C8B8A0",
    "balcony_rail": "#2C2C2C",   # Cast iron
    "balcony_floor": "#5A5A5A",
    "cornice": "#C0B49E",
    "cornice_stroke": "#6B5B4C",     # Dark brown — all cornice/slab outlines
    "string_course": "#D8CDB8",
    "roof_zinc": "#7A8088",      # Zinc grey
    "roof_slope": "#6A7078",
    "dormer": "#888E96",
    "dormer_window": "#4A6078",
    "chimney": "#A09080",
    "pediment": "#C8B8A0",
    "keystone": "#B8A890",
    "ornament": "#C0B098",
    "door": "#5A4030",           # Dark wood — porte-cochère
    "shop_door": "#6B5040",      # Shop entrance — lighter than porte-cochère
    "awning": "#96BF93",         # Awning — desaturated green, 75% brightness
    "awning_stripe": "#A8CCA5",  # Awning stripe highlight
    "terrace_rail": "#3A3A3A",   # Low terrace railing
    "signage_band": "#D0C4AE",   # Signage area above shopfront
    "pier": "#DDD4C4",           # Interior pier fill
    "pier_edge": "#DDD4C4",     # Edge pier fill — same as interior piers
    "pier_line": "#C0B4A0",     # Pier outline
    "sky": "#D6E8F0",
    "ground": "#8A9A7A",
    "outline": "#4A4038",
}

# SVG scale: 1 metre = N pixels
SCALE = 40


@dataclass
class SVGContext:
    """Tracks drawing state and accumulates SVG elements."""
    elements: list[str]
    scale: float = SCALE
    x_origin: float = 0.0   # Pixel offset for this facade
    y_origin: float = 0.0   # Pixel offset (bottom of facade)

    def px(self, metres: float) -> float:
        return metres * self.scale

    def x(self, m: float) -> float:
        return self.x_origin + self.px(m)

    def y(self, m: float, from_top: float = 0.0) -> float:
        """Convert metres-from-ground to SVG y (top-down)."""
        return self.y_origin - self.px(m)

    def rect(self, x_m, y_m, w_m, h_m, fill, stroke=None, stroke_w=0.5, rx=0, opacity=1.0):
        sx, sw, sh = self.x(x_m), self.px(w_m), self.px(h_m)
        sy = self.y(y_m + h_m)  # SVG y is top of rect
        s = stroke or COLORS["outline"]
        extra = f' rx="{rx}"' if rx else ""
        extra += f' opacity="{opacity}"' if opacity < 1.0 else ""
        self.elements.append(
            f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{sw:.1f}" height="{sh:.1f}" '
            f'fill="{fill}" stroke="{s}" stroke-width="{stroke_w}"{extra}/>'
        )

    def line(self, x1_m, y1_m, x2_m, y2_m, stroke=None, stroke_w=1.0):
        s = stroke or COLORS["outline"]
        self.elements.append(
            f'<line x1="{self.x(x1_m):.1f}" y1="{self.y(y1_m):.1f}" '
            f'x2="{self.x(x2_m):.1f}" y2="{self.y(y2_m):.1f}" '
            f'stroke="{s}" stroke-width="{stroke_w}"/>'
        )

    def polygon(self, points_m: list[tuple[float, float]], fill, stroke=None, stroke_w=0.5):
        s = stroke or COLORS["outline"]
        pts = " ".join(f"{self.x(px):.1f},{self.y(py):.1f}" for px, py in points_m)
        self.elements.append(
            f'<polygon points="{pts}" fill="{fill}" stroke="{s}" stroke-width="{stroke_w}"/>'
        )

    def text(self, x_m, y_m, label, size=10, fill="#666"):
        self.elements.append(
            f'<text x="{self.x(x_m):.1f}" y="{self.y(y_m):.1f}" '
            f'font-family="sans-serif" font-size="{size}" fill="{fill}" '
            f'text-anchor="middle">{label}</text>'
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_svg(
    building: BuildingNode,
    facade_filter: Orientation | None = None,
    show_labels: bool = True,
    show_layout_lines: bool = False,
    margin_m: float = 2.0,
) -> str:
    """Render the building's facades as an SVG string.

    By default renders only the front (SOUTH) facade.  Pass
    ``facade_filter=None`` and it renders the first facade,
    or pass a specific Orientation.

    Args:
        building: The IR tree root node.
        facade_filter: Which facade orientation to render, or None for front.
        show_labels: Annotate floors and dimensions.
        margin_m: Margin around the drawing in metres.

    Returns:
        Complete SVG document as a string.
    """
    facades = [c for c in building.children if isinstance(c, FacadeNode)]
    roof = next((c for c in building.children if isinstance(c, RoofNode)), None)

    if facade_filter:
        facades = [f for f in facades if f.orientation == facade_filter]
    else:
        # Default: front facade only
        facades = facades[:1]

    if not facades:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>'

    facade = facades[0]

    # Compute total height (sum floor heights + roof)
    total_h = _facade_height(facade)
    roof_h = 0.0
    if roof:
        slopes = [c for c in roof.children if isinstance(c, MansardSlopeNode)]
        if slopes:
            roof_h = slopes[0].height

    draw_h = total_h + roof_h
    facade_w = facade.width

    canvas_w = (facade_w + margin_m * 2) * SCALE
    canvas_h = (draw_h + margin_m * 3) * SCALE  # Extra margin for ground + sky

    ctx = SVGContext(
        elements=[],
        x_origin=margin_m * SCALE,
        y_origin=(draw_h + margin_m * 1.5) * SCALE,
    )

    # -- Background ---
    ctx.elements.append(
        f'<rect x="0" y="0" width="{canvas_w:.0f}" height="{canvas_h:.0f}" fill="{COLORS["sky"]}"/>'
    )
    # Ground plane
    ground_y = ctx.y(0)
    ctx.elements.append(
        f'<rect x="0" y="{ground_y:.0f}" width="{canvas_w:.0f}" '
        f'height="{margin_m * 1.5 * SCALE:.0f}" fill="{COLORS["ground"]}"/>'
    )

    # -- Wall background ---
    ctx.rect(0, 0, facade_w, total_h, COLORS["wall"], stroke_w=1.0)

    # -- Render floors ---
    for child in facade.children:
        if isinstance(child, GroundFloorNode):
            _draw_ground_floor(ctx, child, facade_w, show_labels)
            if show_layout_lines:
                bays = [c for c in child.children if isinstance(c, BayNode)]
                _draw_layout_lines(ctx, bays, 0.0, child.height, facade_w)
        elif isinstance(child, FloorNode):
            _draw_upper_floor(ctx, child, facade_w, show_labels)
            if show_layout_lines:
                bays = [c for c in child.children if isinstance(c, BayNode)]
                _draw_layout_lines(ctx, bays, child.y_offset, child.height, facade_w)
        elif isinstance(child, CorniceNode):
            _draw_cornice(ctx, child)

    # -- Render roof (starts above the roofline cornice band) ---
    if roof:
        cornice_band_h = 0.20  # roofline cornice visual height
        _draw_roof(ctx, roof, facade_w, total_h + cornice_band_h, roof_h)

    # -- Dimension labels ---
    if show_labels:
        _draw_dimensions(ctx, facade, total_h, roof_h)

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{canvas_w:.0f}" height="{canvas_h:.0f}" '
        f'viewBox="0 0 {canvas_w:.0f} {canvas_h:.0f}">\n'
        f'<style>text {{ font-family: "Helvetica Neue", Arial, sans-serif; }}</style>\n'
    )
    svg += "\n".join(ctx.elements)
    svg += "\n</svg>"
    return svg


# ---------------------------------------------------------------------------
# Floor renderers
# ---------------------------------------------------------------------------

def _draw_ground_floor(ctx: SVGContext, node: GroundFloorNode, facade_w: float, labels: bool):
    """Draw the ground floor: rusticated wall + shopfronts/door."""
    y0 = 0.0
    h = node.height

    # Rusticated wall background
    if node.has_rustication:
        _draw_rustication(ctx, 0, y0, facade_w, h)

    # Collect bays
    bays = [child for child in node.children if isinstance(child, BayNode)]

    # Identify store groups (drawn as continuous openings)
    cafe_groups = _find_store_groups(bays, StoreType.CAFE)
    boutique_groups = _find_store_groups(bays, StoreType.BOUTIQUE)
    group_bay_ids: set[int] = set()
    for group in cafe_groups + boutique_groups:
        for bay in group:
            group_bay_ids.add(id(bay))

    # Draw non-grouped bays individually (skip ground floor cornice)
    for child in node.children:
        if isinstance(child, BayNode):
            if id(child) not in group_bay_ids:
                _draw_ground_bay(ctx, child, y0, h)

    # Vertical pier lines between bays
    _draw_pier_lines(ctx, bays, y0, h, facade_w)

    # Store groups drawn last — span across pier lines between their bays
    for group in cafe_groups:
        _draw_cafe_group(ctx, group, y0, h)
    for group in boutique_groups:
        _draw_boutique_group(ctx, group, y0, h)

    # Strong cornice between ground floor and entresol
    cornice_h = 0.15
    cornice_y = y0 + h - cornice_h
    ctx.rect(0, cornice_y, facade_w, cornice_h, COLORS["cornice"],
             stroke=COLORS["cornice_stroke"], stroke_w=0.3)
    # Dentils below cornice
    dentil_w = 0.06
    dentil_h = 0.05
    spacing = 0.12
    n = int(facade_w / spacing)
    for i in range(n):
        dx = i * spacing + spacing / 2
        ctx.rect(dx, cornice_y - dentil_h, dentil_w, dentil_h, COLORS["cornice"],
                 stroke=COLORS["cornice_stroke"], stroke_w=0.3)
    # Strong line at top
    ctx.line(0, y0 + h, facade_w, y0 + h, COLORS["outline"], 1.5)

    if labels:
        ctx.text(-0.8, y0 + h / 2, "RDC", size=9, fill="#888")


def _draw_upper_floor(ctx: SVGContext, node: FloorNode, facade_w: float, labels: bool):
    """Draw an upper floor: wall band + bays + balconies."""
    y0 = node.y_offset
    h = node.height

    # Floor separation line at the bottom of this floor
    ctx.line(0, y0, facade_w, y0, COLORS["outline"], 0.6)

    # Continuous balcony (drawn AFTER bays so it overlaps — see below)
    has_continuous = False
    for child in node.children:
        if isinstance(child, BalconyNode) and child.is_continuous:
            has_continuous = True

    # Bays
    bays = [child for child in node.children if isinstance(child, BayNode)]
    for child in node.children:
        if isinstance(child, BayNode):
            _draw_upper_bay(ctx, child, y0, h, node)

    # Vertical pier lines between bays
    _draw_pier_lines(ctx, bays, y0, h, facade_w)

    # String course at the floor boundary — redraw on top of piers
    sc_band_h = 0.12
    ctx.rect(0, y0 - sc_band_h / 2, facade_w, sc_band_h,
             COLORS["string_course"], stroke=COLORS["string_course"], stroke_w=0.0)
    ctx.line(0, y0 - sc_band_h / 2, facade_w, y0 - sc_band_h / 2, "#A09888", 0.8)
    ctx.line(0, y0 + sc_band_h / 2, facade_w, y0 + sc_band_h / 2, "#C8BCA8", 0.4)

    # 5th floor gets a prominent intermediate cornice at its base (top of 4th)
    # Drawn here (after 5th floor piers) so it paints over the edge pier fills.
    if node.floor_type == FloorType.FIFTH:
        _draw_intermediate_cornice(ctx, y0, facade_w)




    # Continuous balcony drawn last so it's in front of everything
    if has_continuous:
        for child in node.children:
            if isinstance(child, BalconyNode) and child.is_continuous:
                _draw_continuous_balcony(ctx, child, y0, facade_w, bays)

    if labels:
        ft_name = node.floor_type.name.capitalize()
        ctx.text(-0.8, y0 + h / 2, ft_name, size=9, fill="#888")


# ---------------------------------------------------------------------------
# Bay renderers
# ---------------------------------------------------------------------------

def _draw_ground_bay(ctx: SVGContext, bay: BayNode, floor_y: float, floor_h: float):
    """Draw a single ground-floor bay (shopfront, door, or residential window)."""
    # Custom ground bay: draw as narrow residential window
    if bay.bay_type == BayType.CUSTOM:
        for child in bay.children:
            if isinstance(child, WindowNode):
                win_x = bay.x_offset + (bay.width - child.width) / 2
                win_y = floor_y + child.transform.position[1]
                _draw_window(ctx, child, win_x, win_y, bay.width)
        return

    for child in bay.children:
        if isinstance(child, WindowNode):
            win_x = bay.x_offset + (bay.width - child.width) / 2
            win_y = floor_y + child.transform.position[1]

            if bay.bay_type == BayType.DOOR:
                if bay.porte_style == PorteStyle.FLAT:
                    _draw_flat_opening(ctx, win_x, win_y, child.width, child.height,
                                       COLORS["door"])
                else:
                    _draw_arched_opening(ctx, win_x, win_y, child.width, child.height,
                                         COLORS["door"])
            elif bay.bay_type == BayType.WINDOW:
                # Residential window — standard upper-floor style
                _draw_window(ctx, child, win_x, win_y, bay.width)
            else:
                # Fallback for shopfront bays not in a group
                ctx.rect(win_x, win_y, child.width, child.height,
                         COLORS["window"], stroke_w=1.0)

        elif isinstance(child, OrnamentNode):
            if "keystone" in child.ornament_id:
                kx = bay.x_offset + bay.width / 2
                ky = floor_y + child.transform.position[1]
                _draw_keystone(ctx, kx, ky)


def _find_store_groups(bays: list[BayNode], store_type: StoreType) -> list[list[BayNode]]:
    """Return lists of consecutive bays matching the given store type."""
    groups: list[list[BayNode]] = []
    current: list[BayNode] = []
    for bay in bays:
        if bay.store_type == store_type:
            current.append(bay)
        else:
            if current:
                groups.append(current)
                current = []
    if current:
        groups.append(current)
    return groups


def _draw_boutique_group(ctx: SVGContext, group: list[BayNode], floor_y: float, floor_h: float):
    """Draw a boutique as one continuous display window spanning all bays.

    The window sill sits at 1.0 m above ground.  At the entry bay, a
    centered shop door runs from ground to the window top.  A continuous
    awning matches the cafe style.
    """
    first, last = group[0], group[-1]

    # Window spans the full width of all bays in the group
    win_x = first.x_offset
    win_w = (last.x_offset + last.width) - win_x
    sill = 0.50
    win_y = floor_y + sill
    win_h = floor_h * 0.70 - sill

    # Entry bay door — drawn first so storefront window paints over the top portion
    entry_bay = next((b for b in group if b.is_store_entry), None)
    if entry_bay:
        win_child = next((c for c in entry_bay.children if isinstance(c, WindowNode)), None)
        door_w = win_child.width if win_child else entry_bay.width * 0.45
        door_x = entry_bay.x_offset + (entry_bay.width - door_w) / 2
        door_top = win_y + win_h

        # Door panel (same color as windows, ground to window top)
        ctx.rect(door_x, floor_y, door_w, door_top - floor_y,
                 COLORS["window"], stroke_w=1.0)
        # Door handle
        ctx.rect(door_x + door_w * 0.75, floor_y + (door_top - floor_y) * 0.5,
                 0.04, 0.08, COLORS["window_frame"], stroke_w=0.3)

    # Continuous display window — drawn on top of door
    ctx.rect(win_x, win_y, win_w, win_h, COLORS["window"], stroke_w=1.0)

    # Single transom at 80% of window height
    transom_y = win_y + win_h * 0.8
    ctx.line(win_x, transom_y, win_x + win_w, transom_y,
             COLORS["window_frame"], 0.8)

    # Continuous awning
    awning_h = 0.30
    awning_proj = 0.06
    awning_y = win_y + win_h
    ctx.rect(win_x - awning_proj, awning_y, win_w + awning_proj * 2, awning_h,
             COLORS["awning"], stroke_w=0.6)


def _draw_cafe_group(ctx: SVGContext, group: list[BayNode], floor_y: float, floor_h: float):
    """Draw a cafe as one continuous opening spanning all bays in the group.

    Renders a single wide glass expanse from ground level to a lintel lower
    than the porte-cochère, with one continuous deep-red awning above.
    No mullions — suggests a wide open terrace interior.
    """
    first, last = group[0], group[-1]

    # Opening spans the full width of all bays in the group
    open_x = first.x_offset
    open_w = (last.x_offset + last.width) - open_x

    # Sill at ground level, top lower than porte-cochère
    open_y = floor_y
    open_h = floor_h * 0.70

    # One continuous glass opening — no mullions
    ctx.rect(open_x, open_y, open_w, open_h, COLORS["window"], stroke_w=1.0)

    # Continuous awning
    awning_h = 0.30
    awning_proj = 0.06
    awning_y = open_y + open_h
    ctx.rect(open_x - awning_proj, awning_y, open_w + awning_proj * 2, awning_h,
             COLORS["awning"], stroke_w=0.6)


def _draw_upper_bay(ctx: SVGContext, bay: BayNode, floor_y: float, floor_h: float, floor_node: FloorNode):
    """Draw a single upper-floor bay with window, balconette, pilasters, pediment."""
    # Custom bay rendering
    if bay.custom_bay_style is not None:
        _draw_custom_upper_bay(ctx, bay, floor_y, floor_h)
        return

    win_surround_pad = 0.0
    for child in bay.children:
        if isinstance(child, WindowNode):
            win_x = bay.x_offset + (bay.width - child.width) / 2
            win_y = floor_y + child.transform.position[1]
            # Omit bottom border only when window sits on a continuous balcony
            has_continuous = any(
                isinstance(c, BalconyNode) and c.is_continuous
                for c in floor_node.children
            )
            win_surround_pad = _draw_window(ctx, child, win_x, win_y, bay.width,
                                            omit_bottom=has_continuous)

        elif isinstance(child, BalconyNode) and not child.is_continuous:
            bal_x = bay.x_offset
            bal_y = floor_y + child.transform.position[1]
            _draw_balconette(ctx, child, bal_x, bal_y)

        elif isinstance(child, PilasterNode):
            pil_x = bay.x_offset + bay.width / 2 + child.transform.position[0]
            pil_y = floor_y
            _draw_pilaster(ctx, child, pil_x, pil_y)

        elif isinstance(child, OrnamentNode):
            if "pediment" in child.ornament_id:
                ped_x = bay.x_offset
                ped_y = floor_y + child.transform.position[1] + win_surround_pad
                style = child.ornament_id.replace("pediment_", "")
                _draw_pediment(ctx, ped_x, ped_y, bay.width, style)


def _draw_custom_upper_bay(ctx: SVGContext, bay: BayNode, floor_y: float, floor_h: float):
    """Draw a custom bay: porthole, narrow window, or ornament medallion."""
    style = bay.custom_bay_style

    if style == CustomBayStyle.PORTHOLE:
        # Circular window centered in bay
        for child in bay.children:
            if isinstance(child, WindowNode):
                diameter = child.width  # width == height for porthole
                cx = bay.x_offset + bay.width / 2
                cy = floor_y + child.transform.position[1] + diameter / 2

                # Surround ring
                pad = 0.04
                steps = 24
                surround_pts = []
                for i in range(steps + 1):
                    angle = 2 * math.pi * i / steps
                    surround_pts.append((
                        cx + (diameter / 2 + pad) * math.cos(angle),
                        cy + (diameter / 2 + pad) * math.sin(angle),
                    ))
                ctx.polygon(surround_pts, COLORS["surround_molded"], stroke_w=0.6)

                # Glass circle
                glass_pts = []
                for i in range(steps + 1):
                    angle = 2 * math.pi * i / steps
                    glass_pts.append((
                        cx + (diameter / 2) * math.cos(angle),
                        cy + (diameter / 2) * math.sin(angle),
                    ))
                ctx.polygon(glass_pts, COLORS["window"], stroke_w=0.5)

                # Cross mullion
                r = diameter / 2
                ctx.line(cx - r, cy, cx + r, cy, COLORS["window_frame"], 0.4)
                ctx.line(cx, cy - r, cx, cy + r, COLORS["window_frame"], 0.4)

    elif style == CustomBayStyle.NARROW_WINDOW:
        # Narrow rectangular window — reuse standard _draw_window
        for child in bay.children:
            if isinstance(child, WindowNode):
                win_x = bay.x_offset + (bay.width - child.width) / 2
                win_y = floor_y + child.transform.position[1]
                _draw_window(ctx, child, win_x, win_y, bay.width)

    elif style == CustomBayStyle.STONEWORK:
        # Rusticated stone panel with horizontal coursing lines
        panel_w = bay.width * 0.80
        panel_h = floor_h * 0.55
        panel_x = bay.x_offset + (bay.width - panel_w) / 2
        panel_y = floor_y + (floor_h - panel_h) / 2
        ctx.rect(panel_x, panel_y, panel_w, panel_h, COLORS["ornament"], stroke_w=0.6)
        # 3-4 horizontal coursing lines (rustication bands)
        n_courses = max(3, int(panel_h / 0.25))
        course_h = panel_h / (n_courses + 1)
        for i in range(1, n_courses + 1):
            ly = panel_y + i * course_h
            ctx.line(panel_x, ly, panel_x + panel_w, ly, "#A89880", 0.5)

    elif style == CustomBayStyle.GEOMETRIC:
        # Diamond (rotated square) inscribed in bay — classic Haussmann stone relief
        cx = bay.x_offset + bay.width / 2
        cy = floor_y + floor_h * 0.5
        r = min(bay.width, floor_h) * 0.25
        # Outer diamond
        pts = [
            (cx, cy + r),       # top
            (cx + r, cy),       # right
            (cx, cy - r),       # bottom
            (cx - r, cy),       # left
        ]
        ctx.polygon(pts, COLORS["ornament"], stroke_w=0.6)
        # Inner diamond outline (smaller)
        ri = r * 0.6
        inner_pts = [
            (cx, cy + ri),
            (cx + ri, cy),
            (cx, cy - ri),
            (cx - ri, cy),
        ]
        ctx.polygon(inner_pts, COLORS["wall"], stroke=COLORS["ornament"], stroke_w=0.5)


# ---------------------------------------------------------------------------
# Pier lines (vertical structure between bays)
# ---------------------------------------------------------------------------

def _draw_pier_lines(ctx: SVGContext, bays: list, floor_y: float, floor_h: float, facade_w: float = 0.0):
    """Draw bay piers and edge piers.

    **Bay piers** are the gaps between adjacent bay windows — each bay
    contributes half a pier on each side, so adjacent halves merge into
    one full bay pier.

    **Edge piers** sit between the outermost bays and the facade edges,
    providing a buffer to the party walls.  Drawn in a distinct colour.
    """
    if not bays:
        return

    def _draw_one_pier(left_x: float, right_x: float, is_edge: bool = False):
        w = right_x - left_x
        if w > 0.05:
            line_color = COLORS["pier_line"]
            fill = COLORS["pier_edge"] if is_edge else COLORS["pier"]
            ctx.line(left_x, floor_y, left_x, floor_y + floor_h, line_color, 0.4)
            ctx.line(right_x, floor_y, right_x, floor_y + floor_h, line_color, 0.4)
            ctx.rect(left_x, floor_y, w, floor_h,
                     fill, stroke=COLORS["wall"], stroke_w=0.0)

    # Left edge pier (facade edge to first bay window)
    first_left = bays[0].x_offset
    if first_left > 0.05:
        _draw_one_pier(0, first_left, is_edge=True)

    # Bay piers (between adjacent bay windows)
    for i in range(len(bays) - 1):
        right = bays[i].x_offset + bays[i].width
        left = bays[i + 1].x_offset
        _draw_one_pier(right, left)

    # Right edge pier (last bay window to facade edge)
    if facade_w > 0:
        last_right = bays[-1].x_offset + bays[-1].width
        if facade_w - last_right > 0.05:
            _draw_one_pier(last_right, facade_w, is_edge=True)


# Layout debug lines
# ---------------------------------------------------------------------------

# Colours for each layout element — distinct and saturated for visibility
_LAYOUT_COLORS = {
    "edge_pier":  "#4477CC",   # Blue — edge piers
    "bay_pier":   "#CC4444",   # Red — bay piers
    "bay_window": "#44AA44",   # Green — bay windows
    "bay":        "#DDAA22",   # Gold — full bay extent
}

_LAYOUT_LINE_W = 1.5   # stroke width in SVG units


def _draw_layout_lines(
    ctx: SVGContext,
    bays: list,
    floor_y: float,
    floor_h: float,
    facade_w: float,
) -> None:
    """Draw thin coloured lines at the bottom of a floor showing layout decomposition.

    Four rows of lines, each a different colour:
      - Gold:  full bay (centerline-to-centerline)
      - Green: bay window (opening between bay piers)
      - Red:   bay piers (gaps between adjacent bay windows)
      - Blue:  edge piers (facade edge to outermost bay window)
    """
    if not bays:
        return

    lw = _LAYOUT_LINE_W
    base_y = floor_y + floor_h  # bottom of the floor

    # Row offsets (stacked upward from floor bottom)
    y_edge = base_y - lw * 0.5
    y_pier = base_y - lw * 1.8
    y_win = base_y - lw * 3.1
    y_bay = base_y - lw * 4.4

    # -- Edge piers (blue) --
    edge_color = _LAYOUT_COLORS["edge_pier"]
    first_x = bays[0].x_offset
    if first_x > 0.05:
        ctx.line(0, y_edge, first_x, y_edge, edge_color, lw)
    last_right = bays[-1].x_offset + bays[-1].width
    if facade_w - last_right > 0.05:
        ctx.line(last_right, y_edge, facade_w, y_edge, edge_color, lw)

    # -- Bay piers (red) — gaps between adjacent bay windows --
    pier_color = _LAYOUT_COLORS["bay_pier"]
    for i in range(len(bays) - 1):
        r = bays[i].x_offset + bays[i].width
        l = bays[i + 1].x_offset
        if l - r > 0.01:
            ctx.line(r, y_pier, l, y_pier, pier_color, lw)

    # -- Bay windows (green) --
    win_color = _LAYOUT_COLORS["bay_window"]
    for b in bays:
        ctx.line(b.x_offset, y_win, b.x_offset + b.width, y_win, win_color, lw)

    # -- Full bays (gold) — from half-pier before to half-pier after --
    bay_color = _LAYOUT_COLORS["bay"]
    if len(bays) >= 2:
        pier_w = bays[1].x_offset - (bays[0].x_offset + bays[0].width)
    else:
        pier_w = 0.0
    half_p = pier_w / 2.0
    for b in bays:
        x0 = b.x_offset - half_p
        x1 = b.x_offset + b.width + half_p
        ctx.line(x0, y_bay, x1, y_bay, bay_color, lw)


# ---------------------------------------------------------------------------
# Element renderers
# ---------------------------------------------------------------------------

def _draw_window(ctx: SVGContext, win: WindowNode, x: float, y: float, bay_w: float,
                 omit_bottom: bool = False) -> float:
    """Draw a window with optional surround. Returns surround_pad used."""
    surround_pad = 0.0
    if win.surround_style == SurroundStyle.PILASTERED:
        surround_pad = 0.05
        if omit_bottom:
            ctx.rect(x - surround_pad, y,
                     win.width + surround_pad * 2, win.height + surround_pad,
                     COLORS["surround_pilastered"], stroke_w=0.8)
        else:
            ctx.rect(x - surround_pad, y - surround_pad,
                     win.width + surround_pad * 2, win.height + surround_pad * 2,
                     COLORS["surround_pilastered"], stroke_w=0.8)
    elif win.surround_style in (SurroundStyle.MOLDED, SurroundStyle.EARED):
        surround_pad = 0.05
        if omit_bottom:
            ctx.rect(x - surround_pad, y,
                     win.width + surround_pad * 2, win.height + surround_pad,
                     COLORS["surround_molded"], stroke_w=0.5)
        else:
            ctx.rect(x - surround_pad, y - surround_pad,
                     win.width + surround_pad * 2, win.height + surround_pad * 2,
                     COLORS["surround_molded"], stroke_w=0.5)

    # Glass
    ctx.rect(x, y, win.width, win.height, COLORS["window"], stroke_w=0.8)

    # Mullion (vertical center bar)
    mid_x = x + win.width / 2
    ctx.line(mid_x, y, mid_x, y + win.height, COLORS["window_frame"], 0.6)

    # Transom (horizontal bar at 60%)
    transom_y = y + win.height * 0.6
    ctx.line(x, transom_y, x + win.width, transom_y, COLORS["window_frame"], 0.6)

    return surround_pad


def _draw_arched_opening(ctx: SVGContext, x: float, y: float, w: float, h: float, fill: str):
    """Draw an arched opening (porte-cochère with semicircular top)."""
    # Rectangular lower portion
    arch_h = w / 2  # Semicircular arch radius = half width
    rect_h = h - arch_h
    ctx.rect(x, y, w, rect_h, fill, stroke_w=1.0)

    # Arch (approximated with a polygon)
    cx = x + w / 2
    cy = y + rect_h
    steps = 12
    pts = [(x, cy)]
    for i in range(steps + 1):
        angle = math.pi * i / steps
        px = cx - (w / 2) * math.cos(angle)
        py = cy + (arch_h) * math.sin(angle)
        pts.append((px, py))
    pts.append((x + w, cy))
    ctx.polygon(pts, fill, stroke_w=1.0)


def _draw_flat_opening(ctx: SVGContext, x: float, y: float, w: float, h: float, fill: str):
    """Draw a flat-topped opening (porte-cochère with lintel)."""
    ctx.rect(x, y, w, h, fill, stroke_w=1.0)


def _draw_pediment(ctx: SVGContext, x: float, y: float, bay_w: float, style: str):
    """Draw a triangular or segmental pediment above a window."""
    ped_w = bay_w * 0.80
    ped_x = x + (bay_w - ped_w) / 2

    if style == "triangular":
        ped_h = 0.20
        pts = [
            (ped_x, y),
            (ped_x + ped_w / 2, y + ped_h),
            (ped_x + ped_w, y),
        ]
        ctx.polygon(pts, COLORS["pediment"], stroke_w=0.8)
    elif style == "segmental":
        ped_h = 0.20
        # Curved pediment — approximate with polygon arc
        pts = [(ped_x, y)]
        steps = 8
        for i in range(steps + 1):
            t = i / steps
            px = ped_x + t * ped_w
            py = y + ped_h * math.sin(t * math.pi)
            pts.append((px, py))
        pts.append((ped_x + ped_w, y))
        ctx.polygon(pts, COLORS["pediment"], stroke_w=0.8)


def _draw_keystone(ctx: SVGContext, cx: float, cy: float):
    """Draw a keystone ornament (trapezoid)."""
    w_top, w_bot, h = 0.12, 0.18, 0.2
    pts = [
        (cx - w_top / 2, cy + h),
        (cx + w_top / 2, cy + h),
        (cx + w_bot / 2, cy),
        (cx - w_bot / 2, cy),
    ]
    ctx.polygon(pts, COLORS["keystone"], stroke_w=0.5)


def _draw_pilaster(ctx: SVGContext, pil: PilasterNode, x: float, y: float):
    """Draw a pilaster (thin vertical strip with optional capital)."""
    ctx.rect(x - pil.width / 2, y, pil.width, pil.height,
             COLORS["surround_pilastered"], stroke_w=0.4)
    if pil.has_capital:
        # Small wider block at top (capital)
        cap_w = pil.width * 1.8
        cap_h = 0.12
        ctx.rect(x - cap_w / 2, y + pil.height - cap_h, cap_w, cap_h,
                 COLORS["cornice"], stroke=COLORS["cornice_stroke"], stroke_w=0.3)


def _draw_intermediate_cornice(ctx: SVGContext, floor_y: float, facade_w: float):
    """Draw the intermediate cornice between 4th and 5th floors.

    A projecting stone ledge with small corbels and a shadow underneath —
    lighter than the roofline cornice but heavier than a string course.
    Divides the facade into corps principal (below) and attique (above).
    """
    slab_h = 0.10
    overhang = 0.06

    # Shadow under the slab
    shadow_h = 0.04
    ctx.rect(-overhang, floor_y - shadow_h, facade_w + overhang * 2, shadow_h,
             "#B0A898", stroke_w=0.0)

    # Small corbels under the slab
    corbel_w = 0.07
    corbel_h = 0.12
    corbel_spacing = 0.50
    n_corbels = int(facade_w / corbel_spacing)
    for i in range(n_corbels + 1):
        cx = i * corbel_spacing
        ctx.polygon([
            (cx - corbel_w * 0.3, floor_y - shadow_h),
            (cx + corbel_w * 0.3, floor_y - shadow_h),
            (cx + corbel_w * 0.5, floor_y - shadow_h - corbel_h),
            (cx - corbel_w * 0.5, floor_y - shadow_h - corbel_h),
        ], COLORS["cornice"], stroke=COLORS["cornice_stroke"], stroke_w=0.3)

    # Stone slab (no stroke — outline drawn separately for clean overhang edges)
    ctx.rect(-overhang, floor_y, facade_w + overhang * 2, slab_h,
             COLORS["cornice"], stroke_w=0.0)
    # Thin dark brown outline around the slab
    ctx.rect(-overhang, floor_y, facade_w + overhang * 2, slab_h, "none",
             stroke=COLORS["cornice_stroke"], stroke_w=0.3)


def _draw_continuous_balcony(ctx: SVGContext, bal: BalconyNode, floor_y: float,
                            facade_w: float, bays: list | None = None):
    """Draw a prominent continuous balcony spanning the bay extent.

    The balcony runs from the left edge of the first bay to the right
    edge of the last bay (plus a small overhang), not the full facade
    width.  This keeps it inside the edge piers.
    """
    slab_h = 0.12
    slab_overhang = 0.15  # Balcony projects slightly past outermost bays

    # Compute balcony span from bay extents (outer edge of half-piers)
    if bays and len(bays) >= 2:
        # Half-pier width = gap between adjacent bay windows / 2
        half_pier = (bays[1].x_offset - (bays[0].x_offset + bays[0].width)) / 2.0
        bal_left = bays[0].x_offset - half_pier
        bal_right = bays[-1].x_offset + bays[-1].width + half_pier
    elif bays:
        bal_left = bays[0].x_offset
        bal_right = bays[0].x_offset + bays[0].width
    else:
        bal_left = 0.0
        bal_right = facade_w
    bal_w = bal_right - bal_left

    span_left = bal_left - slab_overhang
    span_right = bal_right + slab_overhang
    span_w = span_right - span_left

    # Shadow under the slab (suggests depth/projection)
    shadow_h = 0.06
    ctx.rect(span_left, floor_y - shadow_h, span_w, shadow_h,
             "#B0A898", stroke_w=0.0)

    # Corbels / brackets under the slab
    corbel_w = 0.10
    corbel_h = 0.18
    corbel_spacing = 0.6
    n_corbels = int(bal_w / corbel_spacing)
    for i in range(n_corbels + 1):
        cx = bal_left + i * corbel_spacing
        # Trapezoid corbel
        ctx.polygon([
            (cx - corbel_w * 0.3, floor_y - shadow_h),
            (cx + corbel_w * 0.3, floor_y - shadow_h),
            (cx + corbel_w * 0.5, floor_y - shadow_h - corbel_h),
            (cx - corbel_w * 0.5, floor_y - shadow_h - corbel_h),
        ], COLORS["cornice"], stroke=COLORS["cornice_stroke"], stroke_w=0.3)

    # Stone slab
    ctx.rect(span_left, floor_y, span_w, slab_h,
             COLORS["balcony_floor"], stroke=COLORS["cornice_stroke"], stroke_w=0.3)
    # Slab edge line (strong)
    ctx.line(span_left, floor_y + slab_h, span_right,
             floor_y + slab_h, COLORS["outline"], 1.0)

    # Wrought-iron railing
    rail_base = floor_y + slab_h
    rail_h = bal.railing_height

    # Top rail (thick)
    ctx.rect(span_left, rail_base + rail_h - 0.03,
             span_w, 0.03,
             COLORS["balcony_rail"], stroke_w=0.5)
    # Bottom rail
    ctx.line(span_left, rail_base + 0.02,
             span_right, rail_base + 0.02,
             COLORS["balcony_rail"], 0.5)
    # Mid rail
    ctx.line(span_left, rail_base + rail_h * 0.5,
             span_right, rail_base + rail_h * 0.5,
             COLORS["balcony_rail"], 0.3)

    # Vertical bars
    bar_spacing = 0.08
    n_bars = int(span_w / bar_spacing)
    for i in range(n_bars + 1):
        bx = span_left + i * bar_spacing
        ctx.line(bx, rail_base + 0.02, bx, rail_base + rail_h - 0.03,
                 COLORS["balcony_rail"], 0.4)
    # Ensure a post at the far right edge
    ctx.line(span_right, rail_base + 0.02, span_right, rail_base + rail_h - 0.03,
             COLORS["balcony_rail"], 0.4)

    # Decorative scroll circles between bars (every 4th bar)
    for i in range(0, n_bars, 4):
        scx = span_left + i * bar_spacing + bar_spacing * 2
        scy = rail_base + rail_h * 0.3
        r = bar_spacing * 1.2
        ctx.elements.append(
            f'<circle cx="{ctx.x(scx):.1f}" cy="{ctx.y(scy):.1f}" r="{ctx.px(r):.1f}" '
            f'fill="none" stroke="{COLORS["balcony_rail"]}" stroke-width="0.4"/>'
        )


def _draw_balconette(ctx: SVGContext, bal: BalconyNode, x: float, y: float):
    """Draw an individual balconette (small projecting balcony per window).

    Rendered with a small stone slab, a pair of corbels, and a short
    wrought-iron railing with vertical bars.
    """
    overhang = 0.06
    slab_h = 0.07

    # Small corbels under slab
    corbel_h = 0.10
    for cx_off in [bal.width * 0.2, bal.width * 0.8]:
        cx = x + cx_off
        ctx.polygon([
            (cx - 0.04, y),
            (cx + 0.04, y),
            (cx + 0.05, y - corbel_h),
            (cx - 0.05, y - corbel_h),
        ], COLORS["cornice"], stroke=COLORS["cornice_stroke"], stroke_w=0.3)

    # Slab
    ctx.rect(x - overhang, y, bal.width + overhang * 2, slab_h,
             COLORS["balcony_floor"], stroke=COLORS["cornice_stroke"], stroke_w=0.3)

    # Railing — balconette rails are 0.5m, inset 8cm from bay edges
    rail_base = y + slab_h
    rail_h = 0.5
    margin = 0.08
    rail_left = x + margin
    rail_right = x + bal.width - margin
    rail_w = rail_right - rail_left

    # Vertical bars (same spacing & weight as noble floor)
    n_bars = max(3, int(rail_w / 0.08))
    bar_spacing = rail_w / n_bars
    for i in range(n_bars + 1):
        bx = rail_left + i * bar_spacing
        ctx.line(bx, rail_base + 0.02, bx, rail_base + rail_h - 0.03,
                 COLORS["balcony_rail"], 0.4)

    # Top rail (matches noble: rect with 0.03 height, stroke 0.5)
    ctx.rect(rail_left, rail_base + rail_h - 0.03,
             rail_w, 0.03,
             COLORS["balcony_rail"], stroke_w=0.5)
    # Bottom rail (matches noble: stroke 0.5)
    ctx.line(rail_left, rail_base + 0.02,
             rail_right, rail_base + 0.02,
             COLORS["balcony_rail"], 0.5)
    # Mid rail (matches noble: stroke 0.3)
    ctx.line(rail_left, rail_base + rail_h * 0.5,
             rail_right, rail_base + rail_h * 0.5,
             COLORS["balcony_rail"], 0.3)


def _draw_cornice(ctx: SVGContext, node: CorniceNode):
    """Draw a horizontal cornice band."""
    y = node.transform.position[1]
    h = max(0.08, node.projection * 0.5)
    overhang = 0.10  # 10cm past facade edges

    # Shadow under the slab
    shadow_h = 0.04
    ctx.rect(-overhang, y - shadow_h, node.width + overhang * 2, shadow_h,
             "#B0A898", stroke_w=0.0)

    if node.has_modillions:
        # Modillions (larger brackets) — spaced to follow the bay rhythm.
        # Dentils are suppressed when modillions are present to avoid clashing.
        mod_w = 0.10
        mod_h = 0.08
        spacing = 0.50  # 4 per 2.0m bay
        n = int(node.width / spacing)
        for i in range(n + 1):
            mx = i * spacing
            ctx.rect(mx - mod_w / 2, y - shadow_h - mod_h, mod_w, mod_h,
                     COLORS["cornice"], stroke=COLORS["cornice_stroke"], stroke_w=0.3)
    elif node.has_dentils:
        # Dentils only (no modillions)
        dentil_w = 0.06
        dentil_h = 0.04
        spacing = 0.12
        n = int((node.width + overhang * 2) / spacing)
        for i in range(n):
            dx = -overhang + i * spacing + spacing / 2
            ctx.rect(dx, y - shadow_h - dentil_h, dentil_w, dentil_h,
                     COLORS["cornice"], stroke=COLORS["cornice_stroke"], stroke_w=0.3)

    # Stone slab (no stroke — outline drawn separately for clean overhang edges)
    ctx.rect(-overhang, y, node.width + overhang * 2, h, COLORS["cornice"], stroke_w=0.0)
    # Thin dark brown outline around the slab
    ctx.rect(-overhang, y, node.width + overhang * 2, h, "none",
             stroke=COLORS["cornice_stroke"], stroke_w=0.3)


def _draw_string_course(ctx: SVGContext, node: StringCourseNode, floor_y: float = 0.0):
    """Draw a horizontal string course / floor band.

    Rendered as a visible horizontal band with a slight shadow line below
    to emphasize the floor separation.
    """
    y = floor_y + node.transform.position[1]
    band_h = max(0.08, node.height * 2)  # Make it visually substantial
    ctx.rect(0, y, node.width, band_h, COLORS["string_course"], stroke_w=0.5)
    # Strong line at bottom edge (shadow)
    ctx.line(0, y, node.width, y, "#A09888", 0.8)
    # Fine line at top edge
    ctx.line(0, y + band_h, node.width, y + band_h, "#C8BCA8", 0.4)


def _draw_rustication(ctx: SVGContext, x: float, y: float, w: float, h: float):
    """Draw rusticated stonework (horizontal grooves)."""
    ctx.rect(x, y, w, h, COLORS["wall_ground"], stroke_w=0.5)
    # Horizontal rustication lines
    course_h = 0.3
    n_courses = int(h / course_h)
    for i in range(1, n_courses):
        ly = y + i * course_h
        ctx.line(x, ly, x + w, ly, "#B8A898", 0.4)


# ---------------------------------------------------------------------------
# Roof renderer
# ---------------------------------------------------------------------------

def _draw_roof(ctx: SVGContext, roof: RoofNode, facade_w: float, cornice_h: float, roof_h: float):
    """Draw the mansard roof with dormers and chimneys.

    Renders three distinct profiles:
    - STEEP:   Near-vertical face (tiny inset), almost a wall with dormers.
    - BROKEN:  Steep lower section + flatter upper section, angle break visible.
    - SHALLOW: Gentle single slope, no dormers.
    """
    # Get the front slope (first child) to read mansard_type
    front_slope = None
    for child in roof.children:
        if isinstance(child, MansardSlopeNode):
            front_slope = child
            break

    if front_slope is None:
        return

    mansard_type = front_slope.mansard_type
    lower_angle = front_slope.lower_angle
    upper_angle = front_slope.upper_angle
    break_pct = front_slope.break_pct

    # Party-wall chimneys behind the roof (drawn first so mansard covers their base)
    for child in roof.children:
        if isinstance(child, ChimneyNode) and not child.is_ridge:
            cx = child.transform.position[0]
            cy = cornice_h + child.transform.position[1]
            _draw_chimney(ctx, child, cx, cy)

    roof_overhang = 0.05  # roof extends 5cm past facade walls
    roof_w = facade_w + roof_overhang * 2
    # Shift x origin so the roof is centered over the facade
    ctx.x_origin -= ctx.px(roof_overhang)
    if mansard_type == MansardType.STEEP:
        _draw_steep_mansard(ctx, roof_w, cornice_h, roof_h, lower_angle)
    elif mansard_type == MansardType.BROKEN:
        _draw_broken_mansard(ctx, roof_w, cornice_h, roof_h, lower_angle, upper_angle, break_pct)
    else:
        _draw_shallow_mansard(ctx, roof_w, cornice_h, roof_h, lower_angle)
    ctx.x_origin += ctx.px(roof_overhang)  # restore

    # Ridge chimneys on top of the mansard (drawn after roof, before dormers)
    for child in roof.children:
        if isinstance(child, ChimneyNode) and child.is_ridge:
            cx = child.transform.position[0]
            cy = cornice_h + child.transform.position[1]
            _draw_chimney(ctx, child, cx, cy)

    # Dormers in front of the roof
    for child in roof.children:
        if isinstance(child, DormerNode):
            dx = child.transform.position[0]
            dy = cornice_h + child.transform.position[1]
            _draw_dormer(ctx, child, dx, dy)


def _draw_steep_mansard(ctx: SVGContext, w: float, y0: float, h: float, angle: float):
    """STEEP: Near-vertical lower face — almost a wall. Tiny horizontal inset.

    Profile (front elevation):
        ____________________
       /                    \     <- very thin flat cap
      |                      |    <- near-vertical zinc face (dormer zone)
      |______________________|   <- cornice line
    """
    inset = h / math.tan(angle) if angle else 0.1
    # Main steep face — nearly rectangular
    pts = [
        (0, y0),
        (inset, y0 + h),
        (w - inset, y0 + h),
        (w, y0),
    ]
    ctx.polygon(pts, COLORS["roof_zinc"], stroke_w=0.6)
    # Zinc seam lines (vertical on steep mansards)
    n_seams = 8
    for i in range(1, n_seams):
        sx = i * w / n_seams
        top_sx = inset + i * (w - 2 * inset) / n_seams
        ctx.line(sx, y0, top_sx, y0 + h, COLORS["roof_slope"], 0.3)


def _draw_broken_mansard(ctx: SVGContext, w: float, y0: float, h: float,
                         lower_angle: float, upper_angle: float, break_pct: float):
    """BROKEN: Two straight segments from cornice to ridge.

    Inputs:
    - lower_angle: angle of the first (steep) segment from horizontal
    - break_pct:   height of the break as a fraction of h (1.0 = single slope)
    - upper_angle: angle of the second (flat) segment from horizontal

    Segment 1 starts at cornice edges and rises steeply to the break point,
    insetting slightly.  Segment 2 picks up from there and angles inward
    at a shallower angle to the ridge.

    Profile (front elevation):
           ______________
          /              \        <- segment 2 (shallow angle)
         /________________\       <- break line at break_pct * h
        |                  |      <- segment 1 (steep angle)
        |__________________|     <- cornice line
    """
    # Segment 1: steep, from cornice (y0) up to break point
    break_h = h * min(break_pct, 1.0)
    inset1 = break_h / math.tan(lower_angle) if lower_angle else 0.1
    break_y = y0 + break_h

    # Segment 1 polygon
    seg1_pts = [
        (0, y0),
        (inset1, break_y),
        (w - inset1, break_y),
        (w, y0),
    ]
    ctx.polygon(seg1_pts, COLORS["roof_zinc"], stroke_w=0.6)

    # Zinc seam lines on segment 1
    n_seams = 8
    for i in range(1, n_seams):
        sx = i * w / n_seams
        top_sx = inset1 + i * (w - 2 * inset1) / n_seams
        ctx.line(sx, y0, top_sx, break_y, COLORS["roof_slope"], 0.3)

    # Segment 2: shallow, from break point up to ridge (skip if break_pct >= 1.0)
    if break_pct < 1.0:
        upper_h = h - break_h
        inset2 = upper_h / math.tan(upper_angle) if upper_angle else 0.5
        # Clamp: ridge must not reach more than 1/4 into the leftover width
        leftover_w = w - 2 * inset1
        max_inset2 = leftover_w * 0.25
        inset2 = max(0.0, min(inset2, max_inset2))
        total_inset = inset1 + inset2

        seg2_pts = [
            (inset1, break_y),
            (total_inset, y0 + h),
            (w - total_inset, y0 + h),
            (w - inset1, break_y),
        ]
        ctx.polygon(seg2_pts, COLORS["roof_slope"], stroke_w=0.6)

        # Break line
        ctx.line(inset1, break_y, w - inset1, break_y, COLORS["outline"], 0.8)


def _draw_shallow_mansard(ctx: SVGContext, w: float, y0: float, h: float, angle: float):
    """SHALLOW: Gentle continuous slope, no dormers.

    Profile (front elevation):
           ________
          /        \          <- single gentle slope (~40°)
         /          \
        /____________\       <- cornice line
    """
    inset = h / math.tan(angle) if angle else 1.5
    pts = [
        (0, y0),
        (inset, y0 + h),
        (w - inset, y0 + h),
        (w, y0),
    ]
    ctx.polygon(pts, COLORS["roof_zinc"], stroke_w=0.6)
    # Horizontal zinc lines
    n_lines = 5
    for i in range(1, n_lines):
        t = i / n_lines
        lx1 = t * inset
        lx2 = w - t * inset
        ly = y0 + t * h
        ctx.line(lx1, ly, lx2, ly, COLORS["roof_slope"], 0.3)


def _draw_dormer(ctx: SVGContext, dormer: DormerNode, cx: float, cy: float):
    """Draw a dormer window on the mansard slope.

    Five styles:
      PEDIMENT_TRIANGLE — rectangular body + triangular pediment cap
      PEDIMENT_CURVED   — rectangular body + curved segmental pediment cap
      POINTY_ROOF       — rectangular body + steep pointed zinc roof
      OVAL              — oeil-de-boeuf: oval stone frame with round window
      FLAT_SLOPE        — rectangular body + low-slope flat zinc cap
    """
    w = dormer.width
    h = dormer.height
    x = cx - w / 2
    style = dormer.style.name

    if style == "OVAL":
        # Oeil-de-boeuf — no rectangular body, just an oval frame + window
        ry = h * 0.40   # vertical radius
        rx = w * 0.45   # horizontal radius
        oy = cy + h * 0.45  # center of oval
        # Stone surround (thicker oval)
        pad = 0.04
        steps = 24
        surround_pts = []
        for i in range(steps + 1):
            angle = 2 * math.pi * i / steps
            px = cx + (rx + pad) * math.cos(angle)
            py = oy + (ry + pad) * math.sin(angle)
            surround_pts.append((px, py))
        ctx.polygon(surround_pts, COLORS["dormer"], stroke_w=0.6)
        # Glass oval
        glass_pts = []
        for i in range(steps + 1):
            angle = 2 * math.pi * i / steps
            px = cx + rx * 0.80 * math.cos(angle)
            py = oy + ry * 0.80 * math.sin(angle)
            glass_pts.append((px, py))
        ctx.polygon(glass_pts, COLORS["dormer_window"], stroke_w=0.5)
        # Cross mullion
        ctx.line(cx - rx * 0.80, oy, cx + rx * 0.80, oy,
                 COLORS["window_frame"], 0.5)
        ctx.line(cx, oy - ry * 0.80, cx, oy + ry * 0.80,
                 COLORS["window_frame"], 0.5)
        return

    if style == "ROUND_SLOPE":
        # Short square dormer with circular window + flat zinc cap
        # Body is 15% smaller but window stays the same size
        # Sits 0.25m higher on the mansard than other dormers
        cy += 0.25
        shrink = 0.85
        dw = w * shrink
        dh = dw  # square aspect ratio
        dx = cx - dw / 2
        body_h = dh
        cap_base_y = cy + body_h
        # Dormer body (stone cheeks)
        ctx.rect(dx, cy, dw, body_h, COLORS["dormer"], stroke_w=0.6)
        # Circular window centered in body (original size)
        oy = cy + body_h * 0.50
        r = w * 0.32
        steps = 24
        # Stone surround
        pad = 0.03
        surround_pts = []
        for i in range(steps + 1):
            angle = 2 * math.pi * i / steps
            surround_pts.append((cx + (r + pad) * math.cos(angle),
                                 oy + (r + pad) * math.sin(angle)))
        ctx.polygon(surround_pts, COLORS["surround_molded"], stroke_w=0.5)
        # Glass
        glass_pts = []
        for i in range(steps + 1):
            angle = 2 * math.pi * i / steps
            glass_pts.append((cx + r * math.cos(angle),
                              oy + r * math.sin(angle)))
        ctx.polygon(glass_pts, COLORS["dormer_window"], stroke_w=0.5)
        # Cross mullion
        ctx.line(cx - r, oy, cx + r, oy, COLORS["window_frame"], 0.4)
        ctx.line(cx, oy - r, cx, oy + r, COLORS["window_frame"], 0.4)
        # Zinc cap — flatter
        cap_h = h * 0.15
        overhang = dw * 0.06
        ctx.rect(dx - overhang, cap_base_y, dw + overhang * 2, cap_h,
                 COLORS["roof_zinc"], stroke_w=0.6)
        return

    # --- Pediment, pointy-roof, and flat-slope styles: rectangular body + rectangular window + cap ---
    # PEDIMENT styles: taller body, narrower window for vertical aspect, sit higher
    if style in ("PEDIMENT_TRIANGLE", "PEDIMENT_CURVED"):
        cy += 0.10  # sit a little higher on the mansard
        body_h = h * 0.78
        win_pad = w * 0.22
        win_top_pad = h * 0.06
    elif style == "FLAT_SLOPE":
        body_h = h * 0.75
        win_pad = w * 0.15
        win_top_pad = h * 0.06
    else:
        body_h = h * 0.65
        win_pad = w * 0.18
        win_top_pad = h * 0.08
    cap_base_y = cy + body_h

    # Dormer body (stone cheeks)
    ctx.rect(x, cy, w, body_h, COLORS["dormer"], stroke_w=0.6)

    # Dormer window
    win_h = body_h - win_top_pad * 2
    ctx.rect(x + win_pad, cy + win_top_pad, w - win_pad * 2, win_h,
             COLORS["dormer_window"], stroke_w=0.5)
    # Mullion
    ctx.line(cx, cy + win_top_pad, cx, cy + win_top_pad + win_h,
             COLORS["window_frame"], 0.4)

    # Cap / roof above the body
    if style == "PEDIMENT_TRIANGLE":
        # Triangular pediment — 10% wider, thin profile
        ped_h = h * 0.15
        overhang = w * 0.13
        pts = [
            (x - overhang, cap_base_y),
            (cx, cap_base_y + ped_h),
            (x + w + overhang, cap_base_y),
        ]
        ctx.polygon(pts, COLORS["dormer"], stroke_w=0.6)
        # Tympanum line (horizontal base of pediment)
        ctx.line(x - overhang, cap_base_y, x + w + overhang, cap_base_y,
                 COLORS["outline"], 0.5)

    elif style == "PEDIMENT_CURVED":
        # Curved segmental pediment — 10% wider, thin profile
        ped_h = h * 0.14
        overhang = w * 0.13
        steps = 16
        pts = [(x - overhang, cap_base_y)]
        for i in range(steps + 1):
            t = i / steps
            px = (x - overhang) + t * (w + overhang * 2)
            py = cap_base_y + ped_h * math.sin(t * math.pi)
            pts.append((px, py))
        pts.append((x + w + overhang, cap_base_y))
        ctx.polygon(pts, COLORS["dormer"], stroke_w=0.6)
        # Tympanum line
        ctx.line(x - overhang, cap_base_y, x + w + overhang, cap_base_y,
                 COLORS["outline"], 0.5)

    elif style == "POINTY_ROOF":
        # Steep pointed roof — front wall extends up into gable, zinc edges
        # visible as a caret (^) from the front elevation
        roof_h = h * 0.45
        overhang = w * 0.05
        # Stone gable wall (dormer face continues up to the peak)
        gable_pts = [
            (x, cap_base_y),
            (cx, cap_base_y + roof_h),
            (x + w, cap_base_y),
        ]
        ctx.polygon(gable_pts, COLORS["dormer"], stroke_w=0.6)
        # Zinc roof edges — caret shape overhanging the gable
        ctx.line(x - overhang, cap_base_y, cx, cap_base_y + roof_h + 0.02,
                 COLORS["roof_zinc"], 1.5)
        ctx.line(cx, cap_base_y + roof_h + 0.02, x + w + overhang, cap_base_y,
                 COLORS["roof_zinc"], 1.5)
        # Ridge finial
        ctx.line(cx, cap_base_y + roof_h, cx, cap_base_y + roof_h + 0.04,
                 COLORS["outline"], 0.8)

    else:  # FLAT_SLOPE
        # Low-slope zinc roof angled toward street — from elevation, a tall
        # rectangle: the back edge meets the mansard high up
        cap_h = h * 0.22
        overhang = w * 0.06
        ctx.rect(x - overhang, cap_base_y, w + overhang * 2, cap_h,
                 COLORS["roof_zinc"], stroke_w=0.6)


def _draw_chimney(ctx: SVGContext, chimney: ChimneyNode, cx: float, cy: float):
    """Draw a chimney stack with optional flue pipe."""
    w = chimney.width
    h = chimney.height
    x = cx - w / 2
    ctx.rect(x, cy, w, h, COLORS["chimney"], stroke_w=0.6)
    # Cap
    cap_w = w * 1.2
    cap_h = 0.08
    ctx.rect(cx - cap_w / 2, cy + h, cap_w, cap_h, COLORS["chimney"], stroke_w=0.6)

    if chimney.has_pipe:
        # Thin flue pipe on top — shorter on edge chimneys, taller on ridge
        pipe_w = w * 0.20
        pipe_h = h * (0.50 if chimney.is_ridge else 0.15)
        pipe_x = cx - pipe_w / 2
        pipe_y = cy + h + cap_h
        ctx.rect(pipe_x, pipe_y, pipe_w, pipe_h, "#6A6060", stroke_w=0.5)
        # Pipe cap (small wider ring)
        ring_w = pipe_w * 1.6
        ring_h = 0.03
        ctx.rect(cx - ring_w / 2, pipe_y + pipe_h, ring_w, ring_h, "#6A6060", stroke_w=0.5)


# ---------------------------------------------------------------------------
# Dimension annotations
# ---------------------------------------------------------------------------

def _draw_dimensions(ctx: SVGContext, facade: FacadeNode, total_h: float, roof_h: float):
    """Add dimension labels to the right side of the drawing."""
    x_label = facade.width + 0.5
    y_acc = 0.0

    for child in facade.children:
        if isinstance(child, (FloorNode, GroundFloorNode)):
            h = child.height
            mid_y = y_acc + h / 2
            label = f"{h:.2f}m"
            ctx.text(x_label, mid_y, label, size=8, fill="#999")
            y_acc += h

    # Total height
    ctx.text(x_label, total_h + 0.3, f"Total: {total_h:.1f}m", size=9, fill="#666")

    # Width
    ctx.text(facade.width / 2, -0.5, f"{facade.width:.1f}m", size=9, fill="#666")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _facade_height(facade: FacadeNode) -> float:
    """Sum floor heights in a facade."""
    total = 0.0
    for child in facade.children:
        if isinstance(child, (FloorNode, GroundFloorNode)):
            total += child.height
    return total
