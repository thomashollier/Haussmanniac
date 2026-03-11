"""Tests for core/grammar.py — Haussmann proportional rules.

Validated against documented measurements from:
- François Loyer, *Paris XIXe siècle* (1987)
- Measured surveys: Bd Haussmann nos. 23-29, Rue de Rivoli, Av de l'Opéra
- Paris building regulations (1859, 1882, 1902 voirie rules)
"""

from core.grammar import HaussmannGrammar, FloorSpec, BaySpec, WindowSpec
from core.types import (
    BayType,
    DormerStyle,
    FloorType,
    OrnamentLevel,
    PedimentStyle,
    RailingPattern,
    StylePreset,
    SurroundStyle,
)


grammar = HaussmannGrammar()


# ---------------------------------------------------------------------------
# Floor stacking
# ---------------------------------------------------------------------------

class TestFloorSequence:
    def test_standard_six_floor(self):
        """A typical 6-storey Haussmann: ground + entresol + noble + 3rd + 4th + mansard."""
        seq = grammar.floor_sequence(6, has_entresol=True)
        assert seq == [
            FloorType.GROUND,
            FloorType.ENTRESOL,
            FloorType.NOBLE,
            FloorType.THIRD,
            FloorType.FOURTH,
            FloorType.MANSARD,
        ]
        assert len(seq) == 6

    def test_seven_floor_boulevard(self):
        """7-storey building: ground + entresol + noble + 3rd + 4th + 5th + mansard."""
        seq = grammar.floor_sequence(7, has_entresol=True)
        assert seq[0] == FloorType.GROUND
        assert seq[1] == FloorType.ENTRESOL
        assert seq[2] == FloorType.NOBLE
        assert seq[-1] == FloorType.MANSARD
        assert len(seq) == 7

    def test_no_entresol(self):
        """Without entresol, more room for middle floors."""
        seq = grammar.floor_sequence(6, has_entresol=False)
        assert FloorType.ENTRESOL not in seq
        assert seq[0] == FloorType.GROUND
        assert seq[-1] == FloorType.MANSARD
        assert len(seq) == 6

    def test_minimal_building(self):
        """3-storey minimum: ground + one middle + mansard."""
        seq = grammar.floor_sequence(3, has_entresol=False)
        assert seq == [FloorType.GROUND, FloorType.NOBLE, FloorType.MANSARD]

    def test_two_floor(self):
        seq = grammar.floor_sequence(2)
        assert seq == [FloorType.GROUND, FloorType.MANSARD]

    def test_always_starts_with_ground(self):
        for n in range(2, 10):
            seq = grammar.floor_sequence(n)
            assert seq[0] == FloorType.GROUND

    def test_always_ends_with_mansard(self):
        for n in range(2, 10):
            seq = grammar.floor_sequence(n)
            assert seq[-1] == FloorType.MANSARD

    def test_noble_always_present_if_enough_floors(self):
        """Noble floor appears in any building with ≥3 floors."""
        for n in range(3, 10):
            seq = grammar.floor_sequence(n, has_entresol=False)
            assert FloorType.NOBLE in seq


