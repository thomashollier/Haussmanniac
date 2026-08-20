# Project Brief — Constraint-Derived Architecture

A design document for a fresh codebase. No implementation, no API — the goal,
the thesis, the shape of the problem, and the traps.

---

## The thesis

Buildings of a place and a period look alike because they were built under the
same constraints, not because their architects followed a style guide. Street
width capped the height. An ordinance capped how far a balcony could stick out
and how low it could hang. A decree fixed the shape of the roof above the
cornice. Land was expensive, so every parcel was built to the limit. What we
call "the Haussmann building" is the residue of those rules meeting a
programme.

**If you model the constraints, the style comes out for free — and it varies
correctly when the inputs vary.**

That is the whole bet. Most procedural building tools are parameterised by
taste: sliders for roof pitch, ornament density, window ratio. They produce
plausible buildings, and every one of them is plausible in the same way,
because the author's taste is the only thing holding them together. A
constraint-derived system produces buildings that are *right for a situation*,
and that change the way a historian would predict when the situation changes.

The test: widen the street and the building should get taller *in steps*, not
continuously, because the rule was a step table. Move the date past a decree
and the roofline should change shape. Take away the mezzanine and the balcony
should jump up a floor by itself — because the balcony rule is about height
above the pavement, not about which floor it is.

---

## What the system is for

You describe a **situation**, not a building:

- the street it faces, and how wide it is
- the parcel — width, depth, mid-block or corner
- the year it was built
- how much money was behind it
- what the ground floor is for

and you get the building that would have stood there. There is no slider for
roof angle, because nobody chose the roof angle.

Everything the system produces should be traceable to a reason. "Why is this
roof a straight 45° plane?" should have an answer, and the answer should be
citable to a source, not to a magic number.

---

## The street is the unit, not the building

This is the part most tools get wrong, and it is the part that matters most
visually.

A building on a nineteenth-century Paris street is not autonomous. Its cornice
continues its neighbour's cornice. Its string courses and balcony lines run
across the party wall. It shares that wall. The block was conceived as one
architectural object with several owners, and the regulation said so
explicitly.

So the system's primary output should be a **street or block**, with the
individual building as a subordinate unit. Get this backwards and you spend
forever bolting alignment onto a generator that was designed to produce
isolated objects — the buildings will each be individually convincing and the
street will read as a shelf of models.

Concretely, the block level owns: the shared cornice line, the storey
registration across neighbours, party walls, corner treatment where two streets
meet, and the rhythm of frontage widths along the run.

---

## The fitting problem

This is the interesting engineering, and it's what you noticed in the Unreal
tools: a facade is a row of modules that has to exactly fill a width which is
never a whole multiple of the module.

Three ways out, and a real system needs all three plus a policy for choosing:

- **Stretch** the modules. Fine to a few percent, obvious past that.
- **Repeat** as many as fit and absorb the remainder somewhere.
- **Substitute** a different, better-fitting module set.

The grammar describes the *arrangement* — end, repeat, special, end — with each
slot declared fixed, repeating, or flexible, and the solver distributes the
leftover. That's the split-grammar idea and it's well-trodden; CityEngine has
done it since the mid-2000s.

Where this project has a better answer than "add padding": **the leftover is
architecturally meaningful.** In this vocabulary the remainder at each end of a
facade is a real element with a name, a minimum size, and rules of its own —
and when it grows past a threshold, the correct move is not to pad but to
insert a narrow extra bay of a different kind. So the fitting solver shouldn't
be a generic layout engine with a cosmetic gutter; it should be expressed in
the vocabulary of the thing being built, where "what to do with the slack" is
itself part of the grammar.

The same solve recurs at every level — frontages along a block, storeys up a
facade, bays across a storey, panes within an opening — so it's worth designing
once and well.

### The module model

A facade is a row of modules of a few kinds — openings (doors, windows),
filler (piers, columns, blank wall), and ends — each with a *range* of
acceptable widths rather than one width. As the frontage grows, slack is
absorbed by the elastic pieces until a threshold, at which point another
module appears. That much is straightforward. The details that decide whether
it looks real:

**The repeating unit is the bay, not the opening.** Measure it centreline to
centreline of the filler: half-pier, opening, half-pier. If the opening is the
module and the pier is the gap *between* modules, the ends become a special
case that infects the whole run — you are permanently deciding whether it
starts on a half pier or a whole one. With centreline units, *N* modules is
exactly *N* × width, and the only special case is the two ends, which is where
you wanted it.

**Elasticity is per type, and that ordering is the solver.** Doors are close to
rigid, and *absolute* rather than proportional — a carriage entrance must admit
a carriage; it does not scale with the building. Openings are semi-rigid, since
their proportion is doing aesthetic work. Filler is elastic; it exists to be
adjusted. Ends are the most elastic, with a hard minimum. Absorb into the most
elastic thing available.

**Absorption is a ladder, not a single threshold.** In order:

