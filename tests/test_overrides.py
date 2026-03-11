"""Tests for the BuildingOverrides system."""

from core.generator import generate_building
from core.types import (
    BuildingConfig,
    BuildingOverrides,
    DormerNode,
    DormerStyle,
    GroundFloorType,
    PorteStyle,
    StylePreset,
)


def _generate(seed: int = 0, preset: str = "MODEST", overrides=None):
    config = BuildingConfig(seed=seed, style_preset=preset, overrides=overrides)
    return generate_building(config)


def _get_dormers(building):
    roof = [c for c in building.children if c.node_type == "roof"][0]
    return [c for c in roof.children if isinstance(c, DormerNode)]


class TestHasDormersOverride:
    def test_force_dormers_on(self):
        """Override has_dormers=True produces dormers even when RNG says no."""
        # Find a seed where modest building has no dormers (short roof)
        no_dormer_seed = None
        for seed in range(100):
            building = _generate(seed=seed)
            if len(_get_dormers(building)) == 0:
                no_dormer_seed = seed
                break
        assert no_dormer_seed is not None, "Need a seed that produces no dormers"

        # Now override to force dormers on
        ovr = BuildingOverrides(has_dormers=True)
        building = _generate(seed=no_dormer_seed, overrides=ovr)
        dormers = _get_dormers(building)
        assert len(dormers) >= 1, "Override should force dormers on"

    def test_force_dormers_off(self):
        """Override has_dormers=False suppresses dormers even when RNG says yes."""
        # Find a seed where modest building has dormers (tall roof)
        dormer_seed = None
        for seed in range(100):
            building = _generate(seed=seed)
            if len(_get_dormers(building)) > 0:
                dormer_seed = seed
                break
        assert dormer_seed is not None, "Need a seed that produces dormers"

        ovr = BuildingOverrides(has_dormers=False)
        building = _generate(seed=dormer_seed, overrides=ovr)
        dormers = _get_dormers(building)
        assert len(dormers) == 0, "Override should suppress dormers"


class TestDormerStyleOverride:
    def test_dormer_style_reaches_ir(self):
        """Override dormer_style is reflected in DormerNode.style."""
        ovr = BuildingOverrides(
            has_dormers=True,
            dormer_style=DormerStyle.OVAL,
        )
        building = _generate(seed=0, overrides=ovr)
        dormers = _get_dormers(building)
        assert len(dormers) >= 1
        for d in dormers:
            assert d.style == DormerStyle.OVAL


class TestAllNoneIdentical:
    def test_empty_overrides_match_no_overrides(self):
        """BuildingOverrides() (all None) produces identical output to None."""
        b_none = _generate(seed=42)
        b_empty = _generate(seed=42, overrides=BuildingOverrides())

        # Compare roof children counts and positions
        roof_none = [c for c in b_none.children if c.node_type == "roof"][0]
        roof_empty = [c for c in b_empty.children if c.node_type == "roof"][0]

        assert len(roof_none.children) == len(roof_empty.children)

        dormers_none = _get_dormers(b_none)
        dormers_empty = _get_dormers(b_empty)
        assert len(dormers_none) == len(dormers_empty)

        for a, b in zip(dormers_none, dormers_empty):
            assert a.transform.position == b.transform.position
            assert a.style == b.style
            assert a.width == b.width


class TestDeterminism:
    def test_non_overridden_values_stable(self):
        """Overriding one field doesn't change non-overridden RNG-driven values."""
        # Generate two buildings with same seed, one with bay_count override
        b_base = _generate(seed=7, preset="RESIDENTIAL")
        b_ovr = _generate(seed=7, preset="RESIDENTIAL",
                          overrides=BuildingOverrides(dormer_style=DormerStyle.POINTY_ROOF))

        # Roof chimney count/positions should be identical (dormer_style doesn't
        # affect chimney RNG since vary_dormer_style is called inside _build_dormers
        # which runs after chimney placement in build_roof)
        from core.types import ChimneyNode
        roof_base = [c for c in b_base.children if c.node_type == "roof"][0]
        roof_ovr = [c for c in b_ovr.children if c.node_type == "roof"][0]

        ch_base = [c for c in roof_base.children if isinstance(c, ChimneyNode)]
        ch_ovr = [c for c in roof_ovr.children if isinstance(c, ChimneyNode)]
        assert len(ch_base) == len(ch_ovr)
        for a, b in zip(ch_base, ch_ovr):
            assert a.width == b.width
            assert a.height == b.height

    def test_same_seed_same_override_same_result(self):
        """Same seed + same override = identical IR."""
        ovr = BuildingOverrides(has_dormers=True, dormer_style=DormerStyle.OVAL)
        b1 = _generate(seed=99, overrides=ovr)
        b2 = _generate(seed=99, overrides=ovr)

        d1 = _get_dormers(b1)
        d2 = _get_dormers(b2)
        assert len(d1) == len(d2)
        for a, b in zip(d1, d2):
            assert a.style == b.style
            assert a.transform.position == b.transform.position