class TestFloorHeights:
    def test_ground_floor_height(self):
        """Ground floor: 3.5-4.0 m, typical 3.8 m."""
        h = grammar.get_floor_height(FloorType.GROUND)
        assert 3.5 <= h <= 4.0

    def test_noble_floor_tallest_middle(self):
        """Noble floor must be the tallest of all non-ground floors."""
        noble_h = grammar.get_floor_height(FloorType.NOBLE)
        for ft in FloorType:
            if ft not in (FloorType.GROUND, FloorType.NOBLE):
                assert noble_h >= grammar.get_floor_height(ft), (
                    f"Noble ({noble_h}) should be >= {ft.name} ({grammar.get_floor_height(ft)})"
                )

    def test_heights_decrease_upward(self):
        """Floor heights should generally decrease from noble upward."""
        order = [FloorType.NOBLE, FloorType.THIRD, FloorType.FOURTH, FloorType.FIFTH]
        heights = [grammar.get_floor_height(ft) for ft in order]
        for i in range(len(heights) - 1):
            assert heights[i] >= heights[i + 1]

    def test_entresol_is_lowest(self):
        """Entresol is the shortest middle floor."""
        ent_h = grammar.get_floor_height(FloorType.ENTRESOL)
        for ft in [FloorType.NOBLE, FloorType.THIRD, FloorType.FOURTH, FloorType.FIFTH]:
            assert ent_h <= grammar.get_floor_height(ft)

    def test_height_ranges_valid(self):
        """All height ranges should have min < max."""
        for ft in FloorType:
            mn, mx = grammar.get_floor_height_range(ft)
            assert mn < mx

    def test_total_building_height_realistic(self):
        """A 7-storey building should be roughly 18-28 m to cornice."""
        specs = grammar.get_floor_specs(7, has_entresol=True)
        total = sum(s.height for s in specs)
        assert 18.0 <= total <= 28.0, f"Total height {total} m out of range"


class TestFloorSpecs:
    def test_spec_count_matches_floors(self):
        specs = grammar.get_floor_specs(6, has_entresol=True)
        assert len(specs) == 6

    def test_specs_have_correct_types(self):
        specs = grammar.get_floor_specs(6, has_entresol=True)
        assert all(isinstance(s, FloorSpec) for s in specs)

    def test_noble_floor_has_balcony(self):
        specs = grammar.get_floor_specs(7, has_entresol=True)
        noble = [s for s in specs if s.floor_type == FloorType.NOBLE]
        assert len(noble) == 1
        assert noble[0].has_balcony is True

    def test_fifth_floor_has_balconette(self):
        specs = grammar.get_floor_specs(7, has_entresol=True)
        fifth = [s for s in specs if s.floor_type == FloorType.FIFTH]
        assert len(fifth) == 1
        assert fifth[0].has_balconette is True


# ---------------------------------------------------------------------------
# Bay layout
# ---------------------------------------------------------------------------

class TestBayLayout:
    def test_bay_count_always_odd(self):
        """Bay count must be odd for facade symmetry."""
        for width in [10.0, 12.0, 15.0, 18.0, 20.0]:
            for style in StylePreset:
                count = grammar.compute_bay_count(width, style)
                assert count % 2 == 1, f"Width {width}, {style.name}: got even count {count}"

    def test_boulevard_has_more_bays(self):
        """Boulevard buildings should have at least 5 bays."""
        count = grammar.compute_bay_count(15.0, StylePreset.BOULEVARD)
        assert count >= 5

    def test_width_determines_bay_count(self):
        """Bay count is determined by facade width, not style preset."""
        # 15m facade → 7 bays regardless of style (threshold_7=13, threshold_9=18)
        for style in StylePreset:
            count = grammar.compute_bay_count(15.0, style)
            assert count == 7, f"15m with {style.name}: expected 7, got {count}"
        # Width thresholds (profile defaults: 5@8m, 7@13m, 9@18m)
        assert grammar.compute_bay_count(7.0) == 3
        assert grammar.compute_bay_count(10.0) == 5
        assert grammar.compute_bay_count(15.0) == 7
        assert grammar.compute_bay_count(20.0) == 9

    def test_layout_spans_facade(self):
        """Bay layout should span most of the facade width (within margins)."""
        specs = grammar.get_bay_layout(15.0, StylePreset.RESIDENTIAL)
        first_x = specs[0].x_offset
        last_right = specs[-1].x_offset + specs[-1].width
        span = last_right - first_x
        # Bays should cover a reasonable portion of facade width
        # (wider edge piers on fewer-bay facades reduce this ratio)
        assert span >= 15.0 * 0.55, f"Span {span} too narrow for 15m facade"

    def test_all_bays_equal_width(self):
        """All bays should be the same width."""
        specs = grammar.get_bay_layout(15.0)
        widths = [s.width for s in specs]
        assert all(abs(w - widths[0]) < 0.001 for w in widths)

    def test_bay_width_is_window_zone(self):
        """BaySpec.width should be the window zone (bay_w minus pier_w)."""
        specs = grammar.get_bay_layout(15.0)
        bp = grammar.profile.bays
        expected = bp.bay_width[1] * (1 - bp.pier_ratio)
        assert abs(specs[0].width - expected) < 0.001

    def test_bays_dont_overlap(self):
        """Bays must not overlap each other."""
        specs = grammar.get_bay_layout(15.0)
        for i in range(len(specs) - 1):
            right_edge = specs[i].x_offset + specs[i].width
            next_left = specs[i + 1].x_offset
            assert right_edge <= next_left + 0.001, (
                f"Bay {i} right edge ({right_edge}) overlaps bay {i+1} left ({next_left})"
            )

    def test_bay_widths_in_range(self):
        """Each bay width should be within the valid range."""
        specs = grammar.get_bay_layout(15.0)
        for s in specs:
            assert 0.8 <= s.width <= 2.0, f"Bay width {s.width} out of range"

    def test_custom_bay_count(self):
        """Explicit bay_count should override automatic calculation."""
        specs = grammar.get_bay_layout(15.0, bay_count=7)
        assert len(specs) == 7

    def test_all_bays_are_window_type(self):
        """Default bay type should be WINDOW."""
        specs = grammar.get_bay_layout(15.0)
        assert all(s.bay_type == BayType.WINDOW for s in specs)