1. widen the ends only — the interior rhythm stays perfect
2. widen all the filler uniformly
3. widen the whole bay toward its maximum
4. insert a **narrow special** — a half-bay, a blind panel, a small round window
5. add a full module and start again

Step 4 is the one that gets skipped and the one that makes it convincing. Five
good bays plus one narrow odd one reads far better than six squeezed bays, and
the odd one is a legitimate element in the vocabulary rather than an apology
for bad arithmetic. If the composition has a central feature, step 5 usually
jumps by **two** modules, so it takes twice the slack to reach.

**Solve the rhythm once per building; storeys decorate the same grid.**
Openings align vertically — that is load-bearing masonry, not a preference. If
every storey runs the fitting solver independently you get near-alignment,
which reads as wrong immediately. The horizontal solve belongs to the facade;
a storey then chooses what occupies each slot — window here, blind panel there,
a richer surround on the good floor — but never where the slots are.

**Specials have position rules, not free slots.** The entrance is not "one of
the modules, anywhere." It wants the centre, or a particular offset, and when
it sits off-centre the composition should answer it — putting the narrow
special on the opposite side, for instance. The grammar needs positional and
symmetry constraints, not just a sequence of types.

**Corners are not a module type.** A corner is the join between two grammars,
and where the corner is chamfered it becomes a third short facade with its own
rhythm. Give it its own concept early; it will not fit into the row.

---

## Absolute and proportional

Every dimension in the model is one of three kinds, and conflating them is the
error that makes procedural buildings look like toys. Decide which kind a
number is *before* you write it down.

| Kind | Set by | Scales with the building? |
|---|---|---|
| **Absolute** | the human body, or an object that must pass through | no |
| **Proportional** | composition and money | yes |
| **Regulatory** | a number written in a law | no, until the law changes |

**Absolute** quantities are fixed by physical fit. A carriage entrance is about
as wide as a carriage. A door is as tall as a person plus clearance. Stair
risers, handrail heights, balustrade gaps narrow enough for a child's head,
sill heights someone can lean on, the depth of a step, the bore of a flue —
none of these care how grand the building is.

**Proportional** quantities are compositional. Bay width, the ratio of pier to
opening, window aspect, the projection of a cornice relative to the height it
crowns, the scale and density of ornament, storey height above its legal
minimum. These are where ambition and budget show up, and they should move
together as one coherent shift rather than drifting independently.

**Regulatory** quantities look absolute but are a different species: they are
numbers in a text, not consequences of a body. A 0.80 m limit on projections, a
6 m minimum height for a balcony, a 2.60 m minimum storey. They don't scale
with wealth and they don't vary by taste — they change on a date, when the
statute changes. Worth marking as their own kind because they are the ones that
carry a citation and the ones a test should assert against the source.

**The test for classifying a number:** ask what would have to change in the
world for it to change.

- "People would have to be a different size" → absolute
- "The owner would have to be richer, the street grander" → proportional
- "The law would have to be rewritten" → regulatory

### Why it matters more than it sounds

A building reads as large or small *because* its absolute elements stay put
while its proportional ones grow. The grand building on the boulevard is
legible as grand precisely because its doorway is only a little bigger than the
modest one's while its windows are much bigger, its bays wider, its cornice
heavier. The door is the ruler the eye measures everything else against.

Scale everything together and you get the doll's-house effect: a building with
no internal reference for size, which could be photographed at any scale and
look identical. This is exactly why a lot of procedural architecture feels like
a model rather than a place — there is no invariant human-sized element to
measure against, so the eye finds no purchase.

The inverse failure is rigidity: treating proportional quantities as fixed, so
every building has the same bay width regardless of status, and the wealth axis
stops reading at all.

So the *ratio* between the two families is the signal. Don't optimise either in
isolation.

### Practical consequences

- **The fitting solver must respect the split.** Absolute elements cannot
  absorb slack — they are rigid by definition, and stretching a doorway to
  make the arithmetic work is exactly the move that destroys scale. Slack goes
  to proportional elements only. This is the same ordering as the elasticity
  ladder above; it is not a coincidence, it is the same fact stated twice.
- **Scaling a building is one explicit operation on one family.** When you move
  from a modest building to a grand one, the proportional family scales and the
  absolute family does not. That should be a single deliberate transformation,
  not a multiplier sprinkled through the rules where it can be applied twice or
  forgotten.
- **Absolutes survive simplification.** When you drop level of detail, the
  human-scale references are the last thing to go, because they are what tells
  the viewer how big the thing is.
- **Carry the kind with the number.** If a quantity doesn't know what kind it
  is, someone will eventually scale a doorway, and nobody will be able to say
  why the result looks wrong — only that it does.

---

## The rule model

Most of what a building "is" ends up captured as tables of settings. The
trouble is rarely the file — it is that the tables are keyed by a **closed
enumeration of positions** (ground, second, third…), and the condition under
which a row applies is left implicit in the key. A list saying that balconies
go on the second and fifth floors does not say *why*, so it cannot be composed
with anything, argued with, or carried to another city.

