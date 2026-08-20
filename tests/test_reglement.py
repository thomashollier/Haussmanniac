"""Tests for the regulatory model in :mod:`core.reglement`.

The numbers asserted here are the ones the decrees actually state, so a
failure means the model has drifted from the law it claims to encode.
"""

import math

import pytest

from core.generator import generate_building
from core.grammar import HaussmannGrammar, compute_gabarit
from core.profile import GRAND_BOULEVARD
from core.reglement import (
    Era,
    RoofEnvelope,
    balcony_rule,
    compute_envelope,
    era_for_year,
    get_reglement,
)
from core.types import (
    BalconyNode,
    BuildingConfig,
    FacadeNode,
    FloorNode,
    GroundFloorNode,
    MansardSlopeNode,
    MansardType,
    RoofNode,
)


# ---------------------------------------------------------------------------
# Height tables
# ---------------------------------------------------------------------------

class TestHeightTables:
    """Facade height as a function of street width, per decree."""

    @pytest.mark.parametrize("street,expected", [
        (5.0, 11.70),    # under 7.80 m — six toises
        (7.80, 11.70),   # boundary belongs to the lower step
        (9.00, 14.62),   # 7.80–9.75 m — sept toises trois pieds
        (12.0, 17.55),   # over 9.75 m — neuf toises
        (30.0, 17.55),   # the 20 m step does not exist before 1859
    ])
    def test_royal_1783_table(self, street, expected):
        assert get_reglement(Era.ROYAL).facade_height_limit(street) == expected

    @pytest.mark.parametrize("street,expected", [
        (5.0, 11.70),
        (9.00, 14.62),
        (12.0, 17.55),
        (20.0, 17.55),
        (25.0, 20.00),   # 1859 adds 20 m for the new wide percées
    ])
    def test_second_empire_1859_table(self, street, expected):
        assert get_reglement(Era.SECOND_EMPIRE).facade_height_limit(street) == expected

    @pytest.mark.parametrize("street,expected", [
        (5.0, 12.0),
        (9.00, 15.0),
        (12.0, 18.0),
        (25.0, 20.0),
    ])
    def test_alphand_1884_table(self, street, expected):
        """The 1884 decree raises every step."""
        assert get_reglement(Era.ALPHAND).facade_height_limit(street) == expected

    def test_1884_raises_every_step_above_1859(self):
        old = get_reglement(Era.SECOND_EMPIRE)
        new = get_reglement(Era.ALPHAND)
        for street in (5.0, 9.0, 12.0, 25.0):
            assert new.facade_height_limit(street) >= old.facade_height_limit(street)

    def test_compute_gabarit_defaults_to_1859(self):
        assert compute_gabarit(30.0) == 20.00
        assert compute_gabarit(12.0) == 17.55
        assert compute_gabarit(8.0) == 14.62
        assert compute_gabarit(5.0) == 11.70

    def test_compute_gabarit_takes_an_era(self):
        assert compute_gabarit(12.0, Era.ALPHAND) == 18.0
        assert compute_gabarit(12.0, "SECOND_EMPIRE") == 17.55


class TestEraLookup:
    @pytest.mark.parametrize("year,era", [
        (1800, Era.ROYAL),
        (1858, Era.ROYAL),
        (1859, Era.SECOND_EMPIRE),
        (1870, Era.SECOND_EMPIRE),
        (1884, Era.ALPHAND),
        (1901, Era.ALPHAND),
        (1902, Era.BONNIER),
        (1913, Era.BONNIER),
    ])
    def test_era_for_year(self, year, era):
        assert era_for_year(year) == era

    def test_get_reglement_accepts_name_or_enum(self):
        assert get_reglement("ALPHAND").era == Era.ALPHAND
        assert get_reglement("alphand").era == Era.ALPHAND
        assert get_reglement(Era.ALPHAND).era == Era.ALPHAND

    def test_unknown_era_lists_the_valid_ones(self):
        with pytest.raises(KeyError, match="SECOND_EMPIRE"):
            get_reglement("napoleon")


# ---------------------------------------------------------------------------
# Roof envelope geometry
# ---------------------------------------------------------------------------