# ---------------------------------------------------------------------------
# Ornament rules
# ---------------------------------------------------------------------------

class TestOrnamentLevels:
    def test_ground_floor_rich(self):
        assert grammar.get_ornament_level(FloorType.GROUND) == OrnamentLevel.RICH

    def test_noble_floor_rich(self):
        assert grammar.get_ornament_level(FloorType.NOBLE) == OrnamentLevel.RICH

    def test_entresol_simple(self):
        assert grammar.get_ornament_level(FloorType.ENTRESOL) == OrnamentLevel.SIMPLE

    def test_third_floor_moderate(self):
        assert grammar.get_ornament_level(FloorType.THIRD) == OrnamentLevel.MODERATE

    def test_mansard_no_ornament(self):
        assert grammar.get_ornament_level(FloorType.MANSARD) == OrnamentLevel.NONE

    def test_ornament_decreases_upward(self):
        """Ornament levels should not increase going up (except ground)."""
        order = [FloorType.NOBLE, FloorType.THIRD, FloorType.FOURTH, FloorType.FIFTH, FloorType.MANSARD]
        levels = [grammar.get_ornament_level(ft).value for ft in order]
        for i in range(len(levels) - 1):
            assert levels[i] >= levels[i + 1]


# ---------------------------------------------------------------------------
# Window spec
# ---------------------------------------------------------------------------

class TestWindowSpec:
    def test_noble_window_has_pediment(self):
        spec = grammar.get_window_spec(FloorType.NOBLE, OrnamentLevel.RICH, 1.3, 3.5)
        assert spec.pediment == PedimentStyle.TRIANGULAR

    def test_noble_window_has_keystone(self):
        spec = grammar.get_window_spec(FloorType.NOBLE, OrnamentLevel.RICH, 1.3, 3.5)
        assert spec.has_keystone is True

    def test_noble_window_pilastered(self):
        spec = grammar.get_window_spec(FloorType.NOBLE, OrnamentLevel.RICH, 1.3, 3.5)
        assert spec.surround_style == SurroundStyle.PILASTERED

    def test_upper_floor_simple_surround(self):
        spec = grammar.get_window_spec(FloorType.FOURTH, OrnamentLevel.SIMPLE, 1.3, 3.0)
        assert spec.surround_style == SurroundStyle.EARED

    def test_mansard_no_surround(self):
        spec = grammar.get_window_spec(FloorType.MANSARD, OrnamentLevel.NONE, 1.0, 2.8)
        assert spec.surround_style == SurroundStyle.NONE

    def test_window_height_proportional_to_floor(self):
        """Window should be roughly 75% of floor height (upper floors)."""
        for fh in [2.5, 3.0, 3.5, 4.0]:
            spec = grammar.get_window_spec(FloorType.THIRD, OrnamentLevel.MODERATE, 1.3, fh)
            ratio = spec.height / fh
            assert 0.60 <= ratio <= 0.85, f"Ratio {ratio} for floor height {fh}"

    def test_window_narrower_than_bay(self):
        spec = grammar.get_window_spec(FloorType.NOBLE, OrnamentLevel.RICH, 1.3, 3.5)
        assert spec.width < 1.3