Make identity **derived** and applicability **explicit**. Four phases, each
reading only the phases before it:

**1. Structure.** The fitting solver fills a budget with slots — storeys into a
height budget, bays into a width. Purely quantitative: no names, no roles, no
meaning. The output is a grid.

**2. Roles, derived rather than declared.** Walk the resulting stack and assign
identity by positional predicate: the bottom slot is the base; a short slot
directly above the base is a mezzanine; the first tall residential slot is the
principal floor; the slot under the roof is the attic. You never declare that a
building *has* a principal floor — you say what makes a floor principal, and
the label falls out.

This is what removes the fixed floor enumeration. A five-storey and a
nine-storey building get correct roles from the same rules, with no special
case for the extra storeys, because nothing is enumerating positions any more.

**3. Qualification.** Rules map a *context* to properties. The context is
everything knowable about a slot once structure and roles exist: its role, its
height above the pavement, its index from the bottom and from the top, its own
height, the building's date and class, whether it is the centre bay, whether it
sits beside the entrance. "A balcony where the floor is at least 6 m above the
pavement" is then a rule rather than a list — and it is the actual ordinance,
which is the point.

**4. Composition by layering.** Rule sets stack: a base vocabulary, then a
period layer, then a class layer, then a site-specific layer. Later layers
override; specificity breaks ties. This is where composability actually lives.
A period stops being a column in a spreadsheet and becomes a rule set you
compose in.

### Consequences

- **Floor heights** stop being a stored value per named floor. They come out of
  the solver filling its budget, driven by per-role *relations*: a preferred
  range, a minimum, and "shorter than the one below." A taper constant becomes
  a relation rather than a magic number.
- **Per-storey rhythm** dissolves as a concept. Since the horizontal grid is
  solved once for the whole facade, a storey has no rhythm of its own — it has
  a *filling* of a shared grid. The rule is "for this slot, on a floor of this
  role, what occupies it?", which cannot drift out of vertical alignment
  because there is only one grid.

### Costs to go in with your eyes open about

- **Build the "why" tooling first, not last.** A rule system is strictly harder
  to debug than a table until you can ask any element which rule produced it.
  Defer that and you will spend weeks bisecting rule sets by hand and conclude
  the approach was a mistake.
- **The phase order is a hard invariant.** Rules reading facts that later rules
  mutate is how this design fails: you get order-dependence that presents as
  nondeterminism. Each phase reads strictly backwards, no exceptions.
- **Don't build a DSL on day one.** Rules can be ordinary functions in the host
  language for a long time. The discipline is in the shape — context in,
  properties out, layered, traceable — not in having a text format. Start with
  the file format and you will design the semantics around what is easy to
  parse.

---

## Chronology: features appearing and disappearing

A vocabulary is not static across a century. Ironwork, sculpture, socle
treatment and shopfronts all turn over, at different rates, and a building is
datable precisely because they do. The system has to represent that, and the
obvious way — sorting features into named periods — is the wrong one.

### Two chronologies that do not align

Regulation changes on decree dates. Style changes on political and cultural
ones. In Paris the regulatory hinges are 1859, 1884 and 1902; the stylistic
ones are around 1848, 1853 and 1870. Force a single period enum to carry both
and its boundaries will be wrong for one of them.

Worse, a period enum cannot represent the ordinary case: the building that kept
its outdated ironwork for twenty years after the fashion moved on. That is most
buildings.

### Date windows, not periods

Attach the date to the **feature variant**, not to the building:

- each variant carries an earliest year, a period of peak prevalence, and a
  latest year
- a building of year *Y* sees the variants whose windows contain *Y*, weighted
  by prevalence at *Y*
- periods survive as documentation labels, never as something the code branches
  on

The moment a rule reads `period == SECOND_EMPIRE` the enum is back and the
straggler building has become unrepresentable.

### Two mechanisms, not one

- **Legality is a step function.** Oriels are illegal in 1881 and legal in
  1882. Binary, sourced, testable — the mechanism the regulatory model already
  implements.
- **Fashion is a distribution.** Mascarons do not appear on a date; they grow
  common through the 1870s and elaborate through the 1890s. That wants a ramp,
  a peak and a decline.

Conflating them gives you streets where every facade of a given year is
suddenly identical.

### Adoption lags down the class ladder

The detail most systems miss. A feature appears on grand frontages first and
reaches modest streets ten to twenty years later, if ever — and modest
buildings *retain* superseded forms long after they have gone from the
boulevards. So availability is a function of `(feature, year, class)`, not
`(feature, year)`. A grand building and a modest building both built in 1885
are not stylistic contemporaries.

### Construction date is not observation date

Where street-level realism comes from. Buildings are altered: shopfronts turn
over every generation or two, ironwork gets added, and combles were
demonstrably raised — the later regulations held the cornice line while
letting owners heighten their roofs, which is visible along the Rue de Rivoli.

