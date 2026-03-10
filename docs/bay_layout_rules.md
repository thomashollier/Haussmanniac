# Bay Layout Rules — Uniform Bays, Edge Pier Absorption

This document describes the algorithm used by `HaussmannGrammar.solve_bay_layout()`
to distribute bays across a facade.  Defaults live in `core/profile.py` → `BayProportions`.

---

## Definitions

| Term           | Description |
|----------------|-------------|
| **Bay**        | The repeating module: half bay-pier + bay window + half bay-pier. Measured centerline-to-centerline. |
| **Bay window** | The opening (window zone) within a bay — the space between the bay piers. |
| **Bay pier**   | The solid stone column that is part of a bay. Each bay has two half-piers; adjacent halves merge into one full pier. |
| **Edge pier**  | The pier butted against the facade edge, providing a buffer between the outermost bays and the side of the building. Absorbs all leftover width. |
| **Door bay**   | The bay to which the porte-cochère belongs. Functions like a standard bay but can be scaled wider to accommodate width constraints and add stylistic features. |

---

## Layout Structure

```
|<-edge pier->|<hp>|  bay window  |<hp><hp>|  bay window  |<hp><hp>|  bay window  |<hp>|<-edge pier->|
              |<-------- bay -------->|    |<-------- bay -------->|    |<-------- bay -------->|
```

`hp` = half bay-pier.  Adjacent half-piers merge into one full bay pier.

---

## Algorithm

**Given**: `facade_width`, `bay_width` (from profile), `pier_ratio` (from profile)

### Step 1: Determine bay count

From facade width thresholds (always odd for symmetry):

| Facade Width    | Bay Count |
|-----------------|-----------|
| < 8.0 m        | 3 bays    |
| 8.0 – 13.0 m   | 5 bays    |
| 13.0 – 18.0 m  | 7 bays    |
| >= 18.0 m       | 9 bays    |

### Step 2: Compute layout

```
bay_pier_w  = bay_width × pier_ratio
bay_window  = bay_width × (1 - pier_ratio)
interior    = bay_count × bay_width
edge_pier   = (facade_width - interior) / 2
```

### Step 3: Validate edge piers

If `edge_pier < 0.1 m`, reduce `bay_count` by 2 and retry.
Edge piers have **no upper limit** — wide edges are historically correct.

### Step 4: Emit BaySpecs

Each BaySpec describes the **bay window** (not the full bay):

```
x_offset = edge_pier + half_bay_pier + i × bay_width
width    = bay_window
```

---

## Parameters (defaults)

| Parameter    | Default | Description                                    |
|--------------|---------|------------------------------------------------|
| `bay_width`  | 1.80 m  | Full bay (half bay-pier + bay window + half bay-pier) |
| `pier_ratio` | 0.29    | Bay pier width as fraction of bay width        |

Derived:
- `bay_pier` = 1.80 × 0.29 = **0.522 m**
- `bay_window` = 1.80 × 0.71 = **1.278 m**

---

## Example Layouts (variation=0)

| Profile          | Lot Width | Bays | Bay Window | Bay Pier | Edge Pier |
|------------------|-----------|------|------------|----------|-----------|
| GRAND BOULEVARD  | 15.0 m    | 7    | 1.278 m    | 0.522 m  | 1.461 m   |
| RESIDENTIAL      | 11.0 m    | 5    | 1.292 m    | 0.528 m  | 1.214 m   |
| MODEST           | 7.8 m     | 3    | 1.193 m    | 0.487 m  | 1.624 m   |
