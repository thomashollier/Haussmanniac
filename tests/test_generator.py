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
from core.variation import Variation


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
        config1 = BuildingConfig(seed=15)
        config2 = BuildingConfig(seed=17)
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


class TestGabaritDerivedFloors:
    """Floor count is derived from street width via gabarit system."""

    def test_grand_explicit_street_width(self):
        """GRAND preset with explicit street=30m → gabarit 20m → 7 floors."""
        config = BuildingConfig(style_preset="BOULEVARD", lot_width=21.0, seed=0, street_width=30.0)
        building = generate_building(config)
        assert building.num_floors == 7

    def test_residential_explicit_street_width(self):
        """RESIDENTIAL preset with explicit street=12m → gabarit 17.55m → 6-7 floors."""
        config = BuildingConfig(style_preset="RESIDENTIAL", lot_width=15.0, seed=0, street_width=12.0)
        building = generate_building(config)
        assert building.num_floors == 7

    def test_modest_explicit_street_width(self):
        """MODEST preset with explicit street=8m → gabarit 14.6m → 6 floors."""
        config = BuildingConfig(style_preset="MODEST", lot_width=10.0, seed=1, street_width=8.0)
        building = generate_building(config)
        assert building.num_floors == 6

    def test_narrow_street_reduces_modest(self):
        """Narrow street (6m) on MODEST → gabarit 11.7m → fewer floors."""
        config = BuildingConfig(
            style_preset="MODEST", lot_width=10.0, seed=1,
            street_width=6.0,
        )
        building = generate_building(config)
        assert building.num_floors < 6

    def test_num_floors_override_skips_gabarit(self):
        """Explicit num_floors bypasses gabarit derivation entirely."""
        config = BuildingConfig(
            style_preset="RESIDENTIAL", lot_width=15.0, seed=1,
            num_floors=5,
        )
        building = generate_building(config)
        assert building.num_floors == 5