So a facade seen in 1900 may have 1860 bones, an 1885 roof and an 1898
shopfront. Give elements their own dates alongside the building's, and a street
stops looking as though it went up in a single afternoon.

### The feature families worth dating

Paris-specific; each typology brings its own. If only five are modelled, these
are the strongest dating instruments on a real facade.

**Ironwork** — the best of them. Thin repeating lozenges and palmettes
(1820s–40s) → dense symmetrical cast scrollwork, the standard haussmannian
railing (1850s–80s) → looser Renaissance-revival variants (1880s–90s) →
asymmetric organic whiplash (from c. 1895; Guimard's Castel Béranger 1895–98,
the métro entrances 1900).

**Socle treatment** — flat incised *refends* (1820s–50s) → raised *bossage*,
heavy and regular (1850s–70s) → exaggerated picturesque rustication,
vermiculated and rock-faced (1880s–90s).

**Keystone sculpture** — plain (Restauration) → simple console or volute
(Second Empire) → *mascaron* appearing sparingly, common from the 1870s,
elaborate and near-universal by the 1890s. Figurative work, caryatids and
atlantes follow the same curve on grand buildings.

**Roof** — plain slate slope with small dormers → 45° comble with pedimented
dormers (canonical 1853–84) → curved arc comble, taller and more elaborate,
with varied dormer shapes and iron cresting (1884+). Zinc becomes the dominant
Parisian roofing material mid-century.

**Shopfront** — timber with small panes, pilasters and a painted fascia
(1820s–50s) → cast-iron framing with larger panes (1850s+) → plate glass
(1870s+) → elaborate carved devantures, mosaic stall risers, gilded lettering
on glass (1890s+). Shopfronts turn over fastest, which makes them the best
carrier of the observation-date idea.

Secondary families worth having: **facing material** (render over rubble →
*pierre de taille* on the percées → brick and *grès flammé* accents in the
1890s); **window surrounds** (bare band → moulded architrave → pediments
richening through the 1870s–80s → irregular heads in the 1890s); **cornices**
(simple moulding → modillions and dentils → very deep and bracketed); and
**composition itself** (strict block unity enforced from the 1855 circulaire,
weakening after the 1880s into individualised facades, corner rotondes and
domes).

### Labels for talking, not for branching

Restauration and Louis-Philippe (1820–48), Second Empire (1853–70), early Third
Republic (1870–84), Belle Époque (1884–1900). Useful in documentation and in
conversation. Not categories the code is allowed to test against.

---

## More than one city

The system should carry to other places and periods — New York brownstones,
the SoHo cast-iron lofts, London terraces, Amsterdam canal houses. Not as a
someday-maybe, but as the thing that proves the abstraction is real rather than
a Paris-shaped coincidence.

The encouraging evidence: **the envelope idea transfers directly.** New York's
1916 Zoning Resolution set facade height as a multiple of the street width and
then required everything above it to stay within a sloping sky-exposure plane.
That is structurally the same rule as the Paris gabarit — street width
determines permitted mass, then a bounding surface governs what happens above
the cornice — in different geometry. The wedding-cake skyscraper and the
mansard roof are one idea in two dialects.

**What stays invariant** is the machinery: budget-filling, derived roles,
contextual qualification, layered composition, and the
absolute/proportional/regulatory split. The test of the design is whether
adding a new typology requires touching the engine at all.

**What varies** is a bundle, and that bundle is the unit of extension:

- the envelope rules
- how roles are assigned from position
- the module catalogue and its dimensional limits
- the qualification rules
- the relation to neighbours
- how the building terminates at the top

Two of those are not merely different numbers and will be baked in silently if
you are not watching for them:

**Block relation is itself a parameter.** Paris is *alignment* — separate
buildings agreeing on shared horizontal lines. A brownstone row is
*repetition* — one builder, one set of plans, twenty near-identical houses
raised together. A cast-iron street is closer to *independent*. Same
block-level concept, three different relations.

**The vertical datum can move.** Paris puts the ground floor at street level.
A brownstone raises its principal floor half a storey up an external stoop,
with a service entrance below grade. That is not a difference in floor heights;
it is the datum itself moving, and it brings systematic asymmetry with it — the
door sits to one side, never centred. A model that assumes ground = datum =
symmetric composition cannot represent a rowhouse at all.

### A validation set that stresses different things

| Typology | What it stresses |
|---|---|
| Haussmann Paris | envelope derivation, block alignment, near-symmetry |
| New York brownstone | section and datum, asymmetry, repetition, very few bays |
| SoHo cast-iron | catalogue kit-of-parts, wide bays, material-limited members |
| Amsterdam canal house | extreme aspect ratio, gable as a dated terminating module, non-vertical facade plane, longitudinal light-well rhythm |

SoHo is the most instructive for a module grammar, because those facades
genuinely were assembled from catalogue components — the ironworks of Badger
and Bogardus sold facade parts out of a book. It is the one case where the
procedural model matches the historical construction process exactly.

