# 05 — Municipal indicator construction

## Objective

This stage converts the corrected origin–service accessibility information and validated institutional/service inventories into one municipality-level analytical matrix for the 144 municipalities of Pará.

The municipal matrix is the direct input to the statistical audit and MCDM. It is not built from rankings; it is built from interpretable criteria derived from the underlying accessibility and institutional evidence.

## Accessibility indicators

Four network-derived criteria are retained in the corrected MCDM specification:

1. `criterion__reachable_service_fraction`
2. `criterion__services_within_120_fraction`
3. `criterion__nearest_reachable_service_time_min`
4. `criterion__median_reachable_service_time_min`

Additional thresholds/statistics such as 60 min, 180 min and p90 travel-time summaries were retained as diagnostics rather than automatically promoted to decision criteria.

## Institutional/service-deficit indicators

Four binary absence indicators represent the modeled local availability of specialized response infrastructure:

5. `criterion__health_specialized_absence`
6. `criterion__creas_absence`
7. `criterion__specialized_security_absence`
8. `criterion__specialized_justice_absence`

The validated opportunity inventory used in consolidation contains:

- 71 specialized health opportunities;
- 138 CREAS;
- 21 specialized security opportunities;
- 6 specialized justice opportunities.

These indicators represent institutional/service absence under the declared source definitions. They are not interpreted as direct measures of violence incidence.

## Territorial context criterion

The ninth criterion is:

9. `criterion__rural_female_share`

It is computed from Census 2022 sector-level female population and sector situation, aggregated to municipality.

Rural female share was retained because it represents territorial context that can affect practical access beyond municipality-average network measures. Its statistical overlap with the other criteria was audited before final inclusion.

## Variables deliberately kept outside MCDM

The following were not inserted directly into the core decision matrix:

- income/poverty;
- schooling;
- race/color;
- female age structure;
- female population magnitude as a direct criterion.

These variables are reserved for SOM/profile analysis or diagnostic/support roles. This avoids treating demographic composition itself as a normative penalty and reduces conceptual double counting.

## Missingness policy

Unavailable or suppressed values are not synthetically filled without an explicit defensible rule.

Afuá is the only municipality with reduced comparability in the corrected MCDM because its access-time criteria remain unavailable under the locked surface-network scope. This limitation is preserved and flagged rather than converted into a worst-case invented value.

## Core implementation

- `src/analysis/build_municipal_access_matrix.py`
- `src/analysis/revise_municipal_access_candidates.py`
- `src/analysis/build_nontransport_municipal_matrix.py`
- `src/analysis/build_sociodemographic_candidate_audit.py`

Detailed consolidation documentation:

- [`docs/stage3_indicator_consolidation.md`](../stage3_indicator_consolidation.md)
- [`docs/stage3_sociodemographic_selection.md`](../stage3_sociodemographic_selection.md)

## Required published artifacts

The documentation bundle should expose:

- the complete municipal analytical matrix;
- a data dictionary for every criterion;
- municipal maps for each final criterion;
- summary distributions/boxplots or histograms;
- a compact table showing source, reference period, transformation, direction and role for each criterion.

All maps must include **title, legend, scale, north/orientation and source/year**.
