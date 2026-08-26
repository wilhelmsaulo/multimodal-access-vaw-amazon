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

## 2026-08-26 — Freeze the reference multimodal OD matrix and close operational Stage 2

**Decision:** freeze the definitive reference-network origin-destination matrix after a successful coherence audit and use it as the immutable routing input for the subsequent formal statistical and accessibility analyses.

**Validated scope:** 12,673 primary origins, 225 primary services, and 2,851,425 origin-service pairs. Of these, 1,536,775 pairs are reachable and 1,314,650 remain explicitly unreachable.

**Safeguards:** do not impute unreachable travel times; do not convert cartographic distance into travel time; do not fabricate flood/dry labels without validated impedance differences; exclude waiting time and ordinary-access air routing from the reference network; do not use zero-time connector edges or promote tracks/restricted roads into the primary routing regime.

**Audit outcome:** no duplicate OD pairs, negative network times, or unreachable rows containing travel times were found. The maximum travel-time arithmetic error was below `1e-6` minute. The closure workflow run was `32991298479`, and the permanent compact audit records are stored under `results/stage2_routing_closure/`.

**Consequence:** operational graph and OD construction are closed. Final E2SFCA results and the formal redundancy/correlation, PCA/ANOVA, stability, and scale/weight audit remain separate subsequent analyses.

## 2026-08-26 — Keep sociodemographic indicators outside E2SFCA

**Decision:** use female population as the E2SFCA demand term, but defer other sociodemographic indicators to the analytical table used by MCDM and SOM.

**Reason:** inserting income, race, schooling, rurality or composite vulnerability directly into E2SFCA would mix territorial accessibility with social vulnerability and change the estimand.

**Consequence:** after E2SFCA coverage and sensitivity are closed, and before MCDM/SOM, select a small theoretically justified sociodemographic block; audit temporal compatibility, missingness, correlation, VIF and conceptual redundancy before inclusion.

## 2026-08-26 — Do not equate unresolved origin attachment with true unreachability

**Decision:** classify the 3,070 non-routing-ready origins by recoverability evidence without modifying the frozen primary OD matrix.

**Reason:** many excluded origins have OSM topological signals but lack an empirically supported connector or defensible modal time. Treating them as truly unreachable, snapping them to the nearest network node, or assigning a speed silently would create different forms of territorial bias.

**Consequence:** primary E2SFCA remains gated. Connector sensitivity bounds will be constructed explicitly, beginning with municipalities below 50% female-population coverage. The primary OD remains immutable unless new connector evidence is separately documented and audited.

## 2026-08-26 — Existing terrestrial evidence cannot close riverine origin coverage

**Decision:** do not recover low-coverage municipalities by relaxing nearest-network attachment or by accepting `track` and `proposed` OSM paths.

**Evidence:** among 322 excluded origins in the ten municipalities below 50% female-population coverage, only six origins satisfy an optimistic screening requiring an observed local path, eligible `footway`/`path`/`service` semantics and the locked 173.996907 m proximity boundary. All six are in Afuá and represent 3,398 women; their inclusion would raise Afuá coverage only to 18.82%.

**Consequence:** the remaining problem is not primarily a terrestrial threshold problem. Primary E2SFCA remains gated while a coverage-aware uncertainty treatment or additional locally validated connector evidence is developed.

## 2026-08-26 — Separate E2SFCA parameter stability from connector uncertainty

**Decision:** execute the presence-based E2SFCA sensitivity grid but retain lower and upper municipal coverage envelopes instead of selecting a single municipal score.

**Evidence:** all six threshold/decay specifications conserve unit supply exactly and retain all 144 municipalities. However, only three municipalities have complete female-population routing coverage, 76 remain below 90%, and Afuá has no observed origin score. Relative envelope widths remain material across all four service categories.

**Consequence:** the six specifications are valid for sensitivity auditing, but no single E2SFCA point estimate is yet authorized as input to MCDM or SOM. Parameter agreement must not be described as resolving routing-coverage uncertainty.