Amsterdam earns its place for a different reason: it is the clearest proof that
the constraint really is generative, because the same constraint produced the
same form in cultures that never met (see below). It also breaks assumptions
the other three leave intact — the facade plane is not vertical, the terminating
module carries the building's date, and the plan is so deep that light has to be
brought in along its length, which is a rhythm on an axis the other typologies
never exercise.

### Sequencing

Do not design the universal system first. Build one typology properly, then
port to a second **deliberately, as an abstraction-discovery exercise**, and
budget for rewriting the boundary once when you do. An abstraction designed
before you have built two will fit neither.

Paris then brownstone is a good order: they differ in section and symmetry,
which are precisely the assumptions most likely to have been baked in without
anyone noticing.

---

## A catalogue of generative constraints

Reference material, and the specification the rule model has to be able to
express. Each entry is a nameable constraint and the visible form it produced.
Organised by *mechanism*, because the mechanism is the thing that recurs;
cities are just where it happened to land.

### Tax on a dimension

The strongest evidence for the thesis, because it is **convergent**. Amsterdam,
Kyoto and Hanoi are unconnected, and all three taxed buildings on their street
frontage. All three produced the same freak proportion: very narrow, very deep,
very tall.

- **Amsterdam** — frontage-based taxation, reinforced by regulated plot widths
  in the canal-belt expansions. The knock-ons cascade: stairs too narrow for
  furniture, so goods came in through the windows; so you need a **hoisting
  beam** at the gable; so facades were deliberately built **leaning forward**
  (*op de vlucht*) to stop the load scraping the front. And because frontage was
  the scarce, taxed, visible dimension, all display migrated to the gable —
  which is why gable *shape* (step, neck, bell, cornice) is simultaneously the
  ornament and the dating evidence. A tax produced a proportion, the proportion
  produced a piece of equipment, and the equipment produced the ornamental
  vocabulary.
- **Kyoto** — the machiya, known as *unagi no nedoko*, "eel beds": a few metres
  of frontage against twenty or more of depth.
- **Hanoi** — the *nhà ống* or tube house of the Old Quarter, on the same
  logic, and still going: land is still held and valued by frontage, so the
  form persists in new construction across Vietnam. Road widening that slices a
  plot leaves slivers a metre or two deep, and they get built on anyway — the
  *nhà siêu mỏng*, "super-thin houses". A tax rule from the imperial period is
  still generating buildings.

All three then hit the same secondary problem — a plan too deep to light from
its ends — and all three solve it the same way, with interstitial courtyards
and light wells punched along the depth (*tsuboniwa*, *sân trong*). Convergent
twice over.

Britain's **window tax** (1696–1851) is the same mechanism aimed at a different
feature, and survives as bricked-up openings: a rule legible as a *negative*.

### Projection over the street

One policy question, three cities that look nothing alike.

- **Paris** — banned outright from 1607 until 1882, hence the flat wall.
- **Bologna** — the opposite: porticoes *mandated* from the 13th century. You
  may build out over the street on condition that what you create beneath stays
  publicly passable and high enough to ride through. Roughly 40 km of
  continuous arcade.
- **Istanbul** — the Ottoman *cumba*, a projecting timber oriel, normal and
  encouraged rather than tolerated.

### Fire

- **London** — the best single precedent for this project. The **1774 Building
  Act** sorted houses into four **"rates"** by value and floor area, each with
  prescribed wall thicknesses and dimensions: an explicit legal typology ladder,
  which is what a class axis is approximating. Earlier acts produced very
  specific facade details for fire reasons — window frames recessed behind the
  brick face instead of flush, and parapets concealing the roof after projecting
  eaves were banned. Two named regulations, two details on every Georgian
  terrace.
- **New Orleans** — the French Quarter is architecturally *Spanish*, because
  after the fires of 1788 and 1794 the Spanish administration mandated stucco
  over brick and tiled roofs.

### Ground and topography

- **Venice** — inverts the solid/void rhythm. Everything stands on piles in
  soft mud, so load concentrates on the party walls, which frees the middle.
  The characteristic palazzo facade is therefore *open at the centre* (the
  clustered polifora) and *solid at the edges* — exactly backwards from Paris.
- **Edinburgh** — the Old Town reached ten to fourteen storeys in the
  seventeenth century because the Flodden Wall and a narrow glacial ridge left
  only one direction to build. Its social stratification is non-monotonic:
  middle floors most desirable, the poor at the top *and* in the cellars.

### Vehicle geometry

- **Barcelona** — Cerdà's Eixample, 1859, the same year as the Paris règlement,
  chamfered every block corner at 45° so trams and carriages could turn and
  see. Cerdà intended two built sides per block, gardens within, and a 16 m
  height limit; speculation filled all four sides and built higher. Today's
  Eixample is the residue of a rule *consistently violated* — a category worth
  having in its own right: **form as the shape of a rule's failure.**

