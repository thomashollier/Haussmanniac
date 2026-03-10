"""Tests for core/facade.py — facade composition and bay population."""

from core.facade import build_facade
from core.floor import build_floor_stack
from core.grammar import HaussmannGrammar
from core.types import (
    BalconyNode,
    BayNode,
    BayType,
    CorniceNode,
    FacadeNode,
    FloorNode,
    FloorType,
    GroundFloorNode,
    OrnamentLevel,
    OrnamentNode,
    Orientation,
    PilasterNode,
    StringCourseNode,
    StylePreset,
    WindowNode,
)
from core.variation import Variation

grammar = HaussmannGrammar()


def _make_facade(
    style: StylePreset = StylePreset.RESIDENTIAL,
    width: float = 15.0,
    seed: int = 42,
    num_floors: int = 6,
) -> FacadeNode:
    variation = Variation(seed=seed, style=style)
    floors = build_floor_stack(
        num_floors=num_floors,
        facade_width=width,
        style=style,
        variation=variation,
        grammar=grammar,
        has_entresol=True,
    )
    return build_facade(
        orientation=Orientation.SOUTH,
        facade_width=width,
        floor_nodes=floors,
        style=style,
        variation=variation,
        grammar=grammar,
    )


class TestFacadeStructure:
    def test_facade_has_children(self):
        facade = _make_facade()
        assert len(facade.children) > 0

    def test_facade_contains_floors(self):
        facade = _make_facade()
        floors = [c for c in facade.children if isinstance(c, (FloorNode, GroundFloorNode))]
        assert len(floors) >= 2

    def test_facade_has_ground_floor(self):
        facade = _make_facade()
        gf = [c for c in facade.children if isinstance(c, GroundFloorNode)]
        assert len(gf) == 1

    def test_facade_has_roofline_cornice(self):
        facade = _make_facade()
        cornices = [c for c in facade.children if isinstance(c, CorniceNode)]
        assert len(cornices) >= 1
        # The roofline cornice should have larger projection
        roofline = [c for c in cornices if c.projection > 0.3]
        assert len(roofline) == 1


class TestBayPopulation:
    def test_every_floor_has_bays(self):
        facade = _make_facade()
        for child in facade.children:
            if isinstance(child, (FloorNode, GroundFloorNode)):
                bays = [c for c in child.children if isinstance(c, BayNode)]
                assert len(bays) >= 3, f"{child.node_type} has {len(bays)} bays"

    def test_bays_have_windows(self):
        facade = _make_facade()
        for child in facade.children:
            if isinstance(child, (FloorNode, GroundFloorNode)):
                bays = [c for c in child.children if isinstance(c, BayNode)]
                for bay in bays:
                    windows = [c for c in bay.children if isinstance(c, WindowNode)]
                    assert len(windows) == 1, f"Bay at x={bay.x_offset} has {len(windows)} windows"

    def test_ground_floor_has_shopfronts(self):
        facade = _make_facade()
        gf = [c for c in facade.children if isinstance(c, GroundFloorNode)][0]
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        shopfronts = [b for b in bays if b.bay_type == BayType.SHOPFRONT]
        doors = [b for b in bays if b.bay_type == BayType.DOOR]
        # All bays should be either shopfront or door (porte-cochère)
        assert len(shopfronts) + len(doors) == len(bays)

    def test_porte_cochere_present(self):
        facade = _make_facade()
        gf = [c for c in facade.children if isinstance(c, GroundFloorNode)][0]
        assert gf.has_porte_cochere is True
        assert gf.porte_cochere_bay_index is not None
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        doors = [b for b in bays if b.bay_type == BayType.DOOR]
        assert len(doors) == 1


class TestBalconies:
    def test_noble_floor_has_continuous_balcony(self):
        facade = _make_facade(num_floors=7)
        noble = [c for c in facade.children
                 if isinstance(c, FloorNode) and c.floor_type == FloorType.NOBLE]
        assert len(noble) == 1
        balconies = [c for c in noble[0].children if isinstance(c, BalconyNode)]
        continuous = [b for b in balconies if b.is_continuous]
        assert len(continuous) == 1

    def test_continuous_balcony_spans_facade(self):
        width = 15.0
        facade = _make_facade(width=width, num_floors=7)
        noble = [c for c in facade.children
                 if isinstance(c, FloorNode) and c.floor_type == FloorType.NOBLE][0]
        balcony = [c for c in noble.children
                   if isinstance(c, BalconyNode) and c.is_continuous][0]
        assert balcony.width == width

    def test_fifth_floor_has_balconettes(self):
        facade = _make_facade(num_floors=7)
        fifth = [c for c in facade.children
                 if isinstance(c, FloorNode) and c.floor_type == FloorType.FIFTH]
        assert len(fifth) == 1
        bays = [c for c in fifth[0].children if isinstance(c, BayNode)]
        for bay in bays:
            balconettes = [c for c in bay.children if isinstance(c, BalconyNode)]
            assert len(balconettes) == 1
            assert balconettes[0].is_continuous is False


class TestOrnament:
    def test_noble_floor_has_pilasters(self):
        facade = _make_facade(style=StylePreset.BOULEVARD, num_floors=7)
        noble = [c for c in facade.children
                 if isinstance(c, FloorNode) and c.floor_type == FloorType.NOBLE]
        assert len(noble) == 1
        bays = [c for c in noble[0].children if isinstance(c, BayNode)]
        for bay in bays:
            pilasters = [c for c in bay.children if isinstance(c, PilasterNode)]
            assert len(pilasters) == 2  # One on each side

    def test_upper_floors_no_pilasters(self):
        facade = _make_facade(style=StylePreset.RESIDENTIAL, num_floors=7)
        fourth = [c for c in facade.children
                  if isinstance(c, FloorNode) and c.floor_type == FloorType.FOURTH]
        if fourth:
            bays = [c for c in fourth[0].children if isinstance(c, BayNode)]
            for bay in bays:
                pilasters = [c for c in bay.children if isinstance(c, PilasterNode)]
                assert len(pilasters) == 0

    def test_floors_have_string_courses(self):
        facade = _make_facade()
        for child in facade.children:
            if isinstance(child, FloorNode):
                strings = [c for c in child.children if isinstance(c, StringCourseNode)]
                assert len(strings) == 1

    def test_ground_floor_has_cornice(self):
        facade = _make_facade()
        gf = [c for c in facade.children if isinstance(c, GroundFloorNode)][0]
        cornices = [c for c in gf.children if isinstance(c, CorniceNode)]
        assert len(cornices) >= 1


class TestBayAlignment:
    def test_bays_aligned_across_floors(self):
        """Bay x_offsets should be identical across all floors."""
        facade = _make_facade()
        floors = [c for c in facade.children if isinstance(c, (FloorNode, GroundFloorNode))]
        bay_offsets_per_floor = []
        for floor in floors:
            bays = [c for c in floor.children if isinstance(c, BayNode)]
            offsets = [round(b.x_offset, 3) for b in bays]
            bay_offsets_per_floor.append(offsets)

        # All floors should have the same bay x-offsets
        for offsets in bay_offsets_per_floor:
            assert offsets == bay_offsets_per_floor[0]
