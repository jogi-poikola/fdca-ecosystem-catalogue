# FDCA Ecosystem Map — Formal Layout Specification

**Specification ID:** `FDCA-LAYOUT-SPEC`  
**Version:** `1.1`  
**Purpose:** Define the ecosystem-map layout independently from `build_dashboard.py`, so a future coding agent can update the builder to conform to this specification without having to infer design policy.

---

## 1. Core principle

Treat the FDCA ecosystem map as a **bilingual, capacity-constrained hierarchical packing problem**, not as a conventional proportional treemap.

Company count is represented by equal-size dots. Category area therefore does not need to be mathematically proportional to company count. Geometry exists primarily to fit:

- equal-size company dots;
- bilingual category labels;
- family clustering;
- fixed corner anchors;
- stable ordering;
- growth headroom;
- readable aspect ratios;
- efficient use of space.

---

## 2. Output formats

The system produces two independently optimized master layouts:

```yaml
formats:
  landscape:
    width_ratio: 16
    height_ratio: 9

  portrait:
    width_ratio: 6
    height_ratio: 19
```

The portrait layout MUST NOT be created by squeezing or mechanically transforming the landscape layout. Both are solved independently using the same policy constraints.

> Note: this specification assumes the earlier “landscape 9:16” requirement meant a physically landscape `16:9` output. The ratio is isolated as configuration and can be changed without altering the algorithm.

---

## 3. Fixed anchors

### 3.1 Masthead / search

The FDCA masthead area is a hard top-left anchor:

```text
masthead.x = 0
masthead.y = 0
```

It contains at least:

- FDCA logo;
- introductory copy;
- search bar.

### 3.2 Data Center Operators

The Data Center Operators family is a hard top-right anchor:

```text
operators.y = 0
operators.x + operators.width = canvas.width
```

Its dimensions may change as counts or labels change, but it MUST remain attached to the top-right corner.

---

## 4. Dynamic taxonomy

The algorithm MUST NOT assume the current category or family list is permanent.

It MUST support:

- categories being added;
- categories being removed;
- family names changing;
- category names changing;
- company counts increasing or decreasing;
- empty categories;
- new families;
- bilingual naming changes.

Stable internal identity SHOULD use taxonomy slugs rather than displayed labels.

Company count MUST NOT be used as the primary source of category order.

---

## 5. Bilingual geometry

Switching between English and Finnish MUST NOT change the layout geometry.

The layout engine measures both languages before solving and uses the larger text envelope.

Conceptually:

```text
required_width =
    max(
        english_required_width,
        finnish_required_width
    )
```

The same principle applies vertically when wrapping differs.

Once a layout has been calculated:

```text
switch language
→ replace strings only
→ do not recalculate geometry
```

---

## 6. Typography

All category titles MUST use the same font family, weight and font size.

A category title:

- MUST fit within the configured maximum number of lines;
- MUST NOT be individually shrunk;
- MUST NOT be clipped;
- MUST NOT use ellipsis;
- MUST NOT disappear.

If a candidate box cannot fit the title under these rules, that candidate shape is invalid.

Actual font metrics SHOULD be used rather than character-count approximations.

---

## 7. Deterministic line wrapping

Line wrapping SHOULD be deterministic.

Preferred break locations:

1. spaces;
2. explicit soft break points;
3. editorially approved compound-word breakpoints.

The renderer SHOULD NOT rely exclusively on browser-dependent hyphenation.

The taxonomy may optionally provide language-specific break hints.

Example:

```json
{
  "fi": "Sähköverkko- ja sähköasemarakentaminen",
  "breaks_fi": [
    "Sähköverkko- ja",
    "sähköasemarakentaminen"
  ]
}
```

---

## 8. Dot capacity

Each company occupies one equal-size dot slot.

For every category:

```text
capacity >= company_count
```

Possible grid alternatives may include, for a category with 17 companies:

```text
3 × 6 = 18
4 × 5 = 20
5 × 4 = 20
6 × 3 = 18
```

The solver should consider multiple candidate shapes rather than deriving a single rectangle directly from company count.

---

## 9. Candidate category shapes