# ---------------------------------------------------------------------------
# Balcony rules
# ---------------------------------------------------------------------------

class TestBalconyRules:
    def test_noble_continuous_balcony(self):
        assert grammar.has_continuous_balcony(FloorType.NOBLE) is True

    def test_fifth_no_continuous_balcony(self):
        """Default profile: 5th floor has balconettes, not continuous balcony."""
        assert grammar.has_continuous_balcony(FloorType.FIFTH) is False

    def test_ground_no_balcony(self):
        assert grammar.has_continuous_balcony(FloorType.GROUND) is False

    def test_fifth_has_balconette(self):
        assert grammar.has_balconette(FloorType.FIFTH) is True

    def test_third_no_balconette(self):
        """Default profile: only 5th floor has balconettes."""
        assert grammar.has_balconette(FloorType.THIRD) is False

    def test_noble_no_balconette(self):
        """Noble floor has continuous balcony, not balconettes."""
        assert grammar.has_balconette(FloorType.NOBLE) is False

    def test_railing_height(self):
        assert grammar.get_railing_height() == 1.0

    def test_noble_railing_classic(self):
        assert grammar.get_railing_pattern(FloorType.NOBLE) == RailingPattern.CLASSIC

    def test_fifth_railing_geometric(self):
        assert grammar.get_railing_pattern(FloorType.FIFTH) == RailingPattern.GEOMETRIC


# ---------------------------------------------------------------------------
# Roof rules
# ---------------------------------------------------------------------------

class TestRoofRules:
    def test_boulevard_steep_mansard(self):
        from core.types import MansardType
        spec = grammar.get_roof_spec(7, StylePreset.BOULEVARD)
        assert spec.mansard_type == MansardType.STEEP
        assert spec.mansard_lower_angle_deg >= 75.0

    def test_residential_broken_mansard(self):
        from core.types import MansardType
        spec = grammar.get_roof_spec(5, StylePreset.RESIDENTIAL)
        assert spec.mansard_type == MansardType.BROKEN
        assert spec.mansard_lower_angle_deg >= 65.0
        assert spec.mansard_upper_angle_deg <= 25.0
        assert spec.break_pct > 0.0

    def test_modest_broken_mansard_with_small_dormers(self):
        from core.types import MansardType
        spec = grammar.get_roof_spec(3, StylePreset.MODEST)
        assert spec.mansard_type == MansardType.BROKEN
        assert spec.break_pct == 0.95  # 95% of total height
        assert spec.dormer_every_n_bays == 1  # placement handled by dormer_placement param
        assert spec.dormer_style == DormerStyle.FLAT_SLOPE

    def test_boulevard_dormers_every_bay(self):
        spec = grammar.get_roof_spec(7, StylePreset.BOULEVARD)
        assert spec.dormer_every_n_bays == 1
        assert spec.dormer_style == DormerStyle.PEDIMENT_CURVED

    def test_modest_dormers_flat_slope(self):
        """Modest gets flat-slope dormers (placement handled by variation)."""
        spec = grammar.get_roof_spec(3, StylePreset.MODEST)
        assert spec.dormer_style == DormerStyle.FLAT_SLOPE

    def test_chimney_count_minimum(self):
        spec = grammar.get_roof_spec(3)
        assert spec.chimney_count >= 2

    def test_chimney_count_scales_with_bays(self):
        spec3 = grammar.get_roof_spec(3)
        spec7 = grammar.get_roof_spec(7)
        assert spec7.chimney_count >= spec3.chimney_count