class TestFloorStacking:
    """Bottom-up floor stacking within gabarit budget."""

    def test_zero_sigma_returns_typ_heights(self):
        """sigma=0 on all floors → typ heights, fits 7 floors in GRAND gabarit."""
        from core.profile import RangeParam, get_profile
        from core.grammar import HaussmannGrammar, compute_gabarit
        from core.variation import Variation

        p = get_profile("grand_boulevard")
        # Set sigma=0 → sample_range always returns typ
        for attr in ("ground", "entresol", "noble", "third", "fourth", "fifth", "mansard"):
            rp = getattr(p.floors, attr)
            setattr(p.floors, attr, RangeParam(rp.typ, rp.variation, 0.0))
        g = HaussmannGrammar(profile=p)
        v = Variation(seed=0, style=StylePreset.BOULEVARD)
        gabarit = compute_gabarit(30.0)
        nf, has_ent, eff = v.vary_floor_stacking(g, gabarit)
        # At typ heights: 4.0+2.8+3.75+3.4+3.15+2.9 = 20.0 ≤ 20.0 gabarit
        assert nf == 7
        assert has_ent is True

    def test_wide_variation_can_lose_floors(self):
        """With wide variation, some seeds can't fit all floors."""
        from core.profile import RangeParam, get_profile
        from core.grammar import HaussmannGrammar, compute_gabarit
        from core.variation import Variation

        p = get_profile("grand_boulevard")
        # Set high sigma + large variation → floors can be tall
        for attr in ("ground", "entresol", "noble", "third", "fourth", "fifth"):
            rp = getattr(p.floors, attr)
            setattr(p.floors, attr, RangeParam(rp.typ, rp.variation, 1.5))
        g = HaussmannGrammar(profile=p)
        gabarit = compute_gabarit(30.0)
        # Over many seeds, at least one should lose a floor
        lost = False
        for seed in range(50):
            v = Variation(seed=seed, style=StylePreset.BOULEVARD)
            nf, _, _ = v.vary_floor_stacking(g, gabarit)
            if nf < 7:
                lost = True
                break
        assert lost, "Expected at least one seed to lose a floor with wide variation"

    def test_entresol_never_on_modest(self):
        """MODEST has entresol_include_pct=0 — never includes entresol."""
        from core.profile import get_profile
        from core.grammar import HaussmannGrammar, compute_gabarit
        from core.variation import Variation

        p = get_profile("modest")
        g = HaussmannGrammar(profile=p)
        gabarit = compute_gabarit(8.0)
        for seed in range(50):
            v = Variation(seed=seed, style=StylePreset.MODEST)
            _, has_ent, _ = v.vary_floor_stacking(g, gabarit)
            assert has_ent is False

    def test_entresol_override_respected(self):
        """has_entresol override forces entresol on/off."""
        from core.profile import RangeParam, get_profile
        from core.grammar import HaussmannGrammar, compute_gabarit
        from core.variation import Variation

        p = get_profile("grand_boulevard")
        # sigma=0 → typ heights, deterministic
        for attr in ("ground", "entresol", "noble", "third", "fourth", "fifth", "mansard"):
            rp = getattr(p.floors, attr)
            setattr(p.floors, attr, RangeParam(rp.typ, rp.variation, 0.0))
        g = HaussmannGrammar(profile=p)
        gabarit = compute_gabarit(30.0)

        # Force entresol off
        v = Variation(seed=0, style=StylePreset.BOULEVARD)
        _, has_ent, _ = v.vary_floor_stacking(g, gabarit, has_entresol_override=False)
        assert has_ent is False

    def test_always_8_rng_calls(self):
        """vary_floor_stacking always consumes exactly 8 RNG calls."""
        from core.profile import get_profile
        from core.grammar import HaussmannGrammar, compute_gabarit
        from core.variation import Variation
        import random

        for preset, style in [
            ("grand_boulevard", StylePreset.BOULEVARD),
            ("residential", StylePreset.RESIDENTIAL),
            ("modest", StylePreset.MODEST),
        ]:
            p = get_profile(preset)
            g = HaussmannGrammar(profile=p)
            gabarit = compute_gabarit(p.typical_street_width.typ)

            # Run stacking, then check RNG state matches consuming 8 calls
            v = Variation(seed=42, style=style)
            v.vary_floor_stacking(g, gabarit)
            state_after = v.rng.getstate()

            # Compare with a raw RNG that consumed exactly 8 calls
            ref = random.Random(42)
            for _ in range(8):
                ref.random()
            assert state_after == ref.getstate(), f"{preset}: RNG consumed != 8 calls"

    def test_narrow_street_reduces_floors(self):
        """Very narrow street (6m) → gabarit 11.7m → fewer floors."""
        config = BuildingConfig(
            style_preset="MODEST", lot_width=10.0, seed=1,
            street_width=6.0,
        )
        building = generate_building(config)
        assert building.num_floors < 6

    def test_street_width_range_produces_gabarit_variation(self):
        """Same preset with different seeds can produce different floor counts
        when street_width is drawn from the range."""
        floor_counts = set()
        for seed in range(100):
            config = BuildingConfig(style_preset="MODEST", lot_width=10.0, seed=seed)
            building = generate_building(config)
            floor_counts.add(building.num_floors)
        # MODEST range (6,8,9) spans the 7.8m threshold → should see both
        # 5 floors (gabarit 11.7m) and 6 floors (gabarit 14.6m)
        assert len(floor_counts) > 1, f"Expected variation, got {floor_counts}"