For each category and each reasonable number of dot columns:

```text
rows = ceil(required_capacity / columns)

width =
    max(
        dot_grid_width,
        bilingual_title_width
    )

height =
    label_band_height
    + dot_grid_height
```

The candidate is retained only if:

- the title fits within the allowed line count;
- minimum padding is respected;
- all dots fit;
- the category stays within defined aspect-ratio limits, unless no better feasible shape exists.

Dominated candidates SHOULD be removed before global solving.

A dominated candidate is one that is not better in capacity, area, aspect ratio, label fit, or stability than another candidate.

---

## 10. Family clustering

Categories sharing the same top-level family/background color MUST remain spatially clustered.

The hierarchy is:

```text
Canvas
    ↓
Family
    ↓
Category
    ↓
Dot grid
```

Categories from one family MUST NOT be freely interleaved with categories from another family.

---

## 11. Rectangular family mode

In rectangular mode:

- each family occupies one rectangle;
- each category occupies one rectangle.

This is the default production mode because it provides:

- clear family boundaries;
- simple rendering;
- predictable visual hierarchy;
- good stability;
- straightforward testing.

Its main disadvantage is that unused space can remain inside a family’s bounding rectangle.

---

## 12. Polyomino / Tetris family mode

In polyomino mode:

- individual categories remain rectangular;
- the union of a family’s category rectangles may form a connected orthogonal shape such as an L, T or staircase.

This can reduce wasted space by allowing another family to occupy otherwise unused corners.

Polyomino family shapes SHOULD:

- remain connected;
- avoid holes where practical;
- avoid one-cell-wide tendrils;
- avoid excessive concave corners;
- avoid intricate interlocking;
- remain visually recognizable as one family.

The solver SHOULD penalize excessive perimeter and fragmentation.

---

## 13. Growth headroom

The layout MAY reserve spare dot capacity so small membership changes do not immediately trigger geometry changes.

Example:

```text
current companies = 31
allocated capacity = 35
```

The next four companies can then occupy existing empty slots.

Headroom MUST be configurable; see Section 26.

---

## 14. Layout stability

Previous published geometry MAY be supplied as solver input.

The optimizer SHOULD prefer keeping categories in approximately familiar positions when the efficiency loss is small.

Example principle:

```text
best possible whitespace = 6.2%
stable alternative       = 6.8%
```

A stable alternative may be preferred if it falls within the configured tolerance.

However, if preserving the old layout causes severe inefficiency or infeasibility, the solver may reflow.

---

## 15. Reflow hysteresis

The map SHOULD NOT fully reflow after every count change.

If spare capacity already exists:

```text
new company
→ fill spare slot
→ keep geometry
```

A larger reflow occurs only when configured trigger conditions are met, such as:

- category capacity overflow;
- taxonomy change;
- label geometry change;
- output format change;
- explicit manual rebuild.

---

## 16. Empty categories

The behavior of zero-company categories is configurable.

Supported policies are defined in Section 26.

The recommended production behavior is to keep empty taxonomy categories visible as minimum-size titled tiles for taxonomy continuity and layout stability.

---

## 17. Optimization hierarchy

Feasibility is lexicographic and MUST come before visual optimization.

### 17.1 Hard feasibility constraints

A valid layout MUST satisfy all applicable hard constraints:

- all elements fit inside the artboard;
- no illegal overlaps;
- masthead is top-left;
- Data Center Operators is top-right;
- all dots fit;
- all titles fit;
- all category titles share the configured font treatment;
- all titles respect the maximum line count;
- EN/FI geometry is identical;
- family clustering is preserved.

### 17.2 Optimization priorities

Among feasible layouts, optimize approximately in this order:

1. minimize unused space;
2. minimize movement from previous published layout;
3. minimize family perimeter / fragmentation;
4. avoid extreme category aspect ratios;
5. preserve canonical order / adjacency;
6. preserve useful spare capacity.

The implementation MAY use lexicographic optimization or weighted optimization, but MUST NOT allow a soft objective to override a hard requirement.

---

## 18. Solver approaches

The specification is implementation-agnostic.

Supported solver strategies may include:

- recursive treemap heuristics;
- deterministic packing heuristics;
- beam search;
- skyline / guillotine packing;
- local improvement;
- CP-SAT / constraint optimization;
- hybrid approaches.

Solver choice MUST NOT change the visual contract.

---

## 19. Short-label suggestions

The algorithm MUST NOT invent or silently publish abbreviations unless explicitly permitted by policy.

It MAY:

- identify labels that create significant space pressure;
- test approved aliases;
- report the measured layout improvement from using them.

Example diagnostic:

```text
Normal names:
unused map area = 9.2%

Approved short names:
unused map area = 7.1%

gain = 2.1 percentage points
```

Human/editorial control remains authoritative.

---

## 20. Output model

The solver SHOULD produce structured layout data separate from rendering code.

Example:

```json
{
  "format": "landscape",
  "mode": "rectangular",
  "canvas": {
    "width": 160,
    "height": 90
  },
  "anchors": {
    "masthead": {
      "x": 0,
      "y": 0,
      "w": 45,
      "h": 25
    },
    "data_center_operators": {
      "x": 128,
      "y": 0,
      "w": 32,
      "h": 25
    }
  },
  "categories": [
    {
      "slug": "power_equipment",
      "rect": {
        "x": 0,
        "y": 26,
        "w": 30,
        "h": 25
      },
      "label_lines": {
        "en": ["POWER EQUIPMENT"],
        "fi": ["SÄHKÖLAITTEET"]
      },
      "dots": {
        "count": 33,
        "capacity": 35,
        "cols": 7,
        "rows": 5
      }
    }
  ]
}
```

The renderer should consume solved coordinates rather than re-deriving layout decisions.

---

## 21. Diagnostics

Each generated layout SHOULD include diagnostic information such as:

```yaml
occupied_area_pct: 91.7
unused_area_pct: 8.3

company_count: 338

total_dot_capacity: 365
spare_dot_capacity: 27

max_category_aspect_ratio: 2.8
mean_category_aspect_ratio: 1.41

movement_cost_from_previous: 0.12
moved_category_count: 3

label_constrained_categories:
  - grid_substation_construction
  - design_engineering

capacity_constrained_categories:
  - power_equipment
```

Diagnostics should make algorithm comparisons measurable rather than subjective.

---

## 22. Failure behavior

If a valid layout cannot be produced, the engine MUST NOT silently violate the design rules.

It MUST NOT silently:

- shrink one category label independently;
- hide a category;
- hide company dots;
- exceed the title line limit;
- clip bilingual labels.

Instead it should return an explicit infeasibility result with diagnostics.

Possible explicit recovery strategies include:

- reduce global title font size;
- reduce dot pitch globally;
- use approved short labels;
- switch rectangular → polyomino;
- require editorial review.

Recovery strategies MUST be policy-controlled.

---

## 23. Responsive behavior

The recommended system has two master topologies:

```text
LANDSCAPE MASTER
PORTRAIT MASTER
```

The browser selects one and scales it uniformly.

The layout SHOULD NOT continuously reflow for arbitrary browser widths unless explicitly configured otherwise.

---

## 24. Rectangular versus polyomino benchmarking

Where supported, the solver MAY generate both modes and compare them.

Example:

```yaml
rectangular:
  unused_area_pct: 10.4
  movement_cost: 0.08
  max_category_aspect: 2.7

polyomino:
  unused_area_pct: 6.9
  movement_cost: 0.10
  max_category_aspect: 2.6
  concave_corners: 8
```

The layout selection policy determines whether an efficiency gain justifies the more complex family geometry.

---

## 25. Separation of concern

The specification distinguishes four different classes of settings:

### Requirements
Define what constitutes a valid FDCA map.

### Layout policies
Choose among legitimate valid visual behaviors.

### Optimization parameters
Control preferences among valid layouts.

### Implementation settings
Control how the computer searches for a valid layout.

An implementation agent MUST NOT treat an implementation setting as permission to violate a requirement.

---

# 26. Formal layout policy variables

This section defines the primary variables that SHOULD be implemented in the layout configuration.

Each setting has a status:

- `locked`: changing it violates the current FDCA visual requirements;
- `configurable`: supported production policy choice;
- `experimental`: supported for comparison/testing;
- `implementation`: solver/runtime choice that should not change the visual contract.

---

## 26.1 `layout_mode`

Controls overall family geometry.

```yaml
layout_mode:
  value: rectangular
  status: configurable
  allowed:
    - rectangular
    - polyomino
    - auto
```

### `rectangular`

Every family occupies one rectangle. Categories inside it are rectangular.

**Upsides**
- clearest family hierarchy;
- simplest rendering;
- easiest to stabilize;
- easiest to test;
- closest to the current visual language.

**Downsides**
- can leave unused area inside family rectangles.

### `polyomino`

Categories remain rectangular, but the union of the family may be L-, T-, staircase-, or other connected orthogonal shapes.

**Upsides**
- can use otherwise wasted corners;
- potentially significantly higher area efficiency.

**Downsides**
- more complex boundaries;
- more visual complexity;
- more difficult packing and testing.

### `auto`

Generate both rectangular and polyomino alternatives and choose according to configured selection thresholds.

**Upsides**
- uses polyomino only when there is a meaningful gain.

**Downsides**
- published visual style can change unless thresholds are strict.

**Recommended:** `rectangular` initially.

---

## 26.2 `category_shape_mode`

Controls whether individual categories may have irregular shapes.

```yaml
category_shape_mode:
  value: rectangular
  status: locked
  allowed:
    - rectangular
    - polyomino
```

### `rectangular`

Every category remains rectangular.

**Upsides**
- simple titles;
- predictable dot grids;
- easy scanning;
- straightforward hit targets and interactions.

**Downside**
- slightly less packing freedom.

### `polyomino`

Individual categories may also become irregular.

**Upside**
- maximum theoretical packing flexibility.

**Downsides**
- awkward title placement;
- unclear dot order;
- confusing category boundaries;
- significantly more complex rendering.

**Recommended and effectively required:** `rectangular`.

The useful Tetris optimization belongs at the family level, not the category level.

---

## 26.3 `empty_category_policy`

Controls zero-company categories.

```yaml
empty_category_policy:
  value: show
  status: configurable
  allowed:
    - show
    - hide
    - reserve
```

### `show`

Render a minimum-size titled tile with zero dots.

**Upsides**
- stable taxonomy;
- users see that the category exists;
- first new company does not introduce an entirely new box;
- better long-term mental map.

**Downside**
- consumes canvas area without displaying companies.

### `hide`

Do not render zero-company categories.

**Upside**
- maximum current density.

**Downsides**
- categories appear/disappear with membership;
- topology changes more often;
- taxonomy looks inconsistent over time.

### `reserve`

Do not visibly render the category but reserve some internal family space for it.

**Upside**
- some future stability without visible empty tiles.

**Downside**
- can create unexplained whitespace.

**Recommended:** `show`.

---

## 26.4 `capacity_headroom`

Controls spare dot capacity.

```yaml
capacity_headroom:
  mode: percentage
  status: configurable

  fraction: 0.08
  minimum_slots: 1
  maximum_fraction: 0.20

  allowed_modes:
    - none
    - fixed_slots
    - percentage
    - adaptive
```

### `none`

Allocate only enough capacity for current companies.

**Upside**
- tightest present-day packing.

**Downside**
- very small membership changes can trigger reflow.

### `fixed_slots`

Give every category the same number of spare positions.

Example:

```yaml
capacity_headroom:
  mode: fixed_slots
  slots: 2
```

**Upside**
- simple and predictable.

**Downside**
- disproportionate between tiny and large categories.

### `percentage`

Reserve a fraction of current count.

Example:

```yaml
capacity_headroom:
  mode: percentage
  fraction: 0.08
  minimum_slots: 1
  maximum_fraction: 0.20
```

**Upside**
- scales naturally with category size;
- good general stability.

**Downside**
- intentionally consumes some empty capacity.

### `adaptive`

Allocate headroom from historical growth patterns.

**Upside**
- potentially best long-term use of spare capacity.

**Downsides**
- requires historical data;
- more complex;
- less transparent.

**Recommended initially:** `percentage`.