# ---------------------------------------------------------------------------
# Ground floor rules
# ---------------------------------------------------------------------------

class TestGroundFloor:
    def test_ground_floor_height(self):
        spec = grammar.get_ground_floor_spec()
        assert 3.5 <= spec.height <= 4.0

    def test_porte_cochere_width(self):
        spec = grammar.get_ground_floor_spec(has_porte_cochere=True)
        assert spec.porte_cochere_width > 2.0

    def test_no_porte_cochere(self):
        spec = grammar.get_ground_floor_spec(has_porte_cochere=False)
        assert spec.porte_cochere_width == 0.0

    def test_rustication_on_boulevard(self):
        spec = grammar.get_ground_floor_spec(StylePreset.BOULEVARD)
        assert spec.has_rustication is True

    def test_no_rustication_on_modest(self):
        spec = grammar.get_ground_floor_spec(StylePreset.MODEST)
        assert spec.has_rustication is False

    def test_shopfront_height_proportional(self):
        spec = grammar.get_ground_floor_spec()
        ratio = spec.shopfront_height / spec.height
        assert 0.65 <= ratio <= 0.85


# ---------------------------------------------------------------------------
# Cornice rules
# ---------------------------------------------------------------------------

class TestCorniceRules:
    def test_roofline_cornice_heavier(self):
        roof_proj = grammar.get_cornice_projection(is_roofline=True)
        floor_proj = grammar.get_cornice_projection(is_roofline=False)
        assert roof_proj > floor_proj

    def test_boulevard_has_modillions(self):
        assert grammar.has_roofline_modillions(StylePreset.BOULEVARD) is True

    def test_modest_no_modillions(self):
        assert grammar.has_roofline_modillions(StylePreset.MODEST) is False

    def test_boulevard_has_dentils(self):
        assert grammar.has_roofline_dentils(StylePreset.BOULEVARD) is True

    def test_modest_no_dentils(self):
        assert grammar.has_roofline_dentils(StylePreset.MODEST) is False


# ---------------------------------------------------------------------------
# Corner chamfer
# ---------------------------------------------------------------------------

class TestCornerChamfer:
    def test_chamfer_width(self):
        assert grammar.get_chamfer_width() == 3.0


# ---------------------------------------------------------------------------
# Edge pier validation (smart bay count)
# ---------------------------------------------------------------------------

class TestEdgePierValidation:
    def test_smart_bay_count_reduces_when_too_many(self):
        """smart_bay_count reduces count when edge piers would be < 0.5m."""
        # 8m facade with 7 bays would have tiny edge piers — should reduce
        count = grammar.smart_bay_count(8.0, 7, StylePreset.RESIDENTIAL)
        assert count < 7
        edge = grammar.compute_edge_pier(8.0, count)
        assert edge >= 0.5, f"Edge pier {edge} still < 0.5m after smart reduction"

    def test_smart_bay_count_preserves_valid(self):
        """If edge pier is already >= 0.5m, count is unchanged."""
        count = grammar.smart_bay_count(15.0, 5, StylePreset.RESIDENTIAL)
        assert count == 5

    def test_edge_piers_at_least_half_metre(self):
        """Parametric: smart_bay_count always produces edge piers >= 0.5m."""
        for width_tenths in range(60, 301):
            width = width_tenths / 10.0
            for desired in [3, 5, 7, 9]:
                count = grammar.smart_bay_count(width, desired)
                edge = grammar.compute_edge_pier(width, count)
                assert edge >= 0.5 or count <= 3, (
                    f"Width {width}m, desired {desired}: {count} bays → edge {edge:.3f}m"
                )

    def test_compute_edge_pier_non_negative(self):
        """compute_edge_pier should always return a non-negative value."""
        for width in [10.0, 13.0, 15.0, 18.0, 20.0]:
            for n in [3, 5, 7]:
                edge = grammar.compute_edge_pier(width, n)
                assert edge >= 0, (
                    f"Width {width}, {n} bays: compute_edge_pier={edge} is negative"
                )

    def test_layout_edge_pier_positive(self):
        """Layout should always have a positive edge pier (first bay offset)."""
        for width in [10.0, 13.0, 15.0, 18.0, 20.0]:
            for n in [3, 5, 7]:
                layout = grammar.get_bay_layout(width, bay_count=n)
                first_x = layout[0].x_offset
                assert first_x > 0, (
                    f"Width {width}, {n} bays: first bay offset {first_x} is non-positive"
                )


