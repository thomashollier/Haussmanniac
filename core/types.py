"""Intermediate representation (IR) dataclasses for Haussmann building generation.

Every node carries a local Transform (position/rotation/scale relative to its
parent) and a node_type string.  The full IR tree is pure Python — no geometry,
no external dependencies.

Units: metres.  Origin: front-left-ground corner of the building.  Y is up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from .reglement import Era, RoofEnvelope


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FloorType(Enum):
    """Vertical zoning — each storey has an architectural role."""
    GROUND = auto()       # RDC — commercial, rusticated
    ENTRESOL = auto()     # Low intermediate level (sometimes omitted)
    NOBLE = auto()        # Étage noble — tallest windows, richest ornament
    THIRD = auto()        # Slightly less ornate than noble
    FOURTH = auto()       # Simpler window surrounds
    FIFTH = auto()        # Second continuous balcony line
    MANSARD = auto()      # Zinc-clad 45° roof slope with dormers


class OrnamentLevel(Enum):
    """Decreasing richness from ground to top."""
    RICH = 3       # Ground floor, noble floor
    MODERATE = 2   # Middle floors
    SIMPLE = 1     # Upper floors
    NONE = 0       # Plain / structural only


class PedimentStyle(Enum):
    """Window pediment shapes."""
    NONE = auto()
    TRIANGULAR = auto()
    SEGMENTAL = auto()     # Curved / arc segment
    ARCHED = auto()        # Full semicircular arch


class BayType(Enum):
    """What occupies a vertical bay on a given floor."""
    WINDOW = auto()
    DOOR = auto()          # Ground-floor entrance / porte-cochère
    SHOPFRONT = auto()     # Ground-floor commercial opening
    BLANK = auto()         # Solid wall (pier, party wall edge)
    EDGE = auto()          # Extended pier padding bay at facade edges
    CUSTOM = auto()        # User-specified one-off width


class PorteStyle(Enum):
    """Style of the porte-cochère opening."""
    ARCHED = auto()        # Rounded top (semicircular arch)
    FLAT = auto()          # Flat lintel (same height, rectangular)


class Orientation(Enum):
    """Cardinal direction a facade faces."""
    NORTH = auto()
    SOUTH = auto()
    EAST = auto()
    WEST = auto()


class RailingPattern(Enum):
    """Wrought-iron balcony railing motifs."""
    CLASSIC = auto()       # Symmetrical scrollwork
    GEOMETRIC = auto()     # Rectilinear Art-Nouveau-influenced
    SIMPLE = auto()        # Plain vertical bars with top rail


class SurroundStyle(Enum):
    """Window surround treatment."""
    NONE = auto()
    MOLDED = auto()        # Simple molding frame
    PILASTERED = auto()    # Flanking pilasters / engaged columns
    EARED = auto()         # Crossette / eared architrave


class MansardType(Enum):
    """Mansard roof profile shapes.

    DIAGONAL: A single unbroken 45° face — the comble of the 1783/84 and
              1859 règlements, which required the roof to be inscribed
              below a 45° diagonal springing from the eaves.  This is the
              true Second Empire roof; dormers are cut into the face.
    STEEP:  Near-vertical lower slope (~75-80°), plenty of room for dormers.
            Only legal once the 1884 decree replaced the diagonal with an arc.
    BROKEN: Very steep lower section that breaks to a much flatter upper
            section above the dormer heads — the profile a post-1884
            circular-arc envelope produces.
    SHALLOW: Gentle continuous slope (~35-45°) with no dormer zone.
             Used on rear facades or modest buildings.
    """
    STEEP = auto()
    BROKEN = auto()
    SHALLOW = auto()
    DIAGONAL = auto()


class DormerStyle(Enum):
    """Mansard dormer window shapes."""
    PEDIMENT_TRIANGLE = auto()  # Triangular pediment cap
    PEDIMENT_CURVED = auto()    # Curved (segmental) pediment cap
    POINTY_ROOF = auto()        # Steep pointed zinc roof
    OVAL = auto()               # Oeil-de-boeuf / oval top
    FLAT_SLOPE = auto()         # Low-slope flat zinc cap, rectangular window
    ROUND_SLOPE = auto()        # Short square dormer, circular window, zinc cap


class CustomBayStyle(Enum):
    """Window treatment for narrow custom bays at facade edges."""
    PORTHOLE = auto()       # Circular window (oeil-de-boeuf)
    NARROW_WINDOW = auto()  # Tall narrow rectangular window
    STONEWORK = auto()      # Rusticated stone panel with coursing
    GEOMETRIC = auto()      # Geometric diamond relief pattern


class OrielStyle(Enum):
    """Shape of an oriel (projecting bay window) in plan."""
    SQUARE = auto()    # Flat front, square returns — the plainest
    CANTED = auto()    # Splayed sides, flat front — the commonest
    BOWED = auto()     # Curved front (a bow window proper)


class BalconyType(Enum):
    """Per-floor balcony treatment, ordered by prominence."""
    NONE = "none"
    BALCONETTE = "balconette"
    CONTINUOUS = "continuous"


class StylePreset(Enum):
    """Quick presets controlling ornament density and proportions."""
    BOULEVARD = auto()     # Rich — Bd Haussmann, Av de l'Opéra
    RESIDENTIAL = auto()   # Moderate — typical side street
    MODEST = auto()        # Minimal — back streets, upper arrondissements


class LayoutStrategy(Enum):
    """Bay layout distribution strategies."""
    UNIFORM = "uniform"              # All bays and piers equal width
    WIDE_DOOR = "wide_door"          # Porte-cochère bay is ~1.5× wider
    GRADUATED_PIERS = "graduated"    # Outer piers match edge width, inner piers narrower


class GroundFloorType(Enum):
    """Ground floor usage type."""
    AUTO = "auto"                # Derived from style preset + RNG
    COMMERCIAL = "commercial"    # All shopfronts (low sill ~0.15m, wide openings)
    RESIDENTIAL = "residential"  # All standard windows (~1.2m sill)
    MIXED = "mixed"              # Shop on one side of porte-cochère, windows on other


class StoreType(Enum):
    """Ground-floor commercial unit type, determined by bay span."""
    BOUTIQUE = auto()      # 1–2 bays: small shop, door + display window
    CAFE = auto()          # 3+ bays: open terrace, folding doors, awning


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

@dataclass
class Transform:
    """Local transform relative to parent node.

    Rotation is Euler angles in radians (Y-up, right-hand rule).
    """
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# IR Node base
# ---------------------------------------------------------------------------

@dataclass
class IRNode:
    """Base for every intermediate-representation node."""
    node_type: str = ""
    transform: Transform = field(default_factory=Transform)


# ---------------------------------------------------------------------------
# Leaf / detail nodes
# ---------------------------------------------------------------------------

@dataclass
class WindowNode(IRNode):
    """A single window opening."""
    node_type: str = field(default="window", init=False)
    width: float = 1.2
    height: float = 1.8
    surround_style: SurroundStyle = SurroundStyle.MOLDED
    pediment: PedimentStyle = PedimentStyle.NONE
    has_keystone: bool = False


@dataclass
class BalconyNode(IRNode):
    """A balcony or balconette attached to a window bay or spanning a floor."""
    node_type: str = field(default="balcony", init=False)
    width: float = 1.2
    depth: float = 0.4
    is_continuous: bool = False
    railing_pattern: RailingPattern = RailingPattern.CLASSIC
    railing_height: float = 1.0


@dataclass
class PilasterNode(IRNode):
    """Engaged column / pilaster flanking a window."""
    node_type: str = field(default="pilaster", init=False)
    width: float = 0.15
    depth: float = 0.08
    height: float = 3.0
    has_capital: bool = True


@dataclass
class OrnamentNode(IRNode):
    """Generic ornamental element (keystone, pediment piece, cornice segment)."""
    node_type: str = field(default="ornament", init=False)
    ornament_id: str = ""          # References an asset in the asset library
    ornament_level: OrnamentLevel = OrnamentLevel.MODERATE


@dataclass
class OrielNode(IRNode):
    """A bay window projecting from the facade, carried on corbels.

    Legal in Paris only from the decree of 22 July 1882, and then only
    starting at the étage noble, projecting no more than 0.40 m, and not
    carrying above the cornice until 1902.  Spans several floors, so it
    hangs off the FacadeNode rather than off any one FloorNode; its
    transform position is its bottom-left corner on the facade plane.
    """
    node_type: str = field(default="oriel", init=False)
    width: float = 1.5
    height: float = 3.0              # total vertical extent
    projection: float = 0.40         # how far it stands off the wall
    style: OrielStyle = OrielStyle.CANTED
    material: str = "metal"          # metal / wood / stone
    bay_index: int = 0               # bay it sits over
    floor_span: int = 1              # how many storeys it runs through
    passes_cornice: bool = False     # 1902 onward only
    children: list[IRNode] = field(default_factory=list)


@dataclass
class CorniceNode(IRNode):
    """Horizontal cornice band between floors or at roofline."""
    node_type: str = field(default="cornice", init=False)
    width: float = 0.0            # Span (set to facade width)
    profile_id: str = "default"   # References a 2-D profile curve
    projection: float = 0.15      # How far it projects from wall face
    has_modillions: bool = False
    has_dentils: bool = False


@dataclass
class StringCourseNode(IRNode):
    """Thin horizontal band / string course."""
    node_type: str = field(default="string_course", init=False)
    width: float = 0.0
    height: float = 0.06
    projection: float = 0.04


# ---------------------------------------------------------------------------
# Aggregation nodes
# ---------------------------------------------------------------------------

@dataclass
class BayNode(IRNode):
    """One vertical bay on a single floor (contains window + ornament)."""
    node_type: str = field(default="bay", init=False)
    width: float = 1.2
    x_offset: float = 0.0
    bay_type: BayType = BayType.WINDOW
    porte_style: PorteStyle = PorteStyle.ARCHED  # Only relevant for DOOR bays
    custom_bay_style: CustomBayStyle | None = None  # Set on CUSTOM-type bays
    store_type: StoreType | None = None      # Only set on commercial ground-floor bays
    is_store_entry: bool = False              # True for the bay that has the shop door
    group: int = 0                           # Symmetry group index
    children: list[IRNode] = field(default_factory=list)


@dataclass
class FloorNode(IRNode):
    """One storey of a facade."""
    node_type: str = field(default="floor", init=False)
    floor_type: FloorType = FloorType.THIRD
    height: float = 3.0
    y_offset: float = 0.0
    ornament_level: OrnamentLevel = OrnamentLevel.MODERATE
    children: list[IRNode] = field(default_factory=list)  # BayNodes, CorniceNodes, etc.


@dataclass
class GroundFloorNode(IRNode):
    """Special ground-floor node (shopfronts, porte-cochère, rustication)."""
    node_type: str = field(default="ground_floor", init=False)
    height: float = 4.5
    has_rustication: bool = True
    has_porte_cochere: bool = False
    porte_cochere_bay_index: Optional[int] = None  # Which bay is the carriage entrance
    children: list[IRNode] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Roof nodes
# ---------------------------------------------------------------------------

@dataclass
class MansardSlopeNode(IRNode):
    """One face of the mansard slope.

    ``envelope_profile`` is the authoritative silhouette: ``(inset, height)``
    points in metres tracing the legal gabarit from the eaves to the ridge
    (see ``core.reglement.GabaritEnvelope.slope_profile``).  Backends should
    draw that polyline directly.  ``lower_angle`` / ``upper_angle`` /
    ``break_pct`` are the two-segment approximation of the same curve, kept
    for consumers that want the classic broken-mansard description.
    """
    node_type: str = field(default="mansard_slope", init=False)
    mansard_type: MansardType = MansardType.BROKEN
    lower_angle: float = math.radians(75)   # Steep lower slope (near-vertical)
    upper_angle: float = math.radians(20)   # Near-flat upper slope
    break_pct: float = 0.95                 # Break as fraction of total height (1.0 = no upper segment)
    height: float = 2.8                     # Total mansard height
    material: str = "zinc"
    roof_envelope: RoofEnvelope | None = None          # Which decree shaped it
    envelope_profile: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class DormerNode(IRNode):
    """A dormer window in the mansard roof."""
    node_type: str = field(default="dormer", init=False)
    width: float = 1.0
    height: float = 1.6
    style: DormerStyle = DormerStyle.PEDIMENT_CURVED


@dataclass
class ChimneyNode(IRNode):
    """A chimney stack on the roof."""
    node_type: str = field(default="chimney", init=False)
    width: float = 0.8
    depth: float = 0.5
    height: float = 2.0
    material: str = "stone"
    is_ridge: bool = False       # Sits on mansard ridge between bays
    has_pipe: bool = False       # Thin flue pipe on top


@dataclass
class RoofNode(IRNode):
    """The complete roof assembly."""
    node_type: str = field(default="roof", init=False)
    mansard_type: MansardType = MansardType.BROKEN
    mansard_lower_angle: float = math.radians(75)
    mansard_upper_angle: float = math.radians(20)
    roof_envelope: RoofEnvelope | None = None   # Envelope the decree imposed
    children: list[IRNode] = field(default_factory=list)  # Slopes, dormers, chimneys


# ---------------------------------------------------------------------------
# Facade & building nodes
# ---------------------------------------------------------------------------

@dataclass
class CornerNode(IRNode):
    """Pan coupé — 45° chamfer at street intersection."""
    node_type: str = field(default="corner", init=False)
    chamfer_width: float = 3.0
    angle: float = math.radians(45)
    children: list[IRNode] = field(default_factory=list)


@dataclass
class FacadeNode(IRNode):
    """One face of the building (front, side, rear)."""
    node_type: str = field(default="facade", init=False)
    orientation: Orientation = Orientation.SOUTH
    width: float = 15.0
    depth_offset: float = 0.0
    children: list[IRNode] = field(default_factory=list)  # FloorNodes, GroundFloorNode


@dataclass
class BuildingNode(IRNode):
    """Root node of the IR tree — one complete building."""
    node_type: str = field(default="building", init=False)
    lot_width: float = 15.0
    lot_depth: float = 12.0
    num_floors: int = 6
    style_preset: StylePreset = StylePreset.RESIDENTIAL
    seed: int = 0
    era: Era = Era.SECOND_EMPIRE          # Regulatory period that shaped it
    street_width: float = 0.0             # Street it fronts (drives the gabarit)
    cornice_height: float = 0.0           # Height of the stone facade (gabarit limit)
    element_palette: object | None = None  # core.elements.ElementPalette (avoids circular import)
    children: list[IRNode] = field(default_factory=list)  # Facades, RoofNode, CornerNodes


# ---------------------------------------------------------------------------
# Building decisions (accumulated per-building choices)
# ---------------------------------------------------------------------------

@dataclass
class BuildingDecisions:
    """Accumulated per-building choices from the generation pipeline.

    Each generation step reads prior decisions and writes its own.
    Passed through the entire pipeline so downstream steps can
    reference any earlier choice.
    """
    balcony_types: dict[FloorType, BalconyType] = field(default_factory=dict)
    element_palette: object | None = None   # core.elements.ElementPalette (avoids circular import)


# ---------------------------------------------------------------------------
# Building overrides (optional per-field overrides for seeded output)
# ---------------------------------------------------------------------------

@dataclass
class BuildingOverrides:
    """Optional overrides that replace individual RNG-driven decisions.

    ``None`` means "use the random value."  The override is applied
    immediately after the corresponding RNG call so the rest of the
    building stays internally consistent.
    """
    bay_count: int | None = None
    porte_cochere_bay: int | None = None
    porte_style: PorteStyle | None = None
    ground_floor_type: GroundFloorType | None = None
    mansard_height: float | None = None
    has_dormers: bool | None = None
    break_ratio: float | None = None
    lower_angle: float | None = None
    upper_angle: float | None = None
    dormer_placement: str | None = None
    dormer_style: DormerStyle | None = None
    has_custom_bays: bool | None = None              # Force custom bays on/off (None = auto)
    custom_bay_style: CustomBayStyle | None = None    # Override the custom bay window style


# ---------------------------------------------------------------------------
# Building configuration (input to the generator)
# ---------------------------------------------------------------------------

@dataclass
class BuildingConfig:
    """User-facing configuration for building generation."""
    lot_width: Optional[float] = None   # None = use profile's typical_lot_width
    lot_depth: Optional[float] = None   # None = use profile's typical_lot_depth
    num_floors: Optional[int] = None    # None = derive from gabarit (street_width)
    style_preset: str = "RESIDENTIAL"   # Resolved to StylePreset enum
    seed: int = 42
    has_entresol: Optional[bool] = None  # None = use profile's has_entresol
    has_porte_cochere: bool = True
    corner_chamfer: bool = False        # Pan coupé at one or both ends
    ground_floor_type: str = "AUTO"     # Resolved to GroundFloorType enum
    profile_name: Optional[str] = None  # Override style_preset's default profile
    profile_variation: float = 0.0      # 0.0 = exact, 0.0-1.0 = variation amount
    street_width: Optional[float] = None  # Street width in metres; determines gabarit
    overrides: BuildingOverrides | None = None  # Per-field overrides for seeded output

    # -- Regulatory period ----------------------------------------------------
    # The era decides the height table, the shape of the comble, and where
    # balconies may go.  ``year`` is a convenience: when set it resolves to
    # the era in force that year and wins over ``era``.
    era: str | Era = Era.SECOND_EMPIRE
    year: Optional[int] = None
    roof_fill: Optional[float] = None   # 0-1: how far the comble builds out to its legal max
                                        # (None = the profile's own value)

    def resolved_era(self) -> Era:
        """Return the ``Era`` this config specifies, from *year* or *era*."""
        from .reglement import era_for_year, get_reglement
        if self.year is not None:
            return era_for_year(self.year)
        if isinstance(self.era, Era):
            return self.era
        return get_reglement(self.era).era