---

## 26.5 `language_geometry`

Controls which languages affect box dimensions.

```yaml
language_geometry:
  mode: maximum_across_languages
  status: locked

  languages:
    - en
    - fi

  allowed_modes:
    - active_language
    - maximum_across_languages
    - reference_language
```

### `active_language`

Size the map for the currently visible language.

**Upside**
- can produce tighter single-language layouts.

**Downside**
- switching language changes geometry.

### `maximum_across_languages`

Every label is sized for whichever configured language requires more room.

**Upside**
- language switch changes text only;
- perfect geometry consistency across EN/FI.

**Downside**
- a shorter language may visibly have spare label space.

### `reference_language`

Use one fixed language as geometry reference.

**Upside**
- simple and stable.

**Downside**
- another language may not fit.

**Required FDCA mode:** `maximum_across_languages`.

---

## 26.6 `category_font`

Controls category-title font sizing.

```yaml
category_font:
  mode: fixed
  status: locked

  size_px: 14

  allowed_modes:
    - fixed
    - global_adaptive
    - per_category_adaptive
```

The actual pixel value MUST be calibrated to the final renderer.

### `fixed`

All categories use exactly one font size.

**Upside**
- visual consistency;
- satisfies the FDCA requirement.

**Downside**
- long labels can force wider/taller boxes.

### `global_adaptive`

The engine may reduce or increase font size globally, but every category still uses the same value.

**Upside**
- useful explicit recovery mechanism.

**Downside**
- typography can change between builds.

### `per_category_adaptive`

Each category may use its own font size.

**Upside**
- easiest way to force everything to fit.

**Downside**
- violates the desired visual consistency.

**Required normal mode:** `fixed`.

If global adaptation is ever allowed as a fallback, it must be explicit and global.

---

## 26.7 `category_title_max_lines`

Controls maximum title wrapping.

```yaml
category_title_max_lines:
  value: 2
  status: locked
```

### `1`

**Upside**
- very clean.

**Downside**
- forces many very wide tiles.

### `2`

**Upside**
- strong compromise between readability and packing freedom.

**Downside**
- some long Finnish titles still constrain geometry.

### `3+`

**Upside**
- permits narrower boxes.

**Downsides**
- taller headers;
- weaker visual rhythm;
- conflicts with the stated design requirement.

**Required:** `2`.

---

## 26.8 `category_order`

Controls how much freedom the solver has to reorder categories inside a family.

```yaml
category_order:
  mode: canonical_stable
  status: configurable
  source: taxonomy

  allowed_modes:
    - taxonomy
    - count_descending
    - solver_free
    - canonical_stable
```

### `taxonomy`

Respect exact source taxonomy order.

**Upside**
- highly predictable.

**Downside**
- can prevent better packing.

### `count_descending`

Order by company count.

**Upside**
- large-first packing can be efficient.

**Downsides**
- membership changes alter order;
- visual topology becomes unstable.

### `solver_free`

Allow any order.

**Upside**
- maximum packing freedom.

**Downside**
- categories may move substantially between versions.

### `canonical_stable`

Use taxonomy order as a strong preference, while allowing limited deviations if they materially improve packing.

**Upsides**
- good compromise between stability and efficiency.

**Downside**
- slightly more complex to implement.

**Recommended:** `canonical_stable`.

---

## 26.9 `layout_stability`

Controls how strongly previous geometry affects a new solve.

```yaml
layout_stability:
  mode: soft
  status: configurable

  use_previous_layout: true
  near_optimal_tolerance: 0.02

  allowed_modes:
    - none
    - soft
    - threshold
    - locked
```

### `none`

Ignore previous coordinates.

**Upside**
- best instantaneous packing.

**Downside**
- layout may change frequently.

### `soft`

Previous positions contribute a movement penalty.

**Upside**
- strong balance between adaptability and familiarity.

**Downside**
- may accept slightly more whitespace.

### `threshold`

Preserve the existing topology if it remains within a specified efficiency tolerance.

Example:

```yaml
near_optimal_tolerance: 0.02
```

means the stable solution may be kept if its unused area is within about 2 percentage points of the better solution.

