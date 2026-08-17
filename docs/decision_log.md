# Decision log

Use one entry for every methodological decision that can change the interpretation of results.

## 2026-08-17 — Repository initialization

**Decision:** create a repository independent of the submitted IEEE TCSS and IEEE Access studies.

**Reason:** the new study has a different unit of analysis, outcome, and computational workflow.

**Consequence:** previous code and data may be reused only after provenance, licensing, and conceptual-fit audits.

## 2026-08-17 — Accessibility is the outcome

**Decision:** the primary outcomes are travel-time accessibility and territorial inequality.

**Excluded interpretations:** incidence, individual risk, underreporting, service quality, and service effectiveness.

## 2026-08-17 — Intra-municipal origins

**Decision:** prioritize census sectors, localities, and defensible populated points over municipal seats or geometric municipal centroids.

**Reason:** municipality-level measures can conceal rural and riverine disadvantage.

## 2026-08-17 — Multimodal door-to-door time

**Decision:** represent access, waiting, in-vehicle travel, transfers, and egress.

**Reason:** infrastructure presence and minimum network time do not represent operational accessibility.

## 2026-08-17 — Air transport restriction

**Decision:** keep air transport disabled in the ordinary-access baseline.

**Reason:** an aerodrome does not imply an affordable, frequent, or publicly accessible connection.

## 2026-08-17 — Selective reuse from preceding repositories

**Decision:** reuse only generic acquisition, provenance, harmonization, and source-catalog infrastructure.

**Included:** SIDRA connector, collection metadata, data-source registry, IBGE-code and numeric harmonization, transport catalog/downloader, and historical source manifests.

**Excluded:** police processing, MCDA, rankings, previous results, municipal aggregate accessibility indicators, simplified visualization geometry, and approximate service geocoding.

**Reason:** the new outcome and unit of analysis are intra-municipal travel-time accessibility; municipal indicators and representative points are not valid substitutes for routable origins, destinations, and networks.

**Next action:** construct and validate 2022 census-sector origins with female population before building the multimodal routing graph.

## 2026-08-17 — IBGE sector population rules

**Decision:** use `V01008` directly as the female-population weight and dissolve multipart geometries by `CD_SETOR`.

**Missingness:** assign zero only to geometry sectors absent from the demographic file when official basic population `v0001` is zero. Preserve all other unavailable female values; do not infer them from total minus male population.

**Reason:** age-group cells are incomplete for some sectors, and missing sex values may reflect confidentiality or special-sector treatment rather than zero population.

**Consequence:** sector coverage and female-population coverage will be reported separately in every subsequent analysis.