class TestBalconyDecisions:
    """Probabilistic balcony system via BuildingDecisions."""

    def test_grand_always_continuous(self):
        """GRAND preset: all probabilities 0 → noble+fifth always CONTINUOUS."""
        from core.types import BalconyType, FloorType
        from core.profile import get_profile
        from core.grammar import HaussmannGrammar
        from core.variation import Variation

        p = get_profile("grand_boulevard")
        g = HaussmannGrammar(profile=p)
        for seed in range(50):
            v = Variation(seed=seed, style=StylePreset.BOULEVARD)
            bt = v.vary_balcony_types(g)
            assert bt[FloorType.NOBLE] == BalconyType.CONTINUOUS
            assert bt[FloorType.FIFTH] == BalconyType.CONTINUOUS

    def test_residential_always_continuous(self):
        """RESIDENTIAL preset: all probabilities 0 → noble+fifth always CONTINUOUS."""
        from core.types import BalconyType, FloorType
        from core.profile import get_profile
        from core.grammar import HaussmannGrammar
        from core.variation import Variation

        p = get_profile("residential")
        g = HaussmannGrammar(profile=p)
        for seed in range(50):
            v = Variation(seed=seed, style=StylePreset.RESIDENTIAL)
            bt = v.vary_balcony_types(g)
            assert bt[FloorType.NOBLE] == BalconyType.CONTINUOUS
            assert bt[FloorType.FIFTH] == BalconyType.CONTINUOUS

    def test_modest_noble_distribution(self):
        """MODEST noble: ~40% NONE, ~30% BALCONETTE, ~30% CONTINUOUS across seeds."""
        from core.types import BalconyType, FloorType
        from core.profile import get_profile
        from core.grammar import HaussmannGrammar
        from core.variation import Variation
        from collections import Counter

        p = get_profile("modest")
        g = HaussmannGrammar(profile=p)
        counts: Counter[BalconyType] = Counter()
        n = 1000
        for seed in range(n):
            v = Variation(seed=seed, style=StylePreset.MODEST)
            bt = v.vary_balcony_types(g)
            counts[bt[FloorType.NOBLE]] += 1
        # All three types should appear
        assert counts[BalconyType.NONE] > 0
        assert counts[BalconyType.BALCONETTE] > 0
        assert counts[BalconyType.CONTINUOUS] > 0
        # Rough distribution check (±10% tolerance)
        assert abs(counts[BalconyType.NONE] / n - 0.40) < 0.10
        assert abs(counts[BalconyType.BALCONETTE] / n - 0.30) < 0.10
        assert abs(counts[BalconyType.CONTINUOUS] / n - 0.30) < 0.10

    def test_fifth_never_exceeds_noble(self):
        """Fifth floor balcony rank never exceeds noble's rank."""
        from core.types import BalconyType, FloorType
        from core.profile import get_profile
        from core.grammar import HaussmannGrammar
        from core.variation import Variation, _BALCONY_RANK

        p = get_profile("modest")
        g = HaussmannGrammar(profile=p)
        for seed in range(500):
            v = Variation(seed=seed, style=StylePreset.MODEST)
            bt = v.vary_balcony_types(g)
            assert _BALCONY_RANK[bt[FloorType.FIFTH]] <= _BALCONY_RANK[bt[FloorType.NOBLE]]

    def test_always_2_rng_calls(self):
        """vary_balcony_types always consumes exactly 2 RNG calls."""
        from core.profile import get_profile
        from core.grammar import HaussmannGrammar
        from core.variation import Variation
        import random

        for preset, style in [
            ("grand_boulevard", StylePreset.BOULEVARD),
            ("residential", StylePreset.RESIDENTIAL),
            ("modest", StylePreset.MODEST),
        ]:
            p = get_profile(preset)
            g = HaussmannGrammar(profile=p)

            v = Variation(seed=99, style=style)
            v.vary_balcony_types(g)
            state_after = v.rng.getstate()

            ref = random.Random(99)
            for _ in range(2):
                ref.random()
            assert state_after == ref.getstate(), f"{preset}: RNG consumed != 2 calls"

    def test_decisions_affect_front_facade(self):
        """MODEST front facade should sometimes lack noble balcony."""
        from core.types import BalconyNode, FloorType

        # Find a seed where noble gets NONE
        found_no_balcony = False
        for seed in range(100):
            config = BuildingConfig(
                style_preset="MODEST", lot_width=10.0, seed=seed,
                street_width=8.0,
            )
            building = generate_building(config)
            front = [c for c in building.children
                     if isinstance(c, FacadeNode) and c.orientation == Orientation.SOUTH][0]
            noble_floors = [c for c in front.children
                           if isinstance(c, FloorNode) and c.floor_type == FloorType.NOBLE]
            if noble_floors:
                balconies = [c for c in noble_floors[0].children
                             if isinstance(c, BalconyNode) and c.is_continuous]
                if len(balconies) == 0:
                    found_no_balcony = True
                    break
        assert found_no_balcony, "Expected at least one MODEST seed with no noble balcony"


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