**Upside**
- understandable and controllable.

**Downside**
- requires comparison against alternative solutions.

### `locked`

Keep previous positions unless infeasible.

**Upside**
- strongest visual stability.

**Downside**
- efficiency can degrade substantially over time.

**Recommended:** `soft` with a near-optimal tolerance.

---

## 26.10 `reflow`

Controls when the full layout is recalculated.

```yaml
reflow:
  mode: on_constraint_change
  status: configurable

  triggers:
    capacity_overflow: true
    taxonomy_change: true
    label_geometry_change: true
    format_change: true

  allowed_modes:
    - always
    - on_any_count_change
    - on_capacity_overflow
    - on_constraint_change
```

### `always`

Recalculate on every build/data change.

**Upside**
- always freshly optimized.

**Downside**
- unnecessary movement and computation.

### `on_any_count_change`

Recalculate whenever any count changes.

**Upside**
- straightforward.

**Downside**
- little practical stability benefit from reserved capacity.

### `on_capacity_overflow`

Keep geometry until a category runs out of spare slots.

**Upside**
- very stable for normal membership growth.

**Downside**
- other structural changes need separate handling.

### `on_constraint_change`

Reflow when meaningful constraints change, including overflow, taxonomy, labels, or format.

**Upside**
- best match for this project.

**Downside**
- slightly more event logic.

**Recommended:** `on_constraint_change`.

---

## 26.11 `short_labels`

Controls abbreviation behavior.

```yaml
short_labels:
  mode: diagnostics_only
  status: configurable

  allowed_modes:
    - disabled
    - diagnostics_only
    - approved_aliases
    - automatic

  automatic_alias_generation_allowed: false
```

### `disabled`

Ignore alternate short names.

**Upside**
- simplest editorial policy.

**Downside**
- no insight into labels causing layout inefficiency.

### `diagnostics_only`

Always build from full names but test whether approved shorter aliases would materially improve the layout.

**Upside**
- gives editors measurable evidence;
- no silent terminology changes.

**Downside**
- cannot automatically realize the space saving.

### `approved_aliases`

The taxonomy may contain approved short display names and the solver may use them.

**Upside**
- can improve layout without invented terminology.

**Downside**
- aliases must be maintained editorially.

### `automatic`

Allow the system to invent abbreviations.

**Upside**
- maximum flexibility.

**Downsides**
- potentially inconsistent or inaccurate terminology;
- undesirable for controlled publication.

**Recommended initially:** `diagnostics_only`.

`automatic` SHOULD be treated as non-production unless explicitly authorized.

---

## 26.12 `solver`

Controls how the computer searches for a solution.

```yaml
solver:
  strategy: heuristic
  status: implementation
  deterministic: true

  allowed:
    - recursive_treemap
    - heuristic
    - cp_sat
    - hybrid
```

### `recursive_treemap`

Closest to the current approach.

**Upsides**
- simple;
- fast;
- deterministic.

**Downsides**
- limited search space;
- weaker fit for bilingual constraints;
- potentially more unused area.

### `heuristic`

Beam search, skyline packing, guillotine packing, iterative improvement, etc.

**Upsides**
- practical speed;
- flexible;
- well suited to candidate category shapes.

**Downside**
- cannot guarantee theoretical optimality.

### `cp_sat`

Constraint optimization.

**Upsides**
- natural support for discrete shapes and non-overlap;
- rigorous hard constraints;
- strong solution quality.

**Downsides**
- additional dependency;
- more implementation complexity;
- potentially longer solve times.

### `hybrid`

Use a heuristic to create a strong starting solution, then improve it with a stronger optimizer.

**Upside**
- potentially best speed/quality tradeoff.

**Downside**
- highest engineering complexity.

**Recommended first implementation:** `heuristic`.

The specification MUST remain independent of solver choice.

---

## 26.13 `responsive_layout`

Controls how viewport shapes map to layout topologies.

```yaml
responsive_layout:
  mode: master_layouts
  status: locked

  allowed_modes:
    - continuous
    - single_master
    - master_layouts

  masters:
    landscape:
      width_ratio: 16
      height_ratio: 9

    portrait:
      width_ratio: 6
      height_ratio: 19
```

