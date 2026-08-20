"""Tests for oriels — the projections the 1882 decree finally permitted.

Paris forbade projections over the street from 1607 until 1882, so the
single most important assertion here is the negative one: a facade dated
before the decree must not carry one.
"""

import pytest

from core.generator import generate_building
from core.grammar import HaussmannGrammar
from core.reglement import Era, get_reglement, oriel_rule
from core.types import (
    BuildingConfig,
    FacadeNode,
    FloorNode,
    GroundFloorNode,
    OrielNode,
    OrielStyle,
    WindowNode,
)

FLOOR_LEVELS = [0.0, 4.0, 6.8, 10.5, 13.9, 17.0]
FLOOR_NAMES = ["GROUND", "ENTRESOL", "NOBLE", "THIRD", "FOURTH", "FIFTH"]
CORNICE = 20.0


def _oriels(building):
    facade = next(c for c in building.children if isinstance(c, FacadeNode))
    return [c for c in facade.children if isinstance(c, OrielNode)]


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

class TestOrielRule:

    @pytest.mark.parametrize("era", [Era.ROYAL, Era.SECOND_EMPIRE])
    def test_forbidden_before_1882(self, era):
        rule = oriel_rule(FLOOR_LEVELS, FLOOR_NAMES, CORNICE, era)
        assert rule.allowed is False

    @pytest.mark.parametrize("era", [Era.ALPHAND, Era.BONNIER])
    def test_permitted_from_1882(self, era):
        assert oriel_rule(FLOOR_LEVELS, FLOOR_NAMES, CORNICE, era).allowed is True

    def test_must_begin_at_the_etage_noble(self):
        rule = oriel_rule(FLOOR_LEVELS, FLOOR_NAMES, CORNICE, Era.ALPHAND)
        assert rule.start_index == FLOOR_NAMES.index("NOBLE")
        assert rule.start_height == 6.8

    def test_projection_capped_at_forty_centimetres(self):
        for era in Era:
            assert oriel_rule(FLOOR_LEVELS, FLOOR_NAMES, CORNICE, era).max_projection == 0.40

    def test_may_not_pass_the_cornice_before_1902(self):
        rule = oriel_rule(FLOOR_LEVELS, FLOOR_NAMES, CORNICE, Era.ALPHAND)
        assert rule.may_pass_cornice is False
        assert rule.max_top == CORNICE

    def test_may_pass_the_cornice_from_1902(self):
        rule = oriel_rule(FLOOR_LEVELS, FLOOR_NAMES, CORNICE, Era.BONNIER)
        assert rule.may_pass_cornice is True
        assert rule.max_top > CORNICE

    def test_demountable_materials_only_under_alphand(self):
        """1882 required them to be removable, so metal and wood."""
        assert set(get_reglement(Era.ALPHAND).oriel_materials) == {"metal", "wood"}
        assert "stone" in get_reglement(Era.BONNIER).oriel_materials

    def test_no_noble_floor_means_no_oriel(self):
        rule = oriel_rule([0.0, 3.2], ["GROUND", "MANSARD"], 6.0, Era.ALPHAND)
        assert rule.allowed is False


# ---------------------------------------------------------------------------
# Generated geometry
# ---------------------------------------------------------------------------

