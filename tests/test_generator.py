"""Tests for core/generator.py — full pipeline and determinism."""

from core.generator import generate_building
from core.types import (
    BuildingConfig,
    BuildingNode,
    ChimneyNode,
    CornerNode,
    DormerNode,
    FacadeNode,
    FloorNode,
    GroundFloorNode,
    MansardSlopeNode,
    Orientation,
    RoofNode,
    StylePreset,
)


def _count_nodes(node, node_type=None) -> int:
    """Recursively count nodes in the IR tree."""
    count = 0
    if node_type is None or isinstance(node, node_type):
        count += 1
    if hasattr(node, "children"):
        for child in node.children:
            count += _count_nodes(child, node_type)
    return count


class TestGeneratorBasics:
    def test_returns_building_node(self):
        config = BuildingConfig(seed=42)
        building = generate_building(config)
        assert isinstance(building, BuildingNode)
        assert building.node_type == "building"

    def test_building_has_four_facades(self):
        building = generate_building(BuildingConfig(seed=1))
        facades = [c for c in building.children if isinstance(c, FacadeNode)]
        assert len(facades) == 4

    def test_facade_orientations(self):
        building = generate_building(BuildingConfig(seed=1))
        facades = [c for c in building.children if isinstance(c, FacadeNode)]
        orientations = {f.orientation for f in facades}
        assert orientations == {
            Orientation.SOUTH,
            Orientation.EAST,
            Orientation.WEST,
            Orientation.NORTH,
        }

    def test_building_has_roof(self):
        building = generate_building(BuildingConfig(seed=1))
        roofs = [c for c in building.children if isinstance(c, RoofNode)]
        assert len(roofs) == 1

    def test_front_facade_width_matches_lot(self):
        config = BuildingConfig(lot_width=18.0, seed=1)
        building = generate_building(config)
        front = [c for c in building.children
                 if isinstance(c, FacadeNode) and c.orientation == Orientation.SOUTH][0]
        assert front.width == 18.0

    def test_side_facades_match_depth(self):
        config = BuildingConfig(lot_depth=10.0, seed=1)
        building = generate_building(config)
        sides = [c for c in building.children
                 if isinstance(c, FacadeNode)
                 and c.orientation in (Orientation.EAST, Orientation.WEST)]
        for side in sides:
            assert side.width == 10.0


class TestGeneratorPresets:
    def test_boulevard_preset(self):
        config = BuildingConfig(style_preset="BOULEVARD", lot_width=20.0, seed=1)
        building = generate_building(config)
        assert building.style_preset == StylePreset.BOULEVARD

    def test_modest_preset(self):
        config = BuildingConfig(style_preset="MODEST", seed=1)
        building = generate_building(config)
        assert building.style_preset == StylePreset.MODEST


class TestDeterminism:
    def test_same_seed_same_tree(self):
        """Identical config + seed must produce an identical IR tree."""
        config = BuildingConfig(seed=123, style_preset="BOULEVARD", lot_width=18.0)
        b1 = generate_building(config)
        b2 = generate_building(config)

        # Same number of total nodes
        assert _count_nodes(b1) == _count_nodes(b2)

        # Same facade structure
        facades1 = [c for c in b1.children if isinstance(c, FacadeNode)]
        facades2 = [c for c in b2.children if isinstance(c, FacadeNode)]
        for f1, f2 in zip(facades1, facades2):
            assert f1.orientation == f2.orientation
            assert f1.width == f2.width
            assert len(f1.children) == len(f2.children)

    def test_different_seed_different_tree(self):
        """Different seeds should produce different variation."""
        config1 = BuildingConfig(seed=1)
        config2 = BuildingConfig(seed=999)
        b1 = generate_building(config1)
        b2 = generate_building(config2)

        # The overall structure is the same (same num_floors, lot_width)
        # but internal details (porte-cochère placement, layout strategy) differ.
        # Compare ground floor porte-cochère bay index — varies by seed.
        front1 = [c for c in b1.children
                  if isinstance(c, FacadeNode) and c.orientation == Orientation.SOUTH][0]
        front2 = [c for c in b2.children
                  if isinstance(c, FacadeNode) and c.orientation == Orientation.SOUTH][0]
        gf1 = [c for c in front1.children if isinstance(c, GroundFloorNode)][0]
        gf2 = [c for c in front2.children if isinstance(c, GroundFloorNode)][0]
        # Porte-cochère bay index should differ with different seeds
        assert gf1.porte_cochere_bay_index != gf2.porte_cochere_bay_index


class TestRoof:
    def test_roof_has_slope(self):
        building = generate_building(BuildingConfig(seed=1))
        roof = [c for c in building.children if isinstance(c, RoofNode)][0]
        slopes = [c for c in roof.children if isinstance(c, MansardSlopeNode)]
        assert len(slopes) >= 1

    def test_roof_has_dormers(self):
        building = generate_building(BuildingConfig(seed=1))
        roof = [c for c in building.children if isinstance(c, RoofNode)][0]
        dormers = [c for c in roof.children if isinstance(c, DormerNode)]
        assert len(dormers) >= 1

    def test_roof_has_chimneys(self):
        building = generate_building(BuildingConfig(seed=1))
        roof = [c for c in building.children if isinstance(c, RoofNode)][0]
        chimneys = [c for c in roof.children if isinstance(c, ChimneyNode)]
        assert len(chimneys) >= 2

    def test_roof_positioned_at_cornice_height(self):
        building = generate_building(BuildingConfig(seed=1))
        roof = [c for c in building.children if isinstance(c, RoofNode)][0]
        # Roof y should be > 0 (above ground)
        assert roof.transform.position[1] > 10.0  # At least 10m up


class TestCornerChamfer:
    def test_no_chamfer_by_default(self):
        building = generate_building(BuildingConfig(seed=1))
        corners = [c for c in building.children if isinstance(c, CornerNode)]
        assert len(corners) == 0

    def test_chamfer_when_requested(self):
        config = BuildingConfig(seed=1, corner_chamfer=True)
        building = generate_building(config)
        corners = [c for c in building.children if isinstance(c, CornerNode)]
        assert len(corners) == 1
        assert corners[0].chamfer_width == 3.0


class TestBuildingMetadata:
    def test_metadata_preserved(self):
        config = BuildingConfig(
            lot_width=20.0, lot_depth=14.0, num_floors=7, seed=55,
        )
        building = generate_building(config)
        assert building.lot_width == 20.0
        assert building.lot_depth == 14.0
        assert building.num_floors == 7
        assert building.seed == 55
