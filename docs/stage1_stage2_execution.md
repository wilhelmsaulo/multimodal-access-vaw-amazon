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

### Services

Columns:

- `service_id`: validated service identifier;
- `service_type`: functional category; different service types are not assumed to be substitutes;
- `capacity`: observed capacity or a documented proxy. A unit-presence proxy must be explicitly labelled as such.

### Multimodal travel matrix

Columns:

- `origin_id`;
- `service_id`;
- `scenario` (at minimum `flood_season` and `dry_season` when seasonal comparison is claimed);
- `travel_time_min`.

Travel time must come from the validated multimodal routing workflow. It must not be back-filled with arbitrary river speeds.

## E2SFCA outputs

Scores are calculated independently by scenario and service type. The implementation supports continuous exponential or Gaussian decay and an optional maximum travel-time threshold. Outputs include service supply-demand ratios and sector accessibility scores.

## Spatial analysis

Global Moran and Local Moran/LISA require a spatial-neighbor edge list with `source_id` and `target_id`. The current implementation accepts an externally constructed defensible adjacency graph so that the exact spatial-neighbor rule remains explicit and auditable.

## Current execution status

As of the Stage 1/Stage 2 branch creation, the public repository contains the analysis code, documentation, census-sector workflow, and source inventories, but it does not contain the validated post-routing travel-time matrix, validated service-capacity table, or final Stage 1 indicator matrix. Therefore numerical Stage 1 and E2SFCA results must not be reported until those generated analytical inputs are recovered or rebuilt and added as redistributable derived products.