class TestRoofEnvelope:

    def test_1884_ceiling_is_28_50(self):
        """20 m of facade plus an 8.50 m comble — the documented ceiling."""
        env = compute_envelope(30.0, Era.ALPHAND, parcel_depth=40.0)
        assert env.facade_height == 20.0
        assert env.legal_ridge_height == pytest.approx(8.50, abs=1e-6)
        assert env.total_height == pytest.approx(28.50, abs=1e-6)

    def test_pre_1884_comble_is_a_45_degree_diagonal(self):
        env = compute_envelope(30.0, Era.SECOND_EMPIRE, parcel_depth=20.0)
        assert env.roof_envelope == RoofEnvelope.DIAGONAL_45
        # Inscribed below a 45° diagonal: one metre in per metre up.
        for h in (0.5, 1.0, 2.5):
            assert env.setback_at(h) == pytest.approx(h)
        lower, upper, _ = env.mansard_angles()
        assert lower == 45.0 and upper == 45.0

    def test_a_steeper_than_45_comble_is_illegal_before_1884(self):
        """A near-vertical face sits outside the diagonal envelope."""
        env = compute_envelope(30.0, Era.SECOND_EMPIRE, parcel_depth=20.0)
        h = 2.0
        near_vertical_inset = h / math.tan(math.radians(80))
        assert near_vertical_inset < env.setback_at(h)

    def test_1884_arc_starts_near_vertical_and_flattens(self):
        env = compute_envelope(30.0, Era.ALPHAND, parcel_depth=40.0)
        assert env.roof_envelope == RoofEnvelope.CIRCULAR_ARC
        r = env.arc_radius
        # Near the eaves the arc gives away almost no depth...
        assert env.setback_at(0.1 * r) < 0.1 * r
        # ...and it is horizontal by the time it reaches the apex.
        assert env.setback_at(r) == pytest.approx(r)

    def test_1884_arc_permits_more_comble_than_the_diagonal(self):
        """This is the extra storey the 1884 decree was understood to allow."""
        old = compute_envelope(30.0, Era.SECOND_EMPIRE, parcel_depth=40.0)
        new = compute_envelope(30.0, Era.ALPHAND, parcel_depth=40.0)
        assert new.legal_ridge_height > old.legal_ridge_height

    def test_1902_arc_runs_onto_a_45_degree_oblique(self):
        env = compute_envelope(30.0, Era.BONNIER, parcel_depth=60.0)
        assert env.roof_envelope == RoofEnvelope.EIGHTH_ARC_OBLIQUE
        h_break = env.arc_radius * math.sin(math.pi / 4)
        # Past the eighth of arc, height and inset advance together — 45°.
        a = env.setback_at(h_break + 1.0)
        b = env.setback_at(h_break + 2.0)
        assert b - a == pytest.approx(1.0)

    def test_1902_allows_a_taller_ridge_on_a_deep_parcel(self):
        """'Dans le cas d'une grande parcelle, la hauteur au centre peut
        donc être très élevée' — the opening Sauvage used at rue Vavin."""
        shallow = compute_envelope(30.0, Era.BONNIER, parcel_depth=8.0)
        deep = compute_envelope(30.0, Era.BONNIER, parcel_depth=60.0)
        assert deep.legal_ridge_height > shallow.legal_ridge_height

    def test_setback_is_monotonic_for_every_era(self):
        for era in Era:
            env = compute_envelope(30.0, era, parcel_depth=40.0)
            prev = -1.0
            for i in range(40):
                s = env.setback_at(i * 0.25)
                assert s >= prev - 1e-9
                prev = s

    def test_setback_and_max_height_are_inverse(self):
        for era in Era:
            env = compute_envelope(30.0, era, parcel_depth=40.0)
            for h in (0.5, 1.5, 3.0):
                if h > env.legal_ridge_height:
                    continue
                assert env.max_height_for_setback(env.setback_at(h)) == pytest.approx(h, abs=1e-6)

    def test_shallow_parcel_limits_the_ridge(self):
        wide = compute_envelope(30.0, Era.ALPHAND, parcel_depth=40.0)
        narrow = compute_envelope(30.0, Era.ALPHAND, parcel_depth=6.0)
        assert narrow.legal_ridge_height < wide.legal_ridge_height

    def test_roof_fill_and_max_ridge_only_lower_the_comble(self):
        full = compute_envelope(30.0, Era.ALPHAND, parcel_depth=40.0)
        half = compute_envelope(30.0, Era.ALPHAND, parcel_depth=40.0, roof_fill=0.5)
        capped = compute_envelope(30.0, Era.ALPHAND, parcel_depth=40.0, max_ridge=2.0)
        assert half.ridge_height == pytest.approx(full.ridge_height * 0.5)
        assert capped.ridge_height == 2.0
        # The legal ceiling is recorded whatever the builder chose to do.
        assert capped.legal_ridge_height == full.legal_ridge_height