class TestSampleRange:
    """Tests for the truncated normal sampling via RangeParam."""

    def test_sigma_zero_returns_typ(self):
        """sigma=0 always returns typ regardless of RNG."""
        from core.profile import RangeParam
        from core.variation import Variation

        rp = RangeParam(3.5, 0.5, 0.0)
        for seed in range(20):
            v = Variation(seed=seed)
            assert v.sample_range(rp) == 3.5

    def test_variation_zero_returns_typ(self):
        """variation=0 always returns typ."""
        from core.profile import RangeParam
        from core.variation import Variation

        rp = RangeParam(2.0, 0.0, 0.5)
        for seed in range(20):
            v = Variation(seed=seed)
            assert v.sample_range(rp) == 2.0

    def test_stays_in_bounds(self):
        """Sampled values always stay within [min, max]."""
        from core.profile import RangeParam
        from core.variation import Variation

        rp = RangeParam(3.0, 0.5, 1.5)
        for seed in range(500):
            v = Variation(seed=seed)
            val = v.sample_range(rp)
            assert rp.min <= val <= rp.max, (
                f"seed {seed}: {val} not in [{rp.min}, {rp.max}]"
            )

    def test_exactly_one_rng_call(self):
        """sample_range consumes exactly 1 RNG call."""
        import random
        from core.profile import RangeParam
        from core.variation import Variation

        rp = RangeParam(3.0, 0.5, 0.4)
        v = Variation(seed=42)
        v.sample_range(rp)
        state_after = v.rng.getstate()

        ref = random.Random(42)
        ref.random()
        assert state_after == ref.getstate()

    def test_high_sigma_spread(self):
        """High sigma should produce values spread across the range."""
        from core.profile import RangeParam
        from core.variation import Variation

        rp = RangeParam(5.0, 2.0, 2.0)
        values = []
        for seed in range(500):
            v = Variation(seed=seed)
            values.append(v.sample_range(rp))
        # Should use most of the range
        assert max(values) - min(values) > 2.0, (
            f"Spread {max(values) - min(values):.3f} too narrow for high sigma"
        )

    def test_low_sigma_peaked(self):
        """Low sigma should cluster values near typ."""
        from core.profile import RangeParam
        from core.variation import Variation

        rp = RangeParam(5.0, 2.0, 0.2)
        values = []
        for seed in range(500):
            v = Variation(seed=seed)
            values.append(v.sample_range(rp))
        # Most values should be near typ
        near_typ = sum(1 for v in values if abs(v - 5.0) < 0.5)
        assert near_typ > 300, f"Only {near_typ}/500 near typ with low sigma"


class TestDeriveChildRng:
    """Tests for the seed hierarchy / derive_child_rng system."""

    def test_deterministic(self):
        """Same seed + component always produces same child."""
        v1 = Variation(seed=42, style=StylePreset.MODEST)
        v2 = Variation(seed=42, style=StylePreset.MODEST)
        c1 = v1.derive_child_rng("front")
        c2 = v2.derive_child_rng("front")
        assert [c1.rng.random() for _ in range(10)] == [c2.rng.random() for _ in range(10)]

    def test_independent(self):
        """Different components produce different sequences."""
        v = Variation(seed=42, style=StylePreset.MODEST)
        c1 = v.derive_child_rng("front")
        c2 = v.derive_child_rng("roof")
        assert c1.rng.random() != c2.rng.random()

    def test_isolation(self):
        """Consuming RNG on one child doesn't affect another."""
        v = Variation(seed=42, style=StylePreset.MODEST)
        c_roof = v.derive_child_rng("roof")
        c_front = v.derive_child_rng("front")
        # Burn 100 calls on front
        for _ in range(100):
            c_front.rng.random()
        # Roof still starts at same point
        v2 = Variation(seed=42, style=StylePreset.MODEST)
        c_roof2 = v2.derive_child_rng("roof")
        assert c_roof.rng.random() == c_roof2.rng.random()

    def test_roof_stable_across_variation(self):
        """Roof decisions identical regardless of profile_variation."""
        results = []
        for var in [0.0, 0.33, 0.67, 1.0]:
            config = BuildingConfig(seed=7, style_preset="MODEST", profile_variation=var)
            building = generate_building(config)
            roof = next(c for c in building.children if isinstance(c, RoofNode))
            dormers = [c for c in roof.children if isinstance(c, DormerNode)]
            style = dormers[0].style.name if dormers else "none"
            results.append((len(dormers) > 0, style))
        assert len(set(results)) == 1, f"Roof not stable: {results}"
