"""Tests for core/types.py — IR dataclasses and enums."""

import math

from core.types import (
    BalconyNode,
    BayNode,
    BayType,
    BuildingConfig,
    BuildingNode,
    ChimneyNode,
    CornerNode,
    CorniceNode,
    DormerNode,
    DormerStyle,
    FacadeNode,
    FloorNode,
    FloorType,
    GroundFloorNode,
    IRNode,
    MansardSlopeNode,
    OrnamentLevel,
    OrnamentNode,
    Orientation,
    PedimentStyle,
    PilasterNode,
    RailingPattern,
    RoofNode,
    StringCourseNode,
    StylePreset,
    SurroundStyle,
    Transform,
    WindowNode,
)


class TestTransform:
    def test_defaults(self):
        t = Transform()
        assert t.position == (0.0, 0.0, 0.0)
        assert t.rotation == (0.0, 0.0, 0.0)
        assert t.scale == (1.0, 1.0, 1.0)

    def test_custom(self):
        t = Transform(position=(1.0, 2.0, 3.0), rotation=(0.1, 0.2, 0.3))
        assert t.position == (1.0, 2.0, 3.0)
        assert t.scale == (1.0, 1.0, 1.0)  # default preserved


class TestEnums:
    def test_floor_types(self):
        assert len(FloorType) == 7
        assert FloorType.GROUND.name == "GROUND"
        assert FloorType.MANSARD.name == "MANSARD"

    def test_ornament_levels_ordered(self):
        assert OrnamentLevel.RICH.value > OrnamentLevel.MODERATE.value
        assert OrnamentLevel.MODERATE.value > OrnamentLevel.SIMPLE.value
        assert OrnamentLevel.SIMPLE.value > OrnamentLevel.NONE.value

    def test_pediment_styles(self):
        assert PedimentStyle.NONE in PedimentStyle

    def test_style_presets(self):
        assert len(StylePreset) == 3


class TestIRNodes:
    def test_node_type_auto_set(self):
        """node_type should be set automatically by each subclass."""
        assert WindowNode().node_type == "window"
        assert BalconyNode().node_type == "balcony"
        assert PilasterNode().node_type == "pilaster"
        assert OrnamentNode().node_type == "ornament"
        assert CorniceNode().node_type == "cornice"
        assert StringCourseNode().node_type == "string_course"
        assert BayNode().node_type == "bay"
        assert FloorNode().node_type == "floor"
        assert GroundFloorNode().node_type == "ground_floor"
        assert MansardSlopeNode().node_type == "mansard_slope"
        assert DormerNode().node_type == "dormer"
        assert ChimneyNode().node_type == "chimney"
        assert RoofNode().node_type == "roof"
        assert CornerNode().node_type == "corner"
        assert FacadeNode().node_type == "facade"
        assert BuildingNode().node_type == "building"

    def test_window_defaults(self):
        w = WindowNode()
        assert w.width == 1.2
        assert w.height == 1.8
        assert w.surround_style == SurroundStyle.MOLDED
        assert w.pediment == PedimentStyle.NONE
        assert w.has_keystone is False

    def test_building_node_children(self):
        b = BuildingNode(lot_width=18.0, num_floors=7)
        f = FacadeNode(orientation=Orientation.SOUTH, width=18.0)
        b.children.append(f)
        assert len(b.children) == 1
        assert b.children[0].node_type == "facade"

    def test_transform_on_node(self):
        w = WindowNode(transform=Transform(position=(1.0, 5.0, 0.0)))
        assert w.transform.position == (1.0, 5.0, 0.0)

    def test_mansard_angles(self):
        m = MansardSlopeNode()
        assert abs(math.degrees(m.lower_angle) - 75.0) < 0.01
        assert abs(math.degrees(m.upper_angle) - 20.0) < 0.01


class TestBuildingConfig:
    def test_defaults(self):
        c = BuildingConfig()
        assert c.lot_width is None   # resolved from profile at generation time
        assert c.lot_depth is None   # resolved from profile at generation time
        assert c.num_floors is None  # resolved from profile at generation time
        assert c.style_preset == "RESIDENTIAL"
        assert c.seed == 42
        assert c.has_entresol is None  # resolved from profile at generation time
        assert c.has_porte_cochere is True
        assert c.corner_chamfer is False
