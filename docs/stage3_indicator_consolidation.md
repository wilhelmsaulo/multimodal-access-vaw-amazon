# Stage 3 candidate-indicator consolidation

## Decision unit

The MCDM alternative universe remains all 144 municipalities of Pará. Census-sector information is used only to construct/aggregate municipal indicators or support later SOM diagnostics.

## Consolidated candidate set

| Indicator | Conceptual block | Direction for prioritization need | Availability | Current status |
|---|---|---|---:|---|
| `criterion__reachable_service_fraction` | Multimodal access | lower = greater access deficit / higher priority need | 143/144 | retain candidate |
| `criterion__services_within_120_fraction` | Multimodal access | lower = greater access deficit / higher priority need | 143/144 | retain candidate |
| `criterion__nearest_reachable_service_time_min` | Multimodal access | higher = greater access burden / higher priority need | 141/144 | retain candidate; structural-missing treatment required |
| `criterion__median_reachable_service_time_min` | Multimodal access | higher = greater access burden / higher priority need | 141/144 | retain candidate; structural-missing treatment required |
| `criterion__health_specialized_absence` | Institutional response | 1 = absence / greater deficit | 144/144 | retain candidate |
| `criterion__creas_absence` | Institutional response | 1 = absence / greater deficit | 144/144 | retain candidate |
| `criterion__specialized_security_absence` | Institutional response | 1 = absence / greater deficit | 144/144 | retain candidate |
| `criterion__specialized_justice_absence` | Institutional response | 1 = absence / greater deficit | 144/144 | retain candidate |
| `criterion__rural_female_share` | Territorial/sociodemographic context | higher = greater rural territorial exposure; interpretation is contextual, not VAW-risk | 144/144 | retain candidate for final MCDM specification review |

## Statistical consolidation result

For the nine candidates:

- no Pearson or Spearman pair reaches absolute correlation 0.80;
- no VIF reaches 5;
- maximum VIF = 3.3861;
- rural female share VIF = 1.4883;
- PCA is not required;
- population size and institutional unit counts are excluded from the candidate statistics because they are diagnostics/support variables rather than independent criteria.

## Structural missingness policy

### Afuá

Afuá remains an alternative. Its access values are structurally missing because the frozen Stage 2 evidence has 44 upstream origins but no origin that satisfies the conservative primary-routing promotion policy. The municipality is classified as a network-coverage limitation, not as proven inaccessibility. No zero, infinite time, or synthetic penalty is permitted.

### Colares and Santa Cruz do Arari

Both municipalities have routing-ready origins and all relevant origin-service pairs were tested, but no service is reachable in the frozen reference network. Zero reachability is therefore an observed result. Finite travel-time summaries do not exist and remain missing; arbitrary travel-time imputation is prohibited.

The choice of MCDM method must therefore explicitly state how structural missing values are handled. A method that silently requires complete finite values cannot be applied without a predeclared and scientifically justified transformation/sensitivity rule.

## Temporal compatibility

- Census-based female population weights and rurality: 2022;
- network/reference OD: frozen 2026 representation;
- CNES/CREAS: 2026-08-19 snapshot;
- specialized security/TJPA: 2026-08-20 snapshot.

The matrix is a mixed-reference analytical construct: current response-system/access representation combined with Census 2022 population/territorial structure. This lag is explicit and is not treated as exact temporal alignment.

## Variables not promoted to the core MCDM matrix

- female population size: diagnostic/aggregation support only;
- female age structure: SOM/descriptive sensitivity only because municipal age-data coverage is uneven;
- 60/180-minute access shares and p90 travel time: sensitivity diagnostics;
- raw counts of services/institutional pillars: diagnostics only;
- income, literacy/education, race/color/ethnicity: deferred until a dedicated construct/source/missingness/ethical and redundancy audit is performed.

## Readiness gate

The candidate-indicator construction, missingness audit, temporal provenance, distribution review, correlation/redundancy audit, VIF audit, conditional PCA decision, and restrained sociodemographic review are now documented.

The next formal decision is **MCDM model and weighting/robustness strategy**, with explicit attention to the structural missing-access cases and mixed benefit/cost/binary/context criteria. No ranking should be produced before that decision is locked.
