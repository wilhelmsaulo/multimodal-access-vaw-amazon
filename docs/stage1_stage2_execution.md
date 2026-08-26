# Stage 1 and Stage 2 execution contract

This document defines the reproducible inputs and outputs required for the structural-bias audit (Stage 1) and the territorial-accessibility diagnosis (Stage 2).

## Stage 1 — structural audit

Required analytical table: one row per sector or municipality, with a stable identifier and the active indicators used in the audit. Transport subcomponents should be kept separate when available, including walking/access, road, river, waiting, transfer, egress, and any directly observed monetary cost. Flood- and dry-season accessibility measures must be stored in distinct columns or in a long-form scenario table.

The audit computes:

- Spearman correlation matrix;
- VIF diagnostics;
- PCA on standardized indicators;
- standardized variance share by declared block;
- flood-versus-dry Spearman rank stability;
- absolute seasonal rank changes;
- implicit weights produced by equal weighting of all indicators versus equal weighting of blocks.

High correlation or VIF is a diagnostic, not an automatic exclusion rule. Indicator retention requires conceptual review.

## Stage 2 — E2SFCA accessibility

Three tables are mandatory.

### Origins

Columns:

- `origin_id`: census-sector or other defensible population-origin identifier;
- `female_population`: female resident population.

The final origin point must represent inhabited space. Rural polygon centroids are not accepted as final origins without independent validation.

Two official IBGE 2022 evidence layers are now integrated into the origin workflow:

1. **Localidades do Brasil**, which provides named permanent inhabited localities and official coordinates. Pará has 4,837 localities. Every locality is spatially assigned to a census sector and the workflow audits sectors with zero, one or multiple localities.
2. **CNEFE 2022 georeferenced addresses**, used to investigate a single residentially anchored representative point per sector. A privacy-preserving workflow audits the Pará file schema, species fields and `NV_GEO_COORD` quality levels without publishing raw address-level coordinates.

The preferred final rule is to retain one female-population demand total per census sector and derive one representative inhabited origin from residential evidence, rather than duplicating a sector population across multiple locality points.

### Services

Columns:

- `service_id`: validated service identifier;
- `service_type`: functional category; different service types are not assumed to be substitutes;
- `primary_supply_weight`: fixed at `1` for every validated routing-ready unit;
- optional capacity metadata may be retained but is not used by the primary model.

The service reconstruction pipeline covers CNES/DEMAS, Censo SUAS/CREAS, TJPA specialized units and the official Ligue 180 network publication. Missing coordinates remain blockers. Missing operational capacity is not imputed and is not a blocker because the estimand is presence-based territorial accessibility, not service throughput.

### Multimodal travel matrix

Columns:

- `origin_id`;
- `service_id`;
- `scenario` (at minimum `flood_season` and `dry_season` when seasonal comparison is claimed);
- `travel_time_min`.

Travel time must come from the validated multimodal routing workflow. It must not be back-filled with arbitrary river speeds or straight-line distance.

The origin-destination contract in `src/network/od_matrix.py` materializes candidate pairs only after origin and destination readiness checks. It deliberately leaves `travel_time_min` empty until the validated network solver produces the value.

## E2SFCA outputs

Scores are calculated independently by scenario and service type, with `S_j = 1` generated explicitly by the executor. The implementation supports continuous exponential or Gaussian decay and an optional maximum travel-time threshold. Outputs include service supply-demand ratios, sector accessibility scores and female-population-weighted municipal scores. Zero-access origins are retained explicitly.

## Spatial analysis

Global Moran and Local Moran/LISA require a spatial-neighbor edge list with `source_id` and `target_id`. The current implementation accepts an externally constructed defensible adjacency graph so that the exact spatial-neighbor rule remains explicit and auditable.

## Current execution status

The reference-network routing layer is closed with 12,673 origins, 225 services and 2,851,425 OD pairs. The presence-based supply rule is authorized, but final E2SFCA execution is blocked by the population-coverage gate: the OD includes 80.50% of upstream access-evidence origins and 85.90% of their female population, with Afuá entirely absent. Formal Stage 1 remains conditional on a versioned analytical indicator table and explicit indicator blocks. The `reference_network` scenario must not be relabelled as flood or dry season.