class TestSlopeProfile:

    def test_profile_starts_at_the_eaves_and_reaches_the_ridge(self):
        for era in Era:
            env = compute_envelope(30.0, era, parcel_depth=20.0)
            pts = env.slope_profile()
            assert pts[0] == (0.0, 0.0)
            assert pts[-1][1] == pytest.approx(env.ridge_height, abs=1e-3)

    def test_profile_is_monotonic(self):
        for era in Era:
            pts = compute_envelope(30.0, era, parcel_depth=20.0).slope_profile()
            for (i0, h0), (i1, h1) in zip(pts, pts[1:]):
                assert i1 >= i0 - 1e-9
                assert h1 >= h0 - 1e-9

    def test_diagonal_profile_is_two_points_a_curve_is_many(self):
        assert len(compute_envelope(30.0, Era.SECOND_EMPIRE, parcel_depth=20.0).slope_profile()) == 2
        assert len(compute_envelope(30.0, Era.ALPHAND, parcel_depth=20.0).slope_profile()) > 5


# ---------------------------------------------------------------------------
# The 1823 balcony ordinance
# ---------------------------------------------------------------------------

class TestBalconyRule:

    def test_nothing_below_six_metres(self):
        rule = balcony_rule([0.0, 3.0, 5.9], Era.SECOND_EMPIRE)
        assert rule.continuous == []
        assert rule.individual == []

    def test_first_line_lands_on_the_noble_floor_with_an_entresol(self):
        # ground 4.0 + entresol 2.8 puts the noble floor at 6.8 m
        levels = [0.0, 4.0, 6.8, 10.5, 13.9, 17.0]
        rule = balcony_rule(levels, Era.SECOND_EMPIRE)
        assert rule.continuous[0] == 2

    def test_without_an_entresol_the_line_moves_up_a_storey(self):
        # ground 3.2 leaves the second storey at 3.2 m — below the limit
        levels = [0.0, 3.2, 6.15, 8.95, 11.65]
        rule = balcony_rule(levels, Era.SECOND_EMPIRE)
        assert rule.continuous[0] == 2

    def test_second_line_is_the_topmost_eligible_floor(self):
        levels = [0.0, 4.0, 6.8, 10.5, 13.9, 17.0]
        rule = balcony_rule(levels, Era.SECOND_EMPIRE)
        assert rule.continuous == [2, 5]

    def test_second_line_can_be_suppressed(self):
        levels = [0.0, 4.0, 6.8, 10.5, 13.9, 17.0]
        assert balcony_rule(levels, Era.SECOND_EMPIRE, second_line=False).continuous == [2]

    def test_individual_balconies_only_appear_late(self):
        levels = [0.0, 4.0, 6.8, 10.5, 13.9, 17.0]
        assert balcony_rule(levels, Era.SECOND_EMPIRE).individual == []
        assert balcony_rule(levels, Era.ALPHAND).individual == [3, 4]

    def test_projection_cap_is_eighty_centimetres(self):
        for era in Era:
            assert balcony_rule([0.0, 7.0], era).max_projection == 0.80


# ---------------------------------------------------------------------------
# Integration with the generator
# ---------------------------------------------------------------------------

def _front_slope(building):
    roof = next(c for c in building.children if isinstance(c, RoofNode))
    return next(c for c in roof.children if isinstance(c, MansardSlopeNode))


