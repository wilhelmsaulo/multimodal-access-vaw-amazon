# 09 — E2SFCA parameter and service-supply audit

This page records the pre-execution audit required before any E2SFCA output can be declared authoritative.

## Question audited

Can the current consolidated service inventory support a defensible `observed_capacity` specification across the service types used by the accessibility model?

## What the code currently supports

The standardized service schema contains:

- `capacity`;
- `capacity_type`;
- `capacity_source`.

The E2SFCA implementation accepts either:

- `observed_capacity` — use the supplied service-specific capacity value;
- `unit_presence` — assign supply = 1 to each service site.

## Capacity availability by source

### CNES / health

The base CNES normalization initializes `capacity` as missing. Capacity is only added when an external table containing `codigo_cnes`, `capacity`, `capacity_type` and `capacity_source` is available and joined through `apply_cnes_bed_capacity(...)`.

The implemented optional capacity source is a hospital-bed table. This creates two scientific cautions:

1. capacity is not guaranteed to be present for every health service used by the routing/accessibility analysis;
2. total hospital beds are not automatically equivalent to the operational capacity of the specialized VAW-related function represented by the selected CNES service.

Therefore an available bed count cannot be promoted automatically to the reference E2SFCA supply value without an additional service-function validation.

### CREAS

CREAS units are normalized with `capacity = NA`, `capacity_type = NA` and `capacity_source = NA` in the current consolidation implementation.

No comparable team-size/caseload/annual-attendance capacity is currently materialized in the frozen service inventory.

### Specialized justice / TJPA

TJPA specialized units are normalized with `capacity = NA`, `capacity_type = NA` and `capacity_source = NA`.

No comparable number of magistrates, staff, hearing slots or service throughput is currently materialized as a validated capacity measure.

### Specialized security / DEAM and related physical units

The standardized manual-service path can carry a capacity field if supplied, but no project-wide validated and comparable police-service capacity metric has been frozen for the routing service set.

Potential quantities such as number of officers, teams or stations would require a separate conceptual and temporal validation before being interpreted as service capacity.

## Audit conclusion

The current service inventory does **not** provide one homogeneous, validated observed-capacity measure across the service types used in the accessibility analysis.

Consequently, `observed_capacity` is **not currently defensible as a universal reference E2SFCA supply specification**.

The most reproducible common supply representation available from the current frozen service inventory is **unit presence**, in which every validated physical service opportunity contributes one supply unit within its own service type.

This conclusion does **not** yet declare `unit_presence` to be the final E2SFCA reference parameterization. It only establishes that it is the currently available homogeneous supply basis if an authoritative execution is performed without acquiring and validating new capacity data.

## Why service-type separation remains essential

The E2SFCA implementation computes scores separately by `service_type`. A CREAS, specialized health site, police unit and justice unit are therefore not treated as functionally interchangeable supply units.

Under `unit_presence`, the interpretation is:

> accessibility to the spatial availability of validated physical service opportunities of the same functional type, adjusted for female-population competition and travel-time impedance.

It is **not** an estimate of staff productivity, treatment throughput, institutional quality or realized service effectiveness.

## Parameters still requiring closure

Before an authoritative E2SFCA run, the following decisions remain to be frozen:

1. reference supply mode — the audit supports `unit_presence` as the homogeneous currently available option;
2. catchment threshold — none versus a substantively justified maximum time;
3. decay function — none, exponential or Gaussian;
4. decay parameter if applicable;
5. municipal aggregation of origin-level scores;
6. sensitivity grid around threshold/decay assumptions;
7. handling/communication of the Afuá coverage limitation.

## Candidate reference strategy for later evaluation

A scientifically conservative candidate, to be tested rather than silently adopted, is:

- `supply_mode = unit_presence`;
- compute separately by service type;
- use the corrected reference OD only;
- preserve unreachable pairs rather than imputing travel time;
- preserve zero-access origins explicitly;
- evaluate more than one time-decay/catchment specification as sensitivity before selecting a reference configuration;
- keep E2SFCA complementary to the already-frozen direct OD criteria in the MCDM.

## Code evidence

Relevant implementation files:

- `src/accessibility/e2sfca.py` — E2SFCA supply modes and two-step calculation;
- `src/data/service_consolidation.py` — standardized capacity fields and source-specific capacity handling;
- `scripts/consolidate_service_inventory.py` — consolidation audit, including missing-capacity reporting.

This audit should be updated if new official service-capacity data are acquired and validated.
