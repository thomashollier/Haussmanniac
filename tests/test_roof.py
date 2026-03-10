"""Tests for core/roof.py — mansard roof generation."""

import math

from core.grammar import HaussmannGrammar
from core.roof import build_roof
from core.types import (
    ChimneyNode,
    DormerNode,
    DormerStyle,
    MansardSlopeNode,
    RoofNode,
    StylePreset,
)
from core.variation import Variation

grammar = HaussmannGrammar()


def _make_roof(
    style: StylePreset = StylePreset.RESIDENTIAL,
    lot_width: float = 15.0,
    lot_depth: float = 12.0,
    cornice_height: float = 18.0,
    seed: int = 42,
) -> RoofNode:
    variation = Variation(seed=seed, style=style)
    return build_roof(
        lot_width=lot_width,
        lot_depth=lot_depth,
        cornice_height=cornice_height,
        style=style,
        variation=variation,
        grammar=grammar,
    )


class TestRoofStructure:
    def test_returns_roof_node(self):
        roof = _make_roof()
        assert isinstance(roof, RoofNode)
        assert roof.node_type == "roof"

    def test_roof_at_cornice_height(self):
        roof = _make_roof(cornice_height=20.0)
        assert roof.transform.position[1] == 20.0

    def test_roof_has_children(self):
        roof = _make_roof()
        assert len(roof.children) > 0

    def test_residential_broken_mansard(self):
        from core.types import MansardType
        roof = _make_roof(style=StylePreset.RESIDENTIAL)
        assert roof.mansard_type == MansardType.BROKEN
        assert math.degrees(roof.mansard_lower_angle) >= 65.0

    def test_boulevard_steep_mansard(self):
        from core.types import MansardType
        roof = _make_roof(style=StylePreset.BOULEVARD)
        assert roof.mansard_type == MansardType.STEEP


class TestSlopes:
    def test_four_slopes(self):
        """A building should have four mansard slope faces."""
        roof = _make_roof()
        slopes = [c for c in roof.children if isinstance(c, MansardSlopeNode)]
        assert len(slopes) == 4

    def test_front_slope_steep(self):
        """Front slope should have the style-appropriate steep angle."""
        roof = _make_roof(style=StylePreset.RESIDENTIAL)
        slopes = [c for c in roof.children if isinstance(c, MansardSlopeNode)]
        front = slopes[0]
        assert math.degrees(front.lower_angle) >= 65.0

    def test_rear_slopes_shallow(self):
        """Rear and side slopes should always be shallow."""
        from core.types import MansardType
        roof = _make_roof(style=StylePreset.BOULEVARD)
        slopes = [c for c in roof.children if isinstance(c, MansardSlopeNode)]
        # Slopes 1,2,3 are rear/sides
        for slope in slopes[1:]:
            assert slope.mansard_type == MansardType.SHALLOW

    def test_slopes_zinc_material(self):
        roof = _make_roof()
        slopes = [c for c in roof.children if isinstance(c, MansardSlopeNode)]
        for slope in slopes:
            assert slope.material == "zinc"

    def test_rear_slope_rotated(self):
        """Rear slope should be rotated 180° around Y."""
        roof = _make_roof()
        slopes = [c for c in roof.children if isinstance(c, MansardSlopeNode)]
        rear = slopes[1]  # Second slope is rear
        assert abs(rear.transform.rotation[1] - math.pi) < 0.01


