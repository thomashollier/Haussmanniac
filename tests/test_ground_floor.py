"""Tests for core/ground_floor.py — shopfronts, porte-cochère, rustication."""

from core.grammar import HaussmannGrammar
from core.ground_floor import build_ground_floor
from core.profile import get_profile
from core.types import (
    BayNode,
    BayType,
    CorniceNode,
    GroundFloorNode,
    OrnamentLevel,
    OrnamentNode,
    PedimentStyle,
    StylePreset,
    SurroundStyle,
    Transform,
    WindowNode,
)
from core.variation import Variation

grammar = HaussmannGrammar()

_STYLE_PROFILE = {
    StylePreset.BOULEVARD: "grand_boulevard",
    StylePreset.RESIDENTIAL: "residential",
    StylePreset.MODEST: "modest",
}


def _make_ground_floor(
    style: StylePreset = StylePreset.RESIDENTIAL,
    facade_width: float = 16.0,
    seed: int = 42,
    has_porte_cochere: bool = True,
) -> GroundFloorNode:
    g = HaussmannGrammar(get_profile(_STYLE_PROFILE.get(style, "residential")))
    variation = Variation(seed=seed, style=style)
    gf_spec = g.get_ground_floor_spec(style, has_porte_cochere)
    node = GroundFloorNode(
        transform=Transform(position=(0.0, 0.0, 0.0)),
        height=gf_spec.height,
    )
    bay_layout = g.get_bay_layout(facade_width, style)
    build_ground_floor(
        node, bay_layout, facade_width, style, variation, g,
        has_porte_cochere,
    )
    return node


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

class TestGroundFloorStructure:
    def test_has_bays(self):
        gf = _make_ground_floor()
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        assert len(bays) >= 3

    def test_has_cornice(self):
        """Ground floor should have a cornice at its top."""
        gf = _make_ground_floor()
        cornices = [c for c in gf.children if isinstance(c, CorniceNode)]
        assert len(cornices) == 1

    def test_cornice_at_floor_height(self):
        gf = _make_ground_floor()
        cornice = [c for c in gf.children if isinstance(c, CorniceNode)][0]
        assert cornice.transform.position[1] == gf.height

    def test_all_bays_have_windows(self):
        gf = _make_ground_floor()
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        for bay in bays:
            windows = [c for c in bay.children if isinstance(c, WindowNode)]
            assert len(windows) == 1


# ---------------------------------------------------------------------------
# Shopfront bays
# ---------------------------------------------------------------------------

class TestShopfronts:
    def test_shopfront_bay_type(self):
        gf = _make_ground_floor(has_porte_cochere=False)
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        for bay in bays:
            assert bay.bay_type == BayType.SHOPFRONT

    def test_shopfront_height_proportional(self):
        """Shopfront openings should be ~75% of floor height."""
        gf = _make_ground_floor(has_porte_cochere=False)
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        for bay in bays:
            window = [c for c in bay.children if isinstance(c, WindowNode)][0]
            ratio = window.height / gf.height
            assert 0.65 <= ratio <= 0.85

    def test_shopfront_wider_than_upper_windows(self):
        """Shopfront openings should be wide (85% of bay width)."""
        gf = _make_ground_floor()
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        for bay in bays:
            window = [c for c in bay.children if isinstance(c, WindowNode)][0]
            assert window.width > bay.width * 0.75

    def test_boulevard_has_pilastered_surround(self):
        gf = _make_ground_floor(style=StylePreset.BOULEVARD, has_porte_cochere=False)
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        for bay in bays:
            window = [c for c in bay.children if isinstance(c, WindowNode)][0]
            assert window.surround_style == SurroundStyle.PILASTERED

    def test_modest_no_surround(self):
        gf = _make_ground_floor(style=StylePreset.MODEST, has_porte_cochere=False)
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        for bay in bays:
            window = [c for c in bay.children if isinstance(c, WindowNode)][0]
            assert window.surround_style == SurroundStyle.NONE


# ---------------------------------------------------------------------------
# Porte-cochère
# ---------------------------------------------------------------------------