class TestGeneratorIntegration:

    def test_era_changes_the_roof_and_nothing_crashes(self):
        shapes = {}
        for era in Era:
            b = generate_building(BuildingConfig(
                seed=42, style_preset="BOULEVARD", era=era, street_width=30.0))
            shapes[era] = _front_slope(b).mansard_type
        assert shapes[Era.SECOND_EMPIRE] == MansardType.DIAGONAL
        assert shapes[Era.ALPHAND] == MansardType.BROKEN

    def test_second_empire_roof_is_a_forty_five_degree_comble(self):
        b = generate_building(BuildingConfig(seed=1, era=Era.SECOND_EMPIRE, street_width=12.0))
        assert math.degrees(_front_slope(b).lower_angle) == pytest.approx(45.0)

    def test_front_slope_carries_the_envelope_profile(self):
        b = generate_building(BuildingConfig(seed=1, era=Era.ALPHAND, street_width=12.0))
        slope = _front_slope(b)
        assert len(slope.envelope_profile) > 2
        assert slope.roof_envelope == RoofEnvelope.CIRCULAR_ARC

    def test_year_resolves_the_era_and_beats_era_field(self):
        b = generate_building(BuildingConfig(seed=1, year=1868, era=Era.BONNIER))
        assert b.era == Era.SECOND_EMPIRE

    def test_building_records_the_era_it_was_built_under(self):
        b = generate_building(BuildingConfig(seed=1, era=Era.ALPHAND, street_width=12.0))
        assert b.era == Era.ALPHAND
        assert b.street_width == pytest.approx(12.0)

    def test_no_balcony_sits_below_six_metres(self):
        for era in Era:
            for preset in ("BOULEVARD", "RESIDENTIAL", "MODEST"):
                for seed in range(12):
                    b = generate_building(BuildingConfig(
                        seed=seed, style_preset=preset, era=era))
                    facade = next(c for c in b.children if isinstance(c, FacadeNode))
                    for fl in facade.children:
                        if not isinstance(fl, (FloorNode, GroundFloorNode)):
                            continue
                        has_balcony = any(isinstance(c, BalconyNode) for c in fl.children)
                        if has_balcony:
                            assert fl.transform.position[1] >= 6.0 - 1e-6

    def test_habitable_storeys_respect_the_1859_minimum(self):
        from core.types import FloorType
        for seed in range(20):
            b = generate_building(BuildingConfig(seed=seed, era=Era.SECOND_EMPIRE))
            facade = next(c for c in b.children if isinstance(c, FacadeNode))
            for fl in facade.children:
                if isinstance(fl, FloorNode) and fl.floor_type != FloorType.ENTRESOL:
                    assert fl.height >= 2.60 - 1e-6


class TestNoSharedStateLeaks:
    """A grammar must never write sampled values back into a shared preset."""

    def test_generating_does_not_mutate_the_module_level_preset(self):
        before = (GRAND_BOULEVARD.floors.ground.typ,
                  GRAND_BOULEVARD.bays.door_bay_width_ratio)
        grammar = HaussmannGrammar()
        generate_building(BuildingConfig(seed=1), grammar=grammar)
        generate_building(BuildingConfig(seed=2), grammar=grammar)
        after = (GRAND_BOULEVARD.floors.ground.typ,
                 GRAND_BOULEVARD.bays.door_bay_width_ratio)
        assert before == after

    def test_reusing_a_grammar_gives_the_same_building(self):
        def bays(b):
            from core.types import BayNode
            facade = next(c for c in b.children if isinstance(c, FacadeNode))
            return [(round(fl.height, 4),
                     tuple(round(x.x_offset, 4) for x in fl.children if isinstance(x, BayNode)))
                    for fl in facade.children
                    if isinstance(fl, (FloorNode, GroundFloorNode))]

        first = generate_building(BuildingConfig(seed=9), grammar=HaussmannGrammar())
        generate_building(BuildingConfig(seed=123), grammar=HaussmannGrammar())
        second = generate_building(BuildingConfig(seed=9), grammar=HaussmannGrammar())
        assert bays(first) == bays(second)