### Permission rather than purchase

- **Beijing** — ornament gated by *rank*, not by money. Roof tile colour, the
  number of figurines on the ridge, and gate type were legally tied to status.
  This is a different mechanism from a wealth axis: a discrete gate on what is
  permitted, not a dial on what is affordable.

### Assumptions these break

Useful as a checklist against anything the first typology quietly bakes in:

- **Edinburgh** — ornament and desirability are not monotonic with height.
- **Venice** — solid/void may be dense at the edges and open at the centre.
- **Charleston** — the single house turns ninety degrees to the street and is
  entered from a side porch, so the street elevation is not the front at all.
  (Often attributed to a frontage tax, though that is contested; climate and
  privacy are the safer explanation.)
- **Beijing** — ornament can be gated by permission rather than bought.
- **Amsterdam** — the facade plane need not be vertical.
- **Barcelona** — the built rule may differ systematically from the written one.

---

## Open question: what the block owns

Two arguments in this document pull against each other, and the conflict is
real rather than a wording problem.

Earlier: *the street is the unit, not the building* — the block is the primary
object and the building is subordinate. Later: *block relation is a parameter*
— some typologies align, some repeat, some are essentially independent. If
buildings on a cast-iron street are designed independently, then for that
typology the block is doing almost nothing, and forcing everything through a
block-level solve is machinery earning its keep in one case out of three.

### Working it through

The way out is to ask what the block actually owns in each case, rather than
whether it is "primary":

| Relation | The block owns | The building receives |
|---|---|---|
| Alignment | shared horizontal datums | constraints it must satisfy |
| Repetition | the design itself | an instance, plus variation |
| Independence | parcel widths and adjacency | only its lot |

Which exposes the common denominator: **the block always owns the subdivision
of frontage and who abuts whom.** That is irreducible — party walls and lot
widths are block facts under every relation. Everything beyond it is what
varies.

So the block is always primary in the weak sense that it divides the ground and
decides adjacency. The relation decides how much *further* its authority runs.

### The better framing

Three named modes is probably the wrong shape. Alignment, repetition and
independence are not categories but points on a coupling dial: **which
properties are block-scoped rather than building-scoped.** Repetition shares
everything. Independence shares nothing but edges. Alignment shares the
horizontals. Model it as a set of block-scoped bindings and the three modes
fall out as extremes of one mechanism — and you also get the cases the enum
cannot express: a street sharing a cornice height but not storey heights, or a
block built as three separate runs by three builders.

Reality supports this. None of the three typologies is pure. Paris streets are
not perfectly aligned; brownstone rows are not perfect clones, since corner
units are usually wider and differently treated, and long rows were built in
sub-runs; cast-iron streets converge loosely on cornice heights anyway through
shared storey conventions. All three are mixtures, which is exactly what a
bindings model represents and a mode enum does not.

### Why not to settle it on paper

Whether bindings is the right abstraction cannot be known until two typologies
exist. Designing a general binding system now risks a mechanism that elegantly
solves a problem nobody has. Mark this as a decision to be taken at the second
typology port, alongside the other boundary rewrite that port is expected to
force.

### What to do in the meantime

Build the first typology with the block owning its datums **explicitly**, and
keep the block-to-building direction strictly one-way.

The point is to establish the channel before knowing everything that will flow
through it. If the block hands down a bundle of already-resolved decisions,
then adding "and also the whole facade design" for a repetition typology is a
change of contents, not of architecture.

This is worth being disciplined about because the failure is quiet. In the
previous attempt every building sampled its own street width independently —
so buildings that were, by construction, on the same street disagreed about how
wide it was, and their cornice lines did not line up. Nothing errored. The
street simply looked subtly wrong, and the cause was a block-level fact being
resolved per building.

---

## Output should be a description, not a mesh

The generator's product is a structured description of a building: what
elements exist, where, at what size, of what kind. Renderers consume it.

This matters for three reasons. It lets you check the generator's work at
speed, in 2D elevation, without waiting on geometry. It lets the same building
target a game engine, a 3D package, and a drawing. And it keeps the
architectural reasoning in one place instead of leaking into whichever renderer
you wrote first — which it *will* do if you let it, and then the second
renderer disagrees with the first and you can't tell which is right.

Rule of thumb: if a renderer is deciding anything a person could argue about,
that decision is in the wrong place.

Levels of detail belong here too: a block seen from a distance needs silhouette
and material; the building you walk up to needs door furniture.

---

## Determinism and addressability

Same situation plus same seed, same building, forever. This is non-negotiable
for anyone placing these in a world and expecting them to stay put.

Beyond that, every individual decision should be addressable — you should be
able to say "this one gets a flat-arched carriage door" and have everything
else about the building stay exactly as it was. That requires the random
choices to be independent of each other rather than drawn from one sequence,
so that pinning one, or adding a new kind of decision later, doesn't shift
everything downstream.