### `continuous`

Recompute for arbitrary viewport sizes.

**Upside**
- maximum theoretical viewport fit.

**Downsides**
- topology changes constantly;
- harder testing;
- harder for users to learn spatial locations.

### `single_master`

Use one layout everywhere and scale it.

**Upside**
- perfect topology consistency.

**Downside**
- performs poorly across radically different aspect ratios.

### `master_layouts`

Maintain a small set of independent canonical layouts.

**Upsides**
- predictable;
- efficient for both landscape and portrait;
- easy to test;
- only a small number of topologies.

**Downside**
- explicit switch between masters.

**Required current approach:** `master_layouts`.

---

## 26.14 `layout_selection`

Controls how rectangular and polyomino alternatives are chosen.

```yaml
layout_selection:
  mode: configured
  status: experimental

  allowed_modes:
    - configured
    - best_efficiency
    - threshold

  polyomino_minimum_absolute_gain: 0.025
  polyomino_minimum_relative_gain: 0.20
```

### `configured`

Publish the explicitly selected `layout_mode`.

**Upside**
- predictable design language.

**Downside**
- does not automatically exploit an unusually strong polyomino result.

### `best_efficiency`

Publish whichever mode minimizes whitespace.

**Upside**
- maximum area efficiency.

**Downside**
- even a tiny efficiency improvement could switch visual style.

### `threshold`

Use polyomino only if its gain crosses defined thresholds.

**Upside**
- rational compromise;
- visual complexity is introduced only when worthwhile.

**Downside**
- requires comparison builds.

**Recommended initially:** `configured`.

Later, after benchmarking, `threshold` is the recommended experimental mode.

---

# 27. Recommended default configuration

```yaml
layout_policy:

  # --------------------------------------------------
  # GEOMETRY
  # --------------------------------------------------

  layout_mode:
    value: rectangular
    status: configurable
    allowed:
      - rectangular
      - polyomino
      - auto

  category_shape_mode:
    value: rectangular
    status: locked
    allowed:
      - rectangular
      - polyomino

  empty_category_policy:
    value: show
    status: configurable
    allowed:
      - show
      - hide
      - reserve


  # --------------------------------------------------
  # CAPACITY / GROWTH
  # --------------------------------------------------

  capacity_headroom:
    mode: percentage
    status: configurable

    fraction: 0.08
    minimum_slots: 1
    maximum_fraction: 0.20

    allowed_modes:
      - none
      - fixed_slots
      - percentage
      - adaptive


  # --------------------------------------------------
  # LANGUAGE / TYPOGRAPHY
  # --------------------------------------------------

  language_geometry:
    mode: maximum_across_languages
    status: locked

    languages:
      - en
      - fi

    allowed_modes:
      - active_language
      - maximum_across_languages
      - reference_language

  category_font:
    mode: fixed
    status: locked

    size_px: 14

    allowed_modes:
      - fixed
      - global_adaptive
      - per_category_adaptive

  category_title_max_lines:
    value: 2
    status: locked


  # --------------------------------------------------
  # ORDER / STABILITY
  # --------------------------------------------------

  category_order:
    mode: canonical_stable
    status: configurable
    source: taxonomy

    allowed_modes:
      - taxonomy
      - count_descending
      - solver_free
      - canonical_stable

  layout_stability:
    mode: soft
    status: configurable

    use_previous_layout: true
    near_optimal_tolerance: 0.02

    allowed_modes:
      - none
      - soft
      - threshold
      - locked

  reflow:
    mode: on_constraint_change
    status: configurable

    triggers:
      capacity_overflow: true
      taxonomy_change: true
      label_geometry_change: true
      format_change: true

    allowed_modes:
      - always
      - on_any_count_change
      - on_capacity_overflow
      - on_constraint_change


  # --------------------------------------------------
  # LABEL ALIASES
  # --------------------------------------------------

  short_labels:
    mode: diagnostics_only
    status: configurable

    allowed_modes:
      - disabled
      - diagnostics_only
      - approved_aliases
      - automatic

    automatic_alias_generation_allowed: false


  # --------------------------------------------------
  # SOLVER
  # --------------------------------------------------

  solver:
    strategy: heuristic
    status: implementation
    deterministic: true

    allowed:
      - recursive_treemap
      - heuristic
      - cp_sat
      - hybrid


  # --------------------------------------------------
  # RESPONSIVE OUTPUT
  # --------------------------------------------------

  responsive_layout:
    mode: master_layouts
    status: locked

    allowed_modes:
      - continuous
      - single_master
      - master_layouts

    masters:

      landscape:
        width_ratio: 16
        height_ratio: 9

      portrait:
        width_ratio: 6
        height_ratio: 19


  # --------------------------------------------------
  # RECTANGULAR / POLYOMINO SELECTION
  # --------------------------------------------------

  layout_selection:
    mode: configured
    status: experimental

    allowed_modes:
      - configured
      - best_efficiency
      - threshold

    polyomino_minimum_absolute_gain: 0.025
    polyomino_minimum_relative_gain: 0.20
```