class TestDormers:
    def test_has_dormers(self):
        roof = _make_roof()
        dormers = [c for c in roof.children if isinstance(c, DormerNode)]
        assert len(dormers) >= 1

    def test_boulevard_dormer_per_bay(self):
        """Boulevard buildings: one dormer per bay."""
        roof = _make_roof(style=StylePreset.BOULEVARD, lot_width=20.0)
        dormers = [c for c in roof.children if isinstance(c, DormerNode)]
        bay_count = grammar.compute_bay_count(20.0, StylePreset.BOULEVARD)
        assert len(dormers) == bay_count

    def test_modest_has_small_dormers(self):
        """Modest mansard: dormers every other bay, base style PEDIMENT_CURVED (variation may swap)."""
        roof = _make_roof(style=StylePreset.MODEST, lot_width=15.0)
        dormers = [c for c in roof.children if isinstance(c, DormerNode)]
        assert len(dormers) >= 1
        for d in dormers:
            assert d.style in (DormerStyle.PEDIMENT_CURVED, DormerStyle.POINTY_ROOF)

    def test_dormers_centered_in_bays(self):
        """Dormers should be centered horizontally within their bay."""
        roof = _make_roof()
        dormers = [c for c in roof.children if isinstance(c, DormerNode)]
        bay_layout = grammar.get_bay_layout(15.0, StylePreset.RESIDENTIAL)
        for dormer, bay in zip(dormers, bay_layout):
            expected_x = bay.x_offset + bay.width / 2
            assert abs(dormer.transform.position[0] - expected_x) < 0.01

    def test_dormer_width_narrower_than_bay(self):
        roof = _make_roof()
        dormers = [c for c in roof.children if isinstance(c, DormerNode)]
        bay_layout = grammar.get_bay_layout(15.0, StylePreset.RESIDENTIAL)
        for dormer, bay in zip(dormers, bay_layout):
            assert dormer.width < bay.width

    def test_dormers_positioned_on_slope(self):
        """Dormers should be positioned partway up the slope, not at base."""
        roof = _make_roof()
        dormers = [c for c in roof.children if isinstance(c, DormerNode)]
        for d in dormers:
            assert d.transform.position[1] > 0.0


class TestChimneys:
    def test_has_chimneys(self):
        roof = _make_roof()
        chimneys = [c for c in roof.children if isinstance(c, ChimneyNode)]
        assert len(chimneys) >= 2

    def test_chimneys_on_party_walls(self):
        """Chimneys should cluster near the left and right lot edges (party walls)."""
        roof = _make_roof(lot_width=20.0)
        chimneys = [c for c in roof.children if isinstance(c, ChimneyNode)]
        xs = [c.transform.position[0] for c in chimneys]
        # All chimneys should be near the edges, not in the middle
        mid = 20.0 / 2
        for x in xs:
            assert abs(x - mid) > mid * 0.5, (
                f"Chimney at x={x:.1f} is too close to center ({mid})"
            )

    def test_chimneys_within_footprint(self):
        """All chimneys should be within the building footprint."""
        width = 15.0
        depth = 12.0
        roof = _make_roof(lot_width=width, lot_depth=depth)
        chimneys = [c for c in roof.children if isinstance(c, ChimneyNode)]
        for c in chimneys:
            assert 0.0 < c.transform.position[0] < width
            assert 0.0 <= c.transform.position[2] <= depth

    def test_chimneys_start_at_mansard_base(self):
        """Chimneys start at the base of the mansard and clear the top."""
        roof = _make_roof()
        chimneys = [c for c in roof.children if isinstance(c, ChimneyNode)]
        roof_spec = grammar.get_roof_spec(
            grammar.compute_bay_count(15.0, StylePreset.RESIDENTIAL),
            StylePreset.RESIDENTIAL,
        )
        for c in chimneys:
            assert c.transform.position[1] == 0.0
            assert c.height > roof_spec.mansard_height

    def test_chimney_stone_material(self):
        roof = _make_roof()
        chimneys = [c for c in roof.children if isinstance(c, ChimneyNode)]
        for c in chimneys:
            assert c.material == "stone"

    def test_chimney_dimensions_varied(self):
        """Different seeds should produce slightly different chimney sizes."""
        roof1 = _make_roof(seed=1)
        roof2 = _make_roof(seed=999)
        ch1 = [c for c in roof1.children if isinstance(c, ChimneyNode)]
        ch2 = [c for c in roof2.children if isinstance(c, ChimneyNode)]
        # At least widths or heights should differ
        widths1 = [c.width for c in ch1]
        widths2 = [c.width for c in ch2]
        assert widths1 != widths2


class TestRoofDeterminism:
    def test_same_seed_same_roof(self):
        r1 = _make_roof(seed=42)
        r2 = _make_roof(seed=42)
        ch1 = [c for c in r1.children if isinstance(c, ChimneyNode)]
        ch2 = [c for c in r2.children if isinstance(c, ChimneyNode)]
        assert len(ch1) == len(ch2)
        for a, b in zip(ch1, ch2):
            assert a.width == b.width
            assert a.height == b.height