You will want this on day one and it is painful to retrofit.

---

## Non-goals

- Interiors, structure, services.
- A general modelling tool. This does one vocabulary well.
- Photoreal materials — that's the renderer's job.
- Modelling every building ever built. Vernacular buildings that break the
  rules are out of scope; the whole point is the ones that didn't.

---

## Success criteria

1. Someone who knows Paris doesn't flinch at a generated street.
2. Changing one input changes the output in the way a specialist would predict,
   including the discontinuities.
3. A whole block generates fast enough to iterate on, and reads as one wall.
4. Any element can be traced back to the rule that produced it.
5. Swapping the rule set gives you a different city — Amsterdam canal houses,
   London terraces, brownstones — without touching the machinery. All of them
   are the same problem: constraint, plus programme, plus a module grammar.

---

## Confidence: what is demonstrated and what is not

This document mixes things that have been built and shown to work with things
that are still design hypotheses. Knowing which is which tells you what to hold
loosely when reality pushes back.

**Demonstrated.** The regulatory model. Implemented end to end, tested against
the figures the decrees state, rendered, and independently corroborated — the
envelope arithmetic reproduces the documented 28.50 m ceiling exactly, which
was not fitted to. Deriving form from regulation is not speculative; it works,
and it corrected a real error in the process.

**Largely demonstrated.** The fitting ladder. A working implementation performs
most of it, including insertion of a narrow special and parity-aware module
addition, and the results hold up across wide sweeps of widths and seeds.

**Asserted, on one piece of evidence.** The block as the primary unit. The
supporting evidence is a genuine failure — buildings on a shared street each
resolved the street width independently and their cornices did not line up —
but the full inversion of control has never been built.

**Unproven.** The rule model: phases, derived roles, layered composition. This
is the most elegant part of the document and the part most likely to be wrong.
Nothing here has been implemented. Treat the first typology as its test.

**Speculative.** Everything about multiple typologies. One worked example and
three sketches. The catalogue of constraints is well sourced, but that the same
machinery spans them is a bet, not a finding.

---

## Paris: the specifics to pin down first

Two things the rule model depends on that are named everywhere in this document
and defined nowhere. Both are needed in the first week, and both are decisions
rather than discoveries.

### Role predicates

Roles are derived from the structure alone — no enum, no input. For Paris:

- **Base** — the bottom slot. Unconditional.
- **Mezzanine** — a slot directly above the base whose height falls markedly
  below the median habitable storey. Present only if the stack produced one.
- **Principal** — the *tallest* habitable slot above the base and mezzanine.
  Not "the first tall one": tallest is what the étage noble actually is. Ties
  break to the lowest.
- **Upper** — every slot between principal and attic, ranked upward from the
  principal. Treatment diminishes with rank.
- **Attic** — the slot inside the roof envelope.

Note the base exclusion is load-bearing: a Paris ground floor is often taller
than the noble floor, so "tallest slot" without qualification picks the wrong
one.

### Qualification context

The read-only fact set every rule sees. Complete before qualification begins,
and never mutated by it.

*Structure* — the slot's own dimensions; its level above the pavement; index
from bottom and from top; total storey count.

*Role* — the assigned role, and rank relative to the principal floor.

*Horizontal* (for bay slots) — index from the left and from the centre; whether
it is the centre bay; distance from the entrance bay; whether it is an edge or
inserted special; the slot's kind (opening, filler, special).

*Building* — date and era; class; street width; corner or mid-block.

*Envelope* — cornice height; whether the slot lies within the comble.

If a rule needs a fact not on this list, that is a signal to extend the context
deliberately rather than to reach around it.

---

## Build order

Sequenced by dependency. First typology is Paris, and only Paris.

**Invariants, from the first commit**

- Phases read strictly backwards; no phase mutates what an earlier one read
- A building never samples a block-level fact — it receives it
- Every quantity carries its kind: absolute, proportional, or regulatory
- Every emitted element records the rule that produced it
- Seed plus situation yields identical output, always

**0 — Foundations** (no dependencies)

- Port the regulatory module unchanged
- IR node vocabulary, with serialisation from day one
- Trace facility: ask any node which rule emitted it. Build this *before* the
  second rule exists
- Site context type: street width, parcel dimensions, date, class, corner

**1 — Fitting solver** (generic, reused throughout)

- Fill a budget with typed slots, in one dimension
- Slot kinds: fixed, repeating, flexible — each with minimum, preferred, maximum
- The absorption ladder, parity-aware
- Returns the grid *and* an account of what it did, for the trace
- One solver serves both axes

**2 — Structure phase**

- Envelope from regulation: cornice height and roof envelope
- Vertical: storeys fill the height budget
- Horizontal: bays fill the parcel width, solved **once per building**
- Output is an unnamed grid. No roles, no meaning

**3 — Roles phase**

- Apply the role predicates above
- Reads structure only

**4 — Qualification phase**