---

# 28. Optimization configuration

Optimization parameters SHOULD be kept separate from layout policy.

Preferred model:

```yaml
optimization:

  priorities:
    feasibility: mandatory

    whitespace:
      priority: 1

    stability:
      priority: 2

    family_compactness:
      priority: 3

    category_aspect_ratio:
      priority: 4

    ordering:
      priority: 5

    spare_capacity:
      priority: 6
```

A weighted alternative may be supported:

```yaml
optimization:
  weights:
    whitespace: 100
    movement: 30
    family_perimeter: 15
    aspect_ratio: 10
    order_disruption: 5
```

However, lexicographic priorities are preferred because they are easier to reason about and make it harder for soft preferences to accidentally override important design behavior.

---

# 29. Requirement status semantics

The implementation MUST understand or preserve the distinction between these statuses.

## `locked`

Changing this setting violates current FDCA requirements.

Examples:

- bilingual geometry invariant;
- fixed category font policy;
- two-line title maximum;
- rectangular individual categories.

## `configurable`

A supported production design choice.

Examples:

- rectangular versus polyomino family mode;
- headroom amount;
- zero-category treatment;
- layout stability strength.

## `experimental`

Supported for benchmarking or future publication after visual review.

Examples:

- threshold-based automatic polyomino selection.

## `implementation`

Controls solver mechanics rather than visual policy.

Examples:

- heuristic versus CP-SAT.

---

# 30. Validation tests

A conforming implementation SHOULD include automated tests for at least:

1. English/Finnish toggle produces identical coordinates.
2. Every category title fits at the configured font size.
3. No title exceeds the configured line count.
4. Masthead remains top-left.
5. Data Center Operators remains top-right.
6. Every dot fits within its category.
7. Family clustering is preserved.
8. No illegal rectangle overlaps occur.
9. Adding a company within spare capacity does not force reflow.
10. Capacity overflow triggers reflow when configured.
11. Adding a new category produces a valid layout.
12. Removing a category behaves according to `empty_category_policy`.
13. Long Finnish labels are included in geometry calculations.
14. Landscape master satisfies its configured aspect ratio.
15. Portrait master satisfies its configured aspect ratio.
16. Layout generation is deterministic for identical inputs and settings.
17. Polyomino mode produces connected family regions.
18. Polyomino mode respects perimeter / fragmentation limits.
19. No individual category font-size variation occurs in fixed mode.
20. Infeasible cases produce explicit diagnostics rather than silent rule violations.

---

# 31. Implementation-agent instruction

When this specification is later given to an agent that updates `build_dashboard.py`, the agent SHOULD:

1. treat this specification as the visual/layout contract;
2. preserve existing functionality not contradicted by the specification;
3. separate layout solving from rendering where practical;
4. expose policy variables rather than burying them as magic constants;
5. preserve taxonomy slugs as stable identifiers;
6. keep hard constraints distinct from soft optimization preferences;
7. produce deterministic output;
8. emit useful diagnostics;
9. avoid changing taxonomy wording unless explicitly requested;
10. avoid silently introducing new fallback behavior.

The builder script itself is **not modified by this specification**.

---

## End of specification