# ---------------------------------------------------------------------------
# Layout strategies
# ---------------------------------------------------------------------------

class TestLayoutStrategies:
    def test_all_bays_uniform(self):
        """All bays should be the same width."""
        specs = grammar.get_bay_layout(15.0, bay_count=7)
        widths = [s.width for s in specs]
        assert all(abs(w - widths[0]) < 0.001 for w in widths)

    def test_edge_piers_absorb_remainder(self):
        """Edge piers should absorb whatever width is left over."""
        specs = grammar.solve_bay_layout(15.0, bay_count=7)
        bp = grammar.profile.bays
        bay_w = bp.bay_width[1]  # full bay (c-to-c)
        edge_left = specs[0].x_offset - bay_w * bp.pier_ratio / 2  # back to facade edge
        last = specs[-1]
        edge_right = 15.0 - (last.x_offset + last.width + bay_w * bp.pier_ratio / 2)
        # Edges should be symmetric
        assert abs(edge_left - edge_right) < 0.01
        # Total should sum to facade width
        interior = 7 * bay_w
        total = interior + edge_left + edge_right
        assert abs(total - 15.0) < 0.01

    def test_solver_uniform_piers(self):
        """Solver produces uniform interior piers."""
        specs = grammar.solve_bay_layout(15.0, bay_count=7)
        piers = []
        for i in range(len(specs) - 1):
            gap = specs[i + 1].x_offset - (specs[i].x_offset + specs[i].width)
            piers.append(gap)
        assert all(abs(p - piers[0]) < 0.001 for p in piers), (
            f"Piers not uniform: {piers}"
        )

    def test_solver_no_overlap(self):
        """Solver: bays must not overlap for various widths."""
        for width in [5.0, 10.0, 15.0, 20.0, 25.0]:
            specs = grammar.solve_bay_layout(width)
            for i in range(len(specs) - 1):
                right_edge = specs[i].x_offset + specs[i].width
                next_left = specs[i + 1].x_offset
                assert right_edge <= next_left + 0.001, (
                    f"Width {width}: bay {i} right ({right_edge}) overlaps bay {i+1} left ({next_left})"
                )

    def test_narrow_facade_minimum_three_bays(self):
        """Very narrow facade should still produce 3 bays (minimum), narrowing as needed."""
        specs = grammar.solve_bay_layout(4.0)
        assert len(specs) == 3
        # Should still not overflow
        last = specs[-1]
        bp = grammar.profile.bays
        half_pier = specs[0].width * (bp.pier_ratio / (1 - bp.pier_ratio)) / 2
        assert last.x_offset + last.width + half_pier <= 4.0 + 0.01

    def test_strategy_ignored_backward_compat(self):
        """get_bay_layout ignores strategy param — all bays uniform."""
        from core.types import LayoutStrategy
        specs_grad = grammar.get_bay_layout(
            10.0, bay_count=3, strategy=LayoutStrategy.GRADUATED_PIERS,
        )
        specs_unif = grammar.get_bay_layout(10.0, bay_count=3)
        assert len(specs_grad) == len(specs_unif)
        for sg, su in zip(specs_grad, specs_unif):
            assert abs(sg.x_offset - su.x_offset) < 0.001
            assert abs(sg.width - su.width) < 0.001

    def test_wide_facade_has_wide_edge_piers(self):
        """Wide facade with few bays should have wide edge piers."""
        specs = grammar.solve_bay_layout(20.0, bay_count=3)
        edge_left = specs[0].x_offset
        assert edge_left > 2.0, f"Edge pier {edge_left} too narrow for 20m/3-bay"