- Rules map context to properties: opening type, surround, balcony, ornament,
  material
- A storey never lays out; it fills the shared grid

**5 — Composition**

- Layer rule sets: base vocabulary, period, class, site
- Later layers win; specificity breaks ties
- User overrides are simply a top layer, not a parallel mechanism
- Do not generalise the bundle format yet

**6 — Termination**

- Comble inscribed in the envelope
- Silhouette emitted as a polyline in the IR, not derived by the renderer

**7 — Renderer** (port, do not rewrite)

- Port element renderers only once the IR has stabilised
- Move composition decisions out of the renderer on the way across
- The renderer decides nothing arguable

**8 — Block**

- The channel exists from the first commit; its contents grow later
- First a single lot with datums handed down, then frontage subdivision, shared
  datums, party walls
- Corner as its own short facade, not a module type

**Validation**

- Keep the previous implementation running as a reference oracle; diff the same
  situations against it
- Assert documented regulatory figures against their sources
- Fuzz across seeds, widths and eras for invariant violations
- Done when a generated street does not make a knowledgeable viewer flinch

**Reference images — a standing requirement**

Every typology ships with a corpus of reference photographs *before* it ships
with rules. Keep them in the repository, keyed to the situation each one
represents — street width, date, class, mid-block or corner — wherever that is
known. They are the ground truth the rules are answerable to, and the thing to
reach for when an argument about proportion cannot be settled from the text of
a regulation.

Render generated output alongside them routinely, not once at the end. Contact
sheets — twenty seeds in one grid — are the cheapest way to catch the single
broken outlier among many.

Two limits, both worth respecting:

- Photographs support **qualitative** comparison reliably and **measurement**
  not at all. Perspective, lens and unknown camera position mean dimensions
  cannot be read off them. Where a number matters, use measured surveys and
  drawings, and record the source.
- A visual check is a tripwire, not a passing grade. "That looks wrong" is
  strong evidence; "that looks right" is weak. Small systematic error —
  every window three percent too tall — is invisible to the eye and belongs to
  the assertions instead.

**Deliberately not in the first stage**

- No second typology
- No rule DSL or parser — rules are ordinary functions
- No general binding system for block relation
- No 3-D backend
- No override system separate from rule layering

**First week**

Reproduce one real building's elevation end to end through all four phases,
with a trace explaining every element, before generalising anything. If the
phase model is wrong, this surfaces it in days rather than after rules have
been built on top of it.

---

## Prior art worth studying

- **Split / shape grammars** — Stiny & Gips (1971) for the root idea; Wonka et
  al., *Instant Architecture* (2003); Müller et al., *Procedural Modeling of
  Buildings* (2006). This is the intellectual lineage of the fitting problem.
- **Esri CityEngine** and its CGA grammar — still the most complete expression
  of split-with-flexible-slots, and the reference for how to let a rule author
  express "this part is fixed, this part floats."
- **Unreal's PCG framework**, and the modular building kits built on it — the
  practical, engine-side version of the same problem.
- **Buildify** (Blender) and the Houdini building generators — good at adaptive
  module fitting, deliberately agnostic about *why* a building is shaped as it
  is. That gap is this project's reason to exist.
- **François Loyer, _Paris XIXe siècle: l'immeuble et la rue_** (1987) — the
  argument that the building only makes sense as a piece of the street.
- **The regulations themselves** — the 1783/84 royal declarations, the 1859
  règlement, the 1884 decree, the 1902 decree, and the 1823 ordinance on
  projections. These are the actual source material. They are short, specific,
  and full of numbers.

---

## Lessons from the previous attempt

Written after building one of these end-to-end and finding out where it hurt.

**Start from the constraint, not from the picture.** The previous version was
built from the appearance inward: look at a photo, add a feature, add a
parameter to vary it. It produced good-looking buildings whose parameters were
independent when the real things are not. When the regulation was finally
modelled, several separate "features" collapsed into consequences of one rule —
and one of them turned out to have been wrong for the entire period the project
was named after.

**Watch for the parameter that shouldn't exist.** If you find yourself adding a
slider, ask what decided that quantity in reality. Often the answer is a rule
you haven't modelled yet, and modelling it deletes the slider and three others.

**Separate the ceiling from what was built.** The law says how tall you *may*
build. Economics and programme say how tall you *did*. Conflating them makes
every building a maximal building, which is wrong and looks it. Keep both, and
keep the difference visible.

**Date is a first-class axis, independent of wealth.** A modest building and a
grand one put up the same year obey the same envelope; the same grand building
put up forty years later does not. One axis of "richness" cannot express this
and you will tie yourself in knots trying.

**Keep the rules inspectable and sourced.** Encode where each number comes
from, and mark clearly the ones you inferred because the source was silent.
Then a test can assert the documented figures and fail when the model drifts
from the law it claims to implement.

**Make the fitting solver architectural from the start.** Retrofitting
"meaningful leftover" onto a generic layout routine is worse than designing for
it.