class TestPorteCochere:
    def test_porte_cochere_present(self):
        gf = _make_ground_floor(has_porte_cochere=True)
        assert gf.has_porte_cochere is True
        assert gf.porte_cochere_bay_index is not None

    def test_exactly_one_door_bay(self):
        gf = _make_ground_floor(has_porte_cochere=True)
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        doors = [b for b in bays if b.bay_type == BayType.DOOR]
        assert len(doors) == 1

    def test_remaining_bays_are_shopfronts(self):
        gf = _make_ground_floor(has_porte_cochere=True)
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        shopfronts = [b for b in bays if b.bay_type == BayType.SHOPFRONT]
        doors = [b for b in bays if b.bay_type == BayType.DOOR]
        assert len(shopfronts) + len(doors) == len(bays)

    def test_no_porte_cochere(self):
        gf = _make_ground_floor(has_porte_cochere=False)
        assert gf.has_porte_cochere is False
        assert gf.porte_cochere_bay_index is None
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        doors = [b for b in bays if b.bay_type == BayType.DOOR]
        assert len(doors) == 0

    def test_porte_cochere_tall_opening(self):
        """Porte-cochère opening should be ~80% of floor height."""
        gf = _make_ground_floor(has_porte_cochere=True)
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        door_bay = [b for b in bays if b.bay_type == BayType.DOOR][0]
        window = [c for c in door_bay.children if isinstance(c, WindowNode)][0]
        ratio = window.height / gf.height
        assert 0.70 <= ratio <= 0.90

    def test_porte_cochere_starts_at_ground(self):
        """Porte-cochère opening should start at ground level."""
        gf = _make_ground_floor(has_porte_cochere=True)
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        door_bay = [b for b in bays if b.bay_type == BayType.DOOR][0]
        window = [c for c in door_bay.children if isinstance(c, WindowNode)][0]
        assert window.transform.position[1] == 0.0

    def test_boulevard_porte_cochere_arched(self):
        """Rich buildings get arched porte-cochère surrounds."""
        gf = _make_ground_floor(
            style=StylePreset.BOULEVARD, has_porte_cochere=True,
        )
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        door_bay = [b for b in bays if b.bay_type == BayType.DOOR][0]
        window = [c for c in door_bay.children if isinstance(c, WindowNode)][0]
        assert window.pediment == PedimentStyle.ARCHED

    def test_porte_cochere_has_keystone(self):
        gf = _make_ground_floor(
            style=StylePreset.RESIDENTIAL, has_porte_cochere=True,
        )
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        door_bay = [b for b in bays if b.bay_type == BayType.DOOR][0]
        keystones = [c for c in door_bay.children if isinstance(c, OrnamentNode)]
        assert len(keystones) >= 1
        assert any("porte_cochere" in k.ornament_id for k in keystones)


# ---------------------------------------------------------------------------
# Rustication
# ---------------------------------------------------------------------------

class TestRustication:
    def test_boulevard_has_rustication(self):
        gf = _make_ground_floor(style=StylePreset.BOULEVARD)
        assert gf.has_rustication is True

    def test_residential_has_rustication(self):
        gf = _make_ground_floor(style=StylePreset.RESIDENTIAL)
        assert gf.has_rustication is True

    def test_modest_no_rustication(self):
        gf = _make_ground_floor(style=StylePreset.MODEST)
        assert gf.has_rustication is False

    def test_boulevard_has_rustication_ornament(self):
        """Boulevard shopfronts should have explicit rustication ornament nodes."""
        gf = _make_ground_floor(
            style=StylePreset.BOULEVARD, has_porte_cochere=False,
        )
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        for bay in bays:
            rusts = [c for c in bay.children
                     if isinstance(c, OrnamentNode) and "rustication" in c.ornament_id]
            assert len(rusts) >= 1


# ---------------------------------------------------------------------------
# Ornament
# ---------------------------------------------------------------------------

class TestGroundFloorOrnament:
    def test_keystones_on_rich_buildings(self):
        gf = _make_ground_floor(
            style=StylePreset.RESIDENTIAL, has_porte_cochere=False,
        )
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        for bay in bays:
            keystones = [c for c in bay.children
                         if isinstance(c, OrnamentNode) and "keystone" in c.ornament_id]
            assert len(keystones) >= 1

    def test_no_keystones_on_modest(self):
        gf = _make_ground_floor(
            style=StylePreset.MODEST, has_porte_cochere=False,
        )
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        for bay in bays:
            keystones = [c for c in bay.children
                         if isinstance(c, OrnamentNode) and "keystone" in c.ornament_id]
            assert len(keystones) == 0

    def test_modest_no_window_keystone(self):
        gf = _make_ground_floor(style=StylePreset.MODEST, has_porte_cochere=False)
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        for bay in bays:
            window = [c for c in bay.children if isinstance(c, WindowNode)][0]
            assert window.has_keystone is False


# ---------------------------------------------------------------------------
# Integration with facade pipeline
# ---------------------------------------------------------------------------

class TestGroundFloorIntegration:
    def test_via_full_pipeline(self):
        """Verify ground_floor module is used by the facade pipeline."""
        from core.facade import build_facade
        from core.floor import build_floor_stack
        from core.types import Orientation

        variation = Variation(seed=42, style=StylePreset.RESIDENTIAL)
        floors = build_floor_stack(
            num_floors=6, facade_width=15.0, style=StylePreset.RESIDENTIAL,
            variation=variation, grammar=grammar,
        )
        facade = build_facade(
            orientation=Orientation.SOUTH, facade_width=15.0,
            floor_nodes=floors, style=StylePreset.RESIDENTIAL,
            variation=variation, grammar=grammar,
        )
        gf_nodes = [c for c in facade.children if isinstance(c, GroundFloorNode)]
        assert len(gf_nodes) == 1
        gf = gf_nodes[0]
        bays = [c for c in gf.children if isinstance(c, BayNode)]
        assert len(bays) >= 3
        # Should have a porte-cochère
        doors = [b for b in bays if b.bay_type == BayType.DOOR]
        assert len(doors) == 1
