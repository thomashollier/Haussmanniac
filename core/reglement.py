"""The Paris building regulations, as code.

The Haussmann apartment building is not a style that was chosen — it is the
residue of a legal envelope.  Street width fixed the facade height, an
ordinance fixed where balconies could start and how far they could project,
and a separate rule fixed the shape of the roof above the cornice.  Change
the decree and the building changes shape.  This module encodes those rules
so the rest of the generator can derive form from them instead of guessing.

Sources
-------
- Déclaration royale du 10 avril 1783 / lettres patentes du 28 août 1784 —
  first tie facade height to street width; combles must be inscribed below
  a 45° diagonal springing from the eaves (égout du toit).
- Ordonnance de 1823 — balconies may project at most 0.80 m and only at
  6 m or more above the pavement.  Unchanged under Haussmann, which is why
  haussmannian facades have so little relief and run to *balcons filants*.
- Circulaire du 21 septembre 1855 — within a block, balcony, cornice and
  entablature lines must align from building to building.
- Règlement du 27 juillet 1859 — streets wider than 20 m may build 20 m of
  facade; combles remain bounded by the 45° diagonal.  Minimum storey
  height 2.60 m, plus courtyard rules, on hygiene grounds.
- Décret du 22 juillet 1882 — oriels (bow windows) permitted: they must
  start at the étage noble, may not pass above the cornice, project at
  most 0.40 m, and must be demountable.  Masonry oriels allowed from 1893.
- Décret du 23 juillet 1884 (Alphand) — raises the height table, and
  replaces the 45° diagonal with an arc of a circle whose radius depends
  on street width, which is what lets a further storey be built set back
  from the facade.  20 m facade + 8.50 m comble = the 28.50 m ceiling.
- Décret du 13 août 1902 (Louis Bonnier) — combles are inscribed in an
  eighth-of-a-circle arc continued by a 45° oblique, and projections may
  now carry above the cornice.  On a deep parcel the ridge can go very
  high, which is the opening Henri Sauvage exploits at rue Vavin.

Documented vs. modelled
-----------------------
Height tables, the 0.80 m / 6 m balcony rule, the 2.60 m storey minimum,
the three envelope geometries and the 8.50 m arc radius for streets over
20 m are all documented.  Two quantities are *modelled* because the texts
do not give them, and both are marked ``MODELLED`` where they appear:
the arc radius for narrower streets (scaled from the 8.50 m anchor) and
the "hauteur maximale" that caps the pre-1884 45° comble.

All dimensions in metres.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Eras
# ---------------------------------------------------------------------------

class Era(Enum):
    """Regulatory period.  Each maps to one ``Reglement``.

    The era is the *date of construction*, and is independent of how grand
    the building is: a modest building on a back street and a boulevard
    building put up the same year obey the same envelope.
    """
    ROYAL = "royal"                  # 1784–1859
    SECOND_EMPIRE = "second_empire"  # 1859–1884  — Haussmann's own period
    ALPHAND = "alphand"              # 1884–1902
    BONNIER = "bonnier"              # 1902–1914


class RoofEnvelope(Enum):
    """Geometry bounding the comble above the cornice line."""
    DIAGONAL_45 = "diagonal_45"          # 1783/84, 1859 — straight 45° from the eaves
    CIRCULAR_ARC = "circular_arc"        # 1884 — quarter arc, near-vertical at the eaves
    EIGHTH_ARC_OBLIQUE = "eighth_arc"    # 1902 — 45° of arc, then a 45° oblique


# ---------------------------------------------------------------------------
# Reglement
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Reglement:
    """One regulatory regime.

    ``height_steps`` is read as: the first step whose ``max_street_width``
    is not exceeded by the street gives the facade height.  ``math.inf``
    terminates the table.
    """
    era: Era
    label: str
    decree: str

    # (max_street_width, max_facade_height)
    height_steps: tuple[tuple[float, float], ...]

    roof_envelope: RoofEnvelope
    # MODELLED: cap on the comble where the decree says only "hauteur
    # maximale".  Calibrated so a Second Empire roof holds exactly the one
    # storey of chambres de bonne it was built for.
    max_roof_height: float = 3.20
    # Documented anchor: 8.50 m arc for streets over 20 m (1884).
    arc_radius_at_20m: float = 8.50

    # Ordonnance de 1823, never relaxed under Haussmann
    max_balcony_projection: float = 0.80
    min_balcony_height: float = 6.00

    # Règlement de 1859, hygiene provisions
    min_floor_height: float = 2.60
    min_courtyard_area: float = 0.0

    # Oriels / bow windows.  Projections over the street had been banned
    # since the edicts of 1607 and 1667; 1882 lifts that for the first time.
    oriels_allowed: bool = False
    oriels_above_cornice: bool = False
    max_oriel_projection: float = 0.40
    oriel_start_floor: str = "NOBLE"   # "il ne doit commencer qu'à l'étage noble"
    # 1882 required oriels to be demountable, so metal and wood only.  Paris
    # allowed brick and cut stone from 1893 — mid-way through the Alphand
    # era, which our four-way split cannot express, so masonry is modelled
    # as arriving with the 1902 règlement.
    oriel_materials: tuple[str, ...] = ("metal", "wood")
    # Individual balconettes on the middle floors appear late in the period
    individual_balconies: bool = False

    def facade_height_limit(self, street_width: float) -> float:
        """Maximum height of the stone facade for a street of *street_width*."""
        for max_width, height in self.height_steps:
            if street_width <= max_width:
                return height
        return self.height_steps[-1][1]

    def arc_radius(self, street_width: float) -> float:
        """Radius of the comble arc.

        MODELLED below 20 m: the 1884 decree says the radius depends on
        street width but the table is not in our sources, so it is scaled
        from the documented 8.50 m anchor in proportion to the facade
        height the same street earns.
        """
        h = self.facade_height_limit(street_width)
        h_max = self.height_steps[-1][1]
        return self.arc_radius_at_20m * (h / h_max)


REGLEMENTS: dict[Era, Reglement] = {
    # Déclaration royale de 1783 / lettres patentes de 1784.
    Era.ROYAL: Reglement(
        era=Era.ROYAL,
        label="Ancien Régime tables",
        decree="Déclaration royale du 10 avril 1783, lettres patentes du 28 août 1784",
        height_steps=(
            (7.80, 11.70),    # six toises
            (9.75, 14.62),    # sept toises trois pieds
            (math.inf, 17.55),  # neuf toises
        ),
        roof_envelope=RoofEnvelope.DIAGONAL_45,
        max_roof_height=3.00,
        min_floor_height=0.0,      # no hygiene minimum before 1859
    ),

    # Règlement du 27 juillet 1859 — adds the 20 m step for the percées.
    Era.SECOND_EMPIRE: Reglement(
        era=Era.SECOND_EMPIRE,
        label="Second Empire",
        decree="Règlement du 27 juillet 1859",
        height_steps=(
            (7.80, 11.70),
            (9.75, 14.62),
            (20.00, 17.55),
            (math.inf, 20.00),
        ),
        roof_envelope=RoofEnvelope.DIAGONAL_45,
        max_roof_height=3.20,
        min_floor_height=2.60,
        min_courtyard_area=0.0,
    ),

    # Décret du 23 juillet 1884 (Alphand), following that of 22 juillet 1882.
    Era.ALPHAND: Reglement(
        era=Era.ALPHAND,
        label="Alphand",
        decree="Décret du 23 juillet 1884",
        height_steps=(
            (7.80, 12.00),
            (9.75, 15.00),
            (20.00, 18.00),
            (math.inf, 20.00),
        ),
        roof_envelope=RoofEnvelope.CIRCULAR_ARC,
        arc_radius_at_20m=8.50,     # 20 + 8.50 = the 28.50 m ceiling
        min_floor_height=2.60,
        min_courtyard_area=30.0,    # habitable rooms on a court: ≥ 30 m²
        oriels_allowed=True,        # 1882, metal or wood; masonry from 1893
        oriels_above_cornice=False,
        individual_balconies=True,
    ),

    # Décret du 13 août 1902 (Louis Bonnier).
    Era.BONNIER: Reglement(
        era=Era.BONNIER,
        label="Bonnier",
        decree="Décret du 13 août 1902",
        height_steps=(
            (7.80, 12.00),
            (9.75, 15.00),
            (20.00, 18.00),
            (math.inf, 20.00),
        ),
        roof_envelope=RoofEnvelope.EIGHTH_ARC_OBLIQUE,
        arc_radius_at_20m=8.50,
        min_floor_height=2.60,
        min_courtyard_area=30.0,
        oriels_allowed=True,
        oriels_above_cornice=True,   # saillies may carry above the cornice
        oriel_materials=("stone", "metal", "wood"),
        individual_balconies=True,
    ),
}


_ERA_START_YEAR: tuple[tuple[int, Era], ...] = (
    (1902, Era.BONNIER),
    (1884, Era.ALPHAND),
    (1859, Era.SECOND_EMPIRE),
    (0, Era.ROYAL),
)


def era_for_year(year: int) -> Era:
    """Return the regulatory era in force in *year*."""
    for start, era in _ERA_START_YEAR:
        if year >= start:
            return era
    return Era.ROYAL


def get_reglement(era: Era | str) -> Reglement:
    """Look up a ``Reglement`` by era (enum or case-insensitive name)."""
    if isinstance(era, Era):
        return REGLEMENTS[era]
    key = str(era).strip().upper()
    for candidate in Era:
        if candidate.name == key or candidate.value.upper() == key:
            return REGLEMENTS[candidate]
    raise KeyError(
        f"Unknown era: {era!r}. Available: {', '.join(e.name for e in Era)}"
    )


# ---------------------------------------------------------------------------
# Gabarit envelope
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GabaritEnvelope:
    """The legal solid a building may occupy on its street frontage.

    ``facade_height`` is the cornice line — the top of the vertical stone
    face.  Above it the comble must stay inside a curve that depends on
    the era.  ``setback_at(h)`` gives the minimum horizontal distance from
    the facade plane at height *h* above the cornice; ``slope_profile()``
    traces that curve as a polyline a backend can draw directly.
    """
    era: Era
    street_width: float
    facade_height: float
    roof_envelope: RoofEnvelope
    arc_radius: float
    ridge_height: float          # apex of the comble as built, above the cornice
    parcel_depth: float
    legal_ridge_height: float = 0.0   # apex the decree would have allowed

    @property
    def total_height(self) -> float:
        """Cornice height plus comble — the full silhouette."""
        return self.facade_height + self.ridge_height

    def setback_at(self, h: float) -> float:
        """Minimum inset from the facade plane at height *h* above the cornice."""
        if h <= 0.0:
            return 0.0
        if self.roof_envelope == RoofEnvelope.DIAGONAL_45:
            # Inscribed below a 45° diagonal from the eaves: inset >= h.
            return h
        r = self.arc_radius
        if self.roof_envelope == RoofEnvelope.CIRCULAR_ARC:
            # Quarter arc centred at (r, 0): vertical at the eaves,
            # horizontal at the apex h = r.
            if h >= r:
                return r
            return r - math.sqrt(max(0.0, r * r - h * h))
        # EIGHTH_ARC_OBLIQUE: 45° of arc, then a 45° oblique.
        h_break = r * math.sin(math.pi / 4)
        if h <= h_break:
            return r - math.sqrt(max(0.0, r * r - h * h))
        inset_break = r - r * math.cos(math.pi / 4)
        return inset_break + (h - h_break)

    def max_height_for_setback(self, inset: float) -> float:
        """Tallest legal point at horizontal distance *inset* from the facade."""
        if inset <= 0.0:
            return 0.0
        r = self.arc_radius
        if self.roof_envelope == RoofEnvelope.DIAGONAL_45:
            return inset
        if self.roof_envelope == RoofEnvelope.CIRCULAR_ARC:
            if inset >= r:
                return r
            return math.sqrt(max(0.0, r * r - (r - inset) ** 2))
        inset_break = r - r * math.cos(math.pi / 4)
        if inset <= inset_break:
            return math.sqrt(max(0.0, r * r - (r - inset) ** 2))
        return r * math.sin(math.pi / 4) + (inset - inset_break)

    def slope_profile(self, samples: int = 16) -> list[tuple[float, float]]:
        """Trace the comble envelope as ``(inset, height)`` points.

        Starts at the eaves ``(0.0, 0.0)`` and ends at the ridge.  Straight
        segments emit two points; curved ones are sampled.  Heights are
        relative to the cornice, insets relative to the facade plane.
        """
        top = self.ridge_height
        if top <= 0.0:
            return [(0.0, 0.0)]

        if self.roof_envelope == RoofEnvelope.DIAGONAL_45:
            return [(0.0, 0.0), (self.setback_at(top), top)]

        pts: list[tuple[float, float]] = []
        r = self.arc_radius
        curve_top = top
        if self.roof_envelope == RoofEnvelope.EIGHTH_ARC_OBLIQUE:
            curve_top = min(top, r * math.sin(math.pi / 4))
        else:
            curve_top = min(top, r)

        n = max(2, samples)
        for i in range(n + 1):
            h = curve_top * i / n
            pts.append((round(self.setback_at(h), 4), round(h, 4)))
        if top > curve_top + 1e-9:
            pts.append((round(self.setback_at(top), 4), round(top, 4)))
        return pts

    def mansard_angles(self) -> tuple[float, float, float]:
        """Approximate the envelope as a broken mansard.

        Returns ``(lower_angle_deg, upper_angle_deg, break_pct)`` — the two
        slope angles and the height fraction at which they meet — for
        backends and consumers that want the classic two-segment
        description rather than the sampled polyline.  Angles are measured
        from horizontal, so 45° is the Second Empire comble and values
        near 80° are the near-vertical start of a post-1884 arc.
        """
        top = self.ridge_height
        if top <= 0.0:
            return (45.0, 45.0, 1.0)

        if self.roof_envelope == RoofEnvelope.DIAGONAL_45:
            return (45.0, 45.0, 1.0)

        if self.roof_envelope == RoofEnvelope.CIRCULAR_ARC:
            break_pct = 0.72
        else:
            r = self.arc_radius
            break_pct = min(0.95, (r * math.sin(math.pi / 4)) / top) if top else 0.72

        h_break = top * break_pct
        inset_break = self.setback_at(h_break)
        inset_top = self.setback_at(top)

        lower = math.degrees(math.atan2(h_break, max(inset_break, 1e-6)))
        d_h = top - h_break
        d_i = max(inset_top - inset_break, 1e-6)
        upper = math.degrees(math.atan2(d_h, d_i))
        return (round(min(lower, 89.0), 2), round(upper, 2), round(break_pct, 3))


def compute_envelope(
    street_width: float,
    era: Era | str = Era.SECOND_EMPIRE,
    parcel_depth: float = 12.0,
    roof_fill: float = 1.0,
    max_ridge: float | None = None,
) -> GabaritEnvelope:
    """Derive the legal envelope for a frontage on a street of *street_width*.

    *parcel_depth* limits the ridge: a comble cannot rise past the point
    where its two opposing slopes meet, so a shallow parcel gets a lower
    roof than the decree alone would allow.

    The decree sets a ceiling, not a target.  Two builder-side constraints
    bring the comble back down to what was actually put up: *roof_fill*
    (0–1) scales it, and *max_ridge* caps it at the height the programme
    needs — usually one or two storeys of chambres de bonne.  The height
    the decree would have permitted is kept as ``legal_ridge_height``.
    """
    reg = get_reglement(era)
    street_width = max(0.0, float(street_width))
    facade_h = reg.facade_height_limit(street_width)
    radius = reg.arc_radius(street_width)

    if reg.roof_envelope == RoofEnvelope.DIAGONAL_45:
        legal_top = reg.max_roof_height
    elif reg.roof_envelope == RoofEnvelope.CIRCULAR_ARC:
        legal_top = radius
    else:
        # Eighth arc then 45°: unbounded by the curve, so the parcel decides.
        legal_top = radius * 2.0

    # Two opposing slopes meet at mid-depth.
    depth_limited = _ridge_for_depth(reg.roof_envelope, radius, parcel_depth / 2.0)
    legal_ridge = max(0.0, min(legal_top, depth_limited))

    ridge = legal_ridge * max(0.0, min(1.0, roof_fill))
    if max_ridge is not None:
        ridge = min(ridge, max(0.0, max_ridge))

    return GabaritEnvelope(
        era=reg.era,
        street_width=street_width,
        facade_height=facade_h,
        roof_envelope=reg.roof_envelope,
        arc_radius=radius,
        ridge_height=round(ridge, 3),
        parcel_depth=parcel_depth,
        legal_ridge_height=round(legal_ridge, 3),
    )


def _ridge_for_depth(envelope: RoofEnvelope, radius: float, half_depth: float) -> float:
    """Height the envelope reaches once *half_depth* of inset is available."""
    if half_depth <= 0.0:
        return 0.0
    if envelope == RoofEnvelope.DIAGONAL_45:
        return half_depth
    if envelope == RoofEnvelope.CIRCULAR_ARC:
        if half_depth >= radius:
            return radius
        return math.sqrt(max(0.0, radius * radius - (radius - half_depth) ** 2))
    inset_break = radius - radius * math.cos(math.pi / 4)
    if half_depth <= inset_break:
        return math.sqrt(max(0.0, radius * radius - (radius - half_depth) ** 2))
    return radius * math.sin(math.pi / 4) + (half_depth - inset_break)


# ---------------------------------------------------------------------------
# The 1823 balcony rule
# ---------------------------------------------------------------------------

@dataclass
class BalconyRule:
    """Where balconies may go, per the ordinance of 1823.

    ``continuous`` holds the indices of floors carrying a *balcon filant*;
    ``individual`` holds floors carrying separate balconettes (permitted in
    practice only late in the period).  ``max_projection`` is the legal
    0.80 m cap that any depth must be clamped to.
    """
    continuous: list[int] = field(default_factory=list)
    individual: list[int] = field(default_factory=list)
    max_projection: float = 0.80
    min_height: float = 6.00


def balcony_rule(
    floor_levels: list[float],
    era: Era | str = Era.SECOND_EMPIRE,
    second_line: bool = True,
) -> BalconyRule:
    """Decide which floors carry balconies from their heights above the pavement.

    *floor_levels* is the height of each floor's own level, bottom-up, in
    metres — the ground floor is 0.0.  The 1823 ordinance permits a balcony
    only at 6 m or more, which is what puts the first *balcon filant* on
    the étage noble of a building with an entresol and pushes it a storey
    higher on one without.  When *second_line* is set the topmost
    residential floor takes the second continuous balcony, the line that
    lets middle-class tenants above the noble floor share the view.

    Middle floors between the two lines take individual balconettes only
    under the later regulations, matching the balcons individuels that
    appear at the end of the haussmannian period.
    """
    reg = get_reglement(era)
    eligible = [i for i, y in enumerate(floor_levels) if y >= reg.min_balcony_height - 1e-9]
    if not eligible:
        return BalconyRule(
            max_projection=reg.max_balcony_projection,
            min_height=reg.min_balcony_height,
        )

    continuous = [eligible[0]]
    if second_line and len(eligible) > 1 and eligible[-1] != eligible[0]:
        continuous.append(eligible[-1])

    individual: list[int] = []
    if reg.individual_balconies:
        individual = [i for i in eligible if i not in continuous]

    return BalconyRule(
        continuous=continuous,
        individual=individual,
        max_projection=reg.max_balcony_projection,
        min_height=reg.min_balcony_height,
    )


# ---------------------------------------------------------------------------
# Oriels — the 1882 relaxation
# ---------------------------------------------------------------------------

@dataclass
class OrielRule:
    """Whether a facade may carry an oriel, and within what limits.

    Paris had forbidden projections over the street since the edicts of
    1607 and 1667.  The decree of 22 July 1882 lifted that for the first
    time in over two centuries, hedged about with conditions: the oriel
    had to begin at the étage noble, could not carry above the cornice,
    could project no more than 0.40 m, and had to be demountable — hence
    metal and wood.  Masonry followed in 1893, and in 1902 the projection
    was finally allowed past the cornice.
    """
    allowed: bool = False
    start_index: int = -1          # floor it must begin on
    start_height: float = 0.0      # that floor's level above the pavement
    max_top: float = 0.0           # highest the oriel may reach
    max_projection: float = 0.40
    may_pass_cornice: bool = False
    materials: tuple[str, ...] = ()


def oriel_rule(
    floor_levels: list[float],
    floor_names: list[str],
    cornice_height: float,
    era: Era | str = Era.SECOND_EMPIRE,
    above_cornice_extra: float = 1.6,
) -> OrielRule:
    """Decide whether and where an oriel may be built.

    *floor_levels* and *floor_names* describe the stack bottom-up, the
    names being ``FloorType`` names.  *cornice_height* is the top of the
    stone facade.  Under the 1902 règlement the oriel may carry above the
    cornice, by up to *above_cornice_extra* metres.
    """
    reg = get_reglement(era)
    if not reg.oriels_allowed:
        return OrielRule(max_projection=reg.max_oriel_projection)

    try:
        start = floor_names.index(reg.oriel_start_floor)
    except ValueError:
        return OrielRule(max_projection=reg.max_oriel_projection)

    max_top = cornice_height
    if reg.oriels_above_cornice:
        max_top += above_cornice_extra

    return OrielRule(
        allowed=True,
        start_index=start,
        start_height=floor_levels[start],
        max_top=max_top,
        max_projection=reg.max_oriel_projection,
        may_pass_cornice=reg.oriels_above_cornice,
        materials=reg.oriel_materials,
    )