# ---------------------------------------------------------------------------
# Modest profile — minimum 3 bays, noble height cap, edge pier widening
# ---------------------------------------------------------------------------

class TestModestProfile:
    def setup_method(self):
        from core.profile import get_profile
        self.modest_grammar = HaussmannGrammar(get_profile("modest"))

    def test_minimum_three_bays_on_narrow_lot(self):
        """Even very narrow lots must produce at least 3 bays."""
        for width in [5.0, 5.5, 6.0, 6.5, 7.0]:
            specs = self.modest_grammar.solve_bay_layout(width)
            assert len(specs) >= 3, f"Width {width}m: got {len(specs)} bays, expected ≥3"

    def test_narrow_lot_bays_dont_overflow(self):
        """Narrowed bays must fit within the facade width."""
        for width in [5.0, 5.5, 6.0, 6.5]:
            specs = self.modest_grammar.solve_bay_layout(width)
            bp = self.modest_grammar.profile.bays
            # Last bay right edge + half pier should not exceed facade
            last = specs[-1]
            bay_w_actual = last.width / (1 - bp.pier_ratio)  # full bay from window zone
            half_pier = bay_w_actual * bp.pier_ratio / 2
            assert last.x_offset + last.width + half_pier <= width + 0.01, (
                f"Width {width}m: bays overflow ({last.x_offset + last.width + half_pier:.3f}m)"
            )

    def test_noble_window_height_capped(self):
        """Noble window must not exceed noble_max_height_ratio of floor height."""
        wp = self.modest_grammar.profile.windows
        floor_h = self.modest_grammar.get_floor_height(FloorType.NOBLE)
        max_h = floor_h * wp.noble_max_height_ratio
        spec = self.modest_grammar.get_window_spec(
            FloorType.NOBLE, OrnamentLevel.RICH, 1.3, floor_h,
        )
        assert spec.height <= max_h + 0.001, (
            f"Noble window {spec.height}m exceeds cap {max_h}m "
            f"({spec.height / floor_h:.0%} of floor)"
        )

    def test_noble_cap_with_varied_profile(self):
        """Noble height cap must hold even after profile variation."""
        from core.profile import get_profile, vary_profile
        for seed in range(50):
            profile = vary_profile(get_profile("modest"), seed, amount=0.5)
            g = HaussmannGrammar(profile)
            wp = profile.windows
            floor_h = g.get_floor_height(FloorType.NOBLE)
            max_h = floor_h * wp.noble_max_height_ratio
            bay_w = profile.bays.bay_width[1] * (1 - profile.bays.pier_ratio)
            spec = g.get_window_spec(FloorType.NOBLE, OrnamentLevel.RICH, bay_w, floor_h)
            assert spec.height <= max_h + 0.001, (
                f"Seed {seed}: noble window {spec.height:.3f}m > cap {max_h:.3f}m"
            )

    def test_edge_piers_not_excessively_wide(self):
        """On moderate-width lots, bays should widen to prevent huge edge piers."""
        # 9.6m lot with 3 bays at 2.0m = 6.0m → edge was 1.8m (90% of bay)
        # After widening, edge piers should be reduced
        specs = self.modest_grammar.solve_bay_layout(9.6, bay_count=3)
        bp = self.modest_grammar.profile.bays
        bay_w_actual = specs[0].width / (1 - bp.pier_ratio)
        edge = specs[0].x_offset - bay_w_actual * bp.pier_ratio / 2
        # Edge should be at most 75% of bay width after widening
        assert edge <= bay_w_actual * 0.76, (
            f"Edge pier {edge:.3f}m is still > 75% of bay {bay_w_actual:.3f}m"
        )

    def test_modest_roof_broken_mansard(self):
        """Modest buildings should use BROKEN mansard (not STEEP)."""
        from core.types import MansardType
        spec = self.modest_grammar.get_roof_spec(3, StylePreset.MODEST)
        assert spec.mansard_type == MansardType.BROKEN
        assert spec.break_pct == 0.95


