# 01 — Data sources and analytical universe

## Scope

The analytical universe is the 144 municipalities of Pará. Accessibility origins are represented at a finer spatial level and subsequently aggregated to municipalities for decision analysis. Destination services used in the reference accessibility model are located in Pará; interstate functional influences are retained for discussion/context rather than silently mixed into the primary surface-access model.

## Core source families

The project combines official or auditable sources for:

- Census 2022 population and territorial structure (IBGE);
- specialized health/service information (including CNES where applicable);
- CREAS / social-assistance infrastructure;
- specialized security and justice services;
- road and waterway network evidence;
- validated service directories and institutional sources;
- contextual police-record data where used descriptively rather than as an assumed demand proxy.

The detailed inventory and source-specific caveats are maintained in [`docs/data_inventory.md`](../data_inventory.md).

## Census-sector origin layer

The frozen Census 2022 origin universe contains 16,714 sectors across all 144 municipalities. Population and female-population attributes are preserved without synthetic filling of unavailable/suppressed values. The dedicated audit is in [`docs/ibge_census2022_sector_audit.md`](../ibge_census2022_sector_audit.md).

For routing, 12,673 origins were classified as routing-ready in the frozen endpoint representation. Their role is to preserve within-municipality spatial heterogeneity before municipal aggregation.

## Service destinations

The corrected reference OD uses 225 service destinations. Service categories are kept functionally explicit; different service types are not assumed to be interchangeable merely because they are spatially proximate.

A separate institutional consolidation identified 236 validated physical opportunities used for the non-transport municipal indicators: 138 CREAS, 71 specialized health opportunities, 21 specialized security opportunities and 6 specialized justice opportunities.

## Temporal compatibility

The study is a mixed-reference analytical construct. Census population structure refers to 2022, while several network/service inventories were validated or frozen in 2026. This temporal heterogeneity is documented explicitly rather than treated as contemporaneous measurement.

Temporal compatibility is therefore evaluated as part of provenance and interpretation. The study does not claim that all layers represent the same observation date.

## Variables deliberately excluded from core MCDM

Income/poverty, schooling, race/color and female age structure were reserved for SOM/profile analysis instead of being inserted directly into the MCDM. This separation is deliberate: MCDM represents access/institutional/territorial priority burden, while SOM will characterize socioeconomic and demographic profiles.

Female population magnitude is an aggregation/support quantity, not a direct priority criterion.

## Reproducibility links

- Source inventory: [`docs/data_inventory.md`](../data_inventory.md)
- Census audit: [`docs/ibge_census2022_sector_audit.md`](../ibge_census2022_sector_audit.md)
- Project scope: [`docs/project_scope.md`](../project_scope.md)
- Decision log: [`docs/decision_log.md`](../decision_log.md)

## Planned visual bundle

This documentation layer will include, as reproducible outputs, a source-flow diagram, an origin/service overview map and compact source-summary tables. Final maps must include title, legend, scale, north/orientation and source/year.
