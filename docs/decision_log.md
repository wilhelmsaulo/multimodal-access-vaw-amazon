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

## 2026-08-28 — MCDM and SOM remain analytically separate

**Decision:** socioeconomic and demographic variables used for SOM profiling do not feed back into the closed Stage-4 MCDM ranking.

**Reason:** MCDM prioritizes municipalities under accessibility, institutional/service and territorial criteria, whereas SOM independently characterizes socioeconomic/demographic municipal profiles.

**Consequence:** any SOM–PROMETHEE comparison is post-hoc and descriptive only.

## 2026-08-28 — Female-specific municipal Census blocks for SOM

**Decision:** use female-specific municipal Census 2022 data whenever an official complete source exists: literacy from SIDRA 9543, age from SIDRA 9514, and race/color from SIDRA 9606. Use household per-capita mean income from SIDRA 10295 with its sample-based-estimate caveat.

**Reason:** these sources align the profile block more closely with the population of substantive interest and eliminate the incomplete coverage of the earlier sector-derived female age candidates.

**Consequence:** total-population race/color table 9605 and partial sector-age derivations remain audit artifacts, not final SOM inputs.

## 2026-08-28 — Compositional age and race/color are represented with ILR coordinates

**Decision:** do not feed complete raw compositional share vectors directly into the SOM. Use three orthonormal ILR coordinates for four-part female age composition and four orthonormal ILR coordinates for five-part female race/color composition.

**Zero rule:** for the race/color log-ratio transform only, replace observed zero counts by a Jeffreys additive pseudo-count of 0.5 before closure. Preserve raw observed counts/shares unchanged in source outputs.

**Reason:** raw complete compositions generate structural linear dependence and severe VIF inflation; ILR preserves compositional geometry without selecting a racial category as a normative reference.

**Consequence:** the final SOM feature gate contains 10 dimensions, zero missing cells, no pairwise |correlation| >= 0.80 and maximum VIF 7.21375.

## 2026-08-28 — SOM selection uses multi-grid, multi-seed diagnostics

**Decision:** train 30 candidate SOMs: grids 5×5, 6×6 and 7×7, with ten seeds each, and select using quantization error, topographic error and across-seed mapping stability rather than visual preference.

**Selected model:** 5×5, seed 5; quantization error 1.69219; topographic error 0; mapping stability 0.88321.

**Consequence:** the neural map is reproducibly selected and is not chosen by appearance.

## 2026-08-28 — Four neutral macroprofiles are retained

**Decision:** partition the selected 25-node SOM codebook using candidate k=2..6 solutions and retain k=4 based on the highest eligible codebook silhouette while requiring at least eight municipalities per profile.

**Selected solution:** P1=30, P2=33, P3=53, P4=28; silhouette 0.36398.

**Interpretation rule:** P1–P4 are neutral mathematical identifiers, not ordinal risk classes, vulnerability levels or violence-risk groups.

## 2026-08-28 — Representative cases and spatialization are post-training interpretation

**Decision:** identify three representative and three extreme municipalities per SOM profile by distance to the profile centroid in globally standardized 11-variable interpretable space. Spatialize the frozen profile assignments using the official IBGE Municipal Digital Mesh 2022 for Pará.

**Reason:** this avoids visually selecting case examples and prevents geographic location from being introduced into the neural training objective after the fact.

**Consequence:** the spatial publication gate requires 144 profile assignments and exactly 144 official municipal polygons. Extreme municipalities are treated as within-profile heterogeneity diagnostics, not automatically as statistical outliers.

## 2026-08-28 — Stage 5 is closed after spatial interpretation

**Decision:** close Stage 5 after data audit, final feature gate, neural training/model selection, macroprofile interpretation, spatialization and post-hoc PROMETHEE comparison.

**Consequence:** subsequent work is manuscript synthesis, sensitivity extension or focused case-study analysis. Any new SOM variable requires reopening the feature gate and retraining the SOM from the beginning.

## 2026-08-28 — Spatial testing of SOM profiles is categorical, not numeric Moran's I

**Decision:** test spatial organization of frozen P1–P4 assignments with a Queen-contiguity graph, global same-profile neighbor share, nominal assortativity and profile-specific join counts under label permutations. Do not compute Moran's I on numeric profile identifiers.

**Reason:** P1–P4 are nominal categories. Treating their numeric IDs as a continuous or ordered quantity would impose artificial distances between profiles.

**Implementation:** official IBGE Municipal Digital Mesh 2022 for Pará; 144 municipalities; 384 undirected Queen-neighbor edges; no islands; 9,999 fixed-graph permutations preserving the exact profile sizes; Holm correction across four profile-specific join-count tests.

**Result:** same-profile neighbor share = 0.5078 versus permutation mean 0.2639 (p=0.0001); nominal assortativity = 0.3248 versus permutation mean -0.0081 (p=0.0001). All four profiles show significant same-profile adjacency enrichment after Holm correction.

**Consequence:** the frozen socioeconomic-demographic profiles exhibit statistically supported spatial assortment, but geography remains post-training interpretation and was not an input to the SOM objective. No causal geographic interpretation is implied.