# ---------------------------------------------------------------------------
# Custom bay insertion
# ---------------------------------------------------------------------------

class TestCustomBays:
    def test_custom_bays_inserted_when_edge_wide(self):
        """Solver inserts CUSTOM bays when edge piers exceed threshold."""
        # Use a wide facade with few bays to force large edge piers
        # 20m facade / 3 bays @ 2.0m = 6.0m interior, edge = 7.0m (>> 75% of 2.0)
        specs = grammar.solve_bay_layout(20.0, bay_count=3)
        custom_bays = [s for s in specs if s.bay_type == BayType.CUSTOM]
        assert len(custom_bays) >= 1, "Should insert custom bays for wide edge piers"

    def test_no_custom_bays_when_edge_small(self):
        """No custom bays when edge piers are within threshold."""
        # 15m facade / 7 bays @ 2.0m = 14.0m, edge = 0.5m (< 75% of 2.0)
        specs = grammar.solve_bay_layout(15.0, bay_count=7)
        custom_bays = [s for s in specs if s.bay_type == BayType.CUSTOM]
        assert len(custom_bays) == 0, "No custom bays needed for narrow edge piers"

    def test_allow_custom_bays_false_suppresses(self):
        """allow_custom_bays=False suppresses custom bay insertion."""
        specs = grammar.solve_bay_layout(20.0, bay_count=3, allow_custom_bays=False)
        custom_bays = [s for s in specs if s.bay_type == BayType.CUSTOM]
        assert len(custom_bays) == 0, "Custom bays should be suppressed"

    def test_custom_bays_at_edges(self):
        """Custom bays should appear at the start and/or end of the layout."""
        specs = grammar.solve_bay_layout(20.0, bay_count=3)
        custom_bays = [s for s in specs if s.bay_type == BayType.CUSTOM]
        if len(custom_bays) >= 2:
            # First and last should be custom
            assert specs[0].bay_type == BayType.CUSTOM
            assert specs[-1].bay_type == BayType.CUSTOM
        elif len(custom_bays) == 1:
            # Should be at one edge
            assert specs[0].bay_type == BayType.CUSTOM or specs[-1].bay_type == BayType.CUSTOM

    def test_custom_bays_narrower_than_standard(self):
        """Custom bays should be narrower than standard bays."""
        specs = grammar.solve_bay_layout(20.0, bay_count=3)
        custom_bays = [s for s in specs if s.bay_type == BayType.CUSTOM]
        window_bays = [s for s in specs if s.bay_type == BayType.WINDOW]
        if custom_bays and window_bays:
            for cb in custom_bays:
                assert cb.width < window_bays[0].width, (
                    f"Custom bay width {cb.width} should be < standard {window_bays[0].width}"
                )

    def test_custom_bays_no_overlap(self):
        """Custom bays must not overlap with standard bays."""
        specs = grammar.solve_bay_layout(20.0, bay_count=3)
        for i in range(len(specs) - 1):
            right = specs[i].x_offset + specs[i].width
            next_left = specs[i + 1].x_offset
            assert right <= next_left + 0.001, (
                f"Bay {i} right ({right}) overlaps bay {i+1} left ({next_left})"
            )

    def test_custom_bays_within_facade(self):
        """All bays (including custom) must stay within facade width."""
        for width in [15.0, 18.0, 20.0, 25.0]:
            specs = grammar.solve_bay_layout(width, bay_count=3)
            assert specs[0].x_offset >= 0, f"First bay starts before facade"
            last = specs[-1]
            assert last.x_offset + last.width <= width + 0.01, (
                f"Last bay exceeds facade width ({last.x_offset + last.width:.3f} > {width})"
            )