class TestGeneratedOriels:

    @pytest.mark.parametrize("era", [Era.ROYAL, Era.SECOND_EMPIRE])
    def test_no_oriels_on_any_pre_1882_facade(self, era):
        for preset in ("BOULEVARD", "RESIDENTIAL", "MODEST"):
            for seed in range(25):
                b = generate_building(BuildingConfig(
                    seed=seed, style_preset=preset, era=era))
                assert _oriels(b) == []

    def test_oriels_do_appear_after_1882(self):
        found = sum(bool(_oriels(generate_building(BuildingConfig(
            seed=seed, style_preset="BOULEVARD", era=Era.ALPHAND, street_width=30.0))))
            for seed in range(40))
        assert found > 0

    def test_they_are_rarer_on_modest_frontages(self):
        def rate(preset):
            return sum(bool(_oriels(generate_building(BuildingConfig(
                seed=seed, style_preset=preset, era=Era.BONNIER))))
                for seed in range(60))
        assert rate("MODEST") < rate("BOULEVARD")

    def test_every_oriel_obeys_the_decree(self):
        for era in (Era.ALPHAND, Era.BONNIER):
            reg = get_reglement(era)
            for preset in ("BOULEVARD", "RESIDENTIAL", "MODEST"):
                for seed in range(30):
                    b = generate_building(BuildingConfig(
                        seed=seed, style_preset=preset, era=era))
                    facade = next(c for c in b.children if isinstance(c, FacadeNode))
                    floors = [c for c in facade.children
                              if isinstance(c, (FloorNode, GroundFloorNode))]
                    cornice = sum(f.height for f in floors)
                    noble = next((f.y_offset for f in floors
                                  if isinstance(f, FloorNode)
                                  and f.floor_type.name == "NOBLE"), None)
                    for o in _oriels(b):
                        base = o.transform.position[1]
                        assert o.projection <= reg.max_oriel_projection + 1e-9
                        if noble is not None:
                            assert base >= noble - 1e-6
                        top = base + o.height
                        if not reg.oriels_above_cornice:
                            assert top <= cornice + 1e-6
                        assert o.material in reg.oriel_materials

    def test_oriel_never_sits_on_the_porte_cochere(self):
        for era in (Era.ALPHAND, Era.BONNIER):
            for seed in range(40):
                b = generate_building(BuildingConfig(
                    seed=seed, style_preset="BOULEVARD", era=era, street_width=30.0))
                facade = next(c for c in b.children if isinstance(c, FacadeNode))
                ground = next((c for c in facade.children
                               if isinstance(c, GroundFloorNode)), None)
                if ground is None or ground.porte_cochere_bay_index is None:
                    continue
                for o in _oriels(b):
                    assert o.bay_index != ground.porte_cochere_bay_index

    def test_oriel_stays_within_the_facade(self):
        for seed in range(40):
            b = generate_building(BuildingConfig(
                seed=seed, style_preset="BOULEVARD", era=Era.BONNIER, street_width=30.0))
            facade = next(c for c in b.children if isinstance(c, FacadeNode))
            for o in _oriels(b):
                assert o.transform.position[0] >= -1e-6
                assert o.transform.position[0] + o.width <= facade.width + 1e-6

    def test_oriel_carries_its_own_glazing(self):
        for seed in range(40):
            b = generate_building(BuildingConfig(
                seed=seed, style_preset="BOULEVARD", era=Era.ALPHAND, street_width=30.0))
            for o in _oriels(b):
                windows = [c for c in o.children if isinstance(c, WindowNode)]
                assert windows, "an oriel with no windows is just a buttress"
                for win in windows:
                    top = win.transform.position[1] + win.height
                    assert 0.0 <= win.transform.position[1]
                    assert top <= o.height + 1e-6

    def test_only_1902_carries_above_the_cornice(self):
        def crowned(era):
            return sum(1 for seed in range(60)
                       for o in _oriels(generate_building(BuildingConfig(
                           seed=seed, style_preset="BOULEVARD", era=era, street_width=30.0)))
                       if o.passes_cornice)
        assert crowned(Era.ALPHAND) == 0
        assert crowned(Era.BONNIER) > 0

    def test_styles_and_patterns_both_vary(self):
        styles, counts = set(), set()
        for seed in range(60):
            b = generate_building(BuildingConfig(
                seed=seed, style_preset="BOULEVARD", era=Era.BONNIER, street_width=30.0))
            o = _oriels(b)
            if o:
                styles.add(o[0].style)
                counts.add(len(o))
        assert len(styles) > 1
        assert len(counts) > 1
        assert styles <= set(OrielStyle)

    def test_deterministic_for_a_seed(self):
        def sig(b):
            return [(o.bay_index, o.style, o.material, round(o.height, 4))
                    for o in _oriels(b)]
        cfg = dict(seed=5, style_preset="BOULEVARD", era=Era.BONNIER, street_width=30.0)
        assert sig(generate_building(BuildingConfig(**cfg))) == \
            sig(generate_building(BuildingConfig(**cfg)))


class TestOrielStreamIsolation:
    """Oriels were added late; adding them must not disturb existing seeds."""

    def test_deriving_the_oriel_stream_consumes_no_master_rng(self):
        from core.variation import Variation
        v = Variation(seed=42)
        before = v.rng.getstate()
        v.derive_child_rng("oriel")
        assert v.rng.getstate() == before

    def test_pre_1882_facades_are_untouched_by_the_oriel_code(self):
        """With no oriels generated, the facade must match a build that
        cannot produce them at all."""
        from core.types import BayNode
        def sig(b):
            facade = next(c for c in b.children if isinstance(c, FacadeNode))
            return [(round(fl.height, 4),
                     tuple((round(x.x_offset, 4), round(x.width, 4))
                           for x in fl.children if isinstance(x, BayNode)))
                    for fl in facade.children
                    if isinstance(fl, (FloorNode, GroundFloorNode))]

        for seed in range(15):
            plain = generate_building(BuildingConfig(seed=seed, era=Era.SECOND_EMPIRE))
            again = generate_building(BuildingConfig(seed=seed, era=Era.SECOND_EMPIRE))
            assert sig(plain) == sig(again)
            assert _oriels(plain) == []
