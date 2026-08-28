# 08 — Reproducibility and publication status

This page is the authoritative human-readable register of which analytical components have been **executed and frozen**, which are **published for inspection**, and which remain **methodologically open**.

The purpose is to prevent executable code, diagnostic experiments and final analytical outputs from being confused with one another.

## Status classes

- **AUTHORITATIVE + PUBLISHED** — executed on the final/corrected inputs, validated, and represented by permanent tables/figures/documentation in the repository.
- **AUTHORITATIVE ARTIFACT** — executed and validated, but the complete machine-scale object is retained as a GitHub Actions artifact rather than duplicated in Git.
- **IMPLEMENTED / NOT YET AUTHORITATIVE** — executable model code exists, but no final parameterization/output has been frozen for interpretation.
- **PLANNED** — analysis has not yet been executed as a final study stage.

## Current analytical register

| Component | Status | Authoritative basis | Permanent public documentation |
|---|---|---|---|
| Data-source inventory and provenance | AUTHORITATIVE + PUBLISHED | Official-source acquisition/audit record | `docs/data_inventory.md`, `docs/methodology/01_data_sources.md` |
| Census-sector / populated-origin construction | AUTHORITATIVE + PUBLISHED | IBGE Census 2022 origin audits | `docs/ibge_census2022_sector_audit.md`, methodology pages |
| Service destinations / institutional inventory | AUTHORITATIVE + PUBLISHED | validated service inventories | `docs/methodology/01_data_sources.md`, Stage-3 tables |
| Multimodal temporal network | AUTHORITATIVE + PUBLISHED | corrected backbone used by run `33089335405` | `results/stage2_network/` |
| Full corrected origin–service OD matrix | AUTHORITATIVE ARTIFACT | run `33089335405`; 2,851,425 OD pairs | `results/stage2_od/` contains summaries/figures; full matrix retained as workflow artifact |
| E2SFCA complementary accessibility analysis | AUTHORITATIVE + PUBLISHED | corrected OD run `33089335405`; unit-presence reference plus four sensitivities | `results/e2sfca/`, `docs/methodology/04_accessibility_e2sfca.md` |
| Municipal network-access indicators | AUTHORITATIVE + PUBLISHED | corrected OD → Stage-3 municipal matrix | `results/stage3/`, `docs/methodology/05_municipal_indicators.md` |
| Institutional absence indicators | AUTHORITATIVE + PUBLISHED | validated 2026 institutional inventories | `results/stage3/` |
| Rural female share | AUTHORITATIVE + PUBLISHED | Census 2022 | `results/stage3/` |
| Statistical audit (missingness, redundancy, correlation, VIF, PCA decision) | AUTHORITATIVE + PUBLISHED | corrected Stage-3 run `33090126353` | `results/stage3/`, `docs/methodology/06_statistical_audit.md` |
| PROMETHEE II reference prioritization | AUTHORITATIVE + PUBLISHED | corrected Stage-4 run `33090126353` | `results/stage4/` |
| TOPSIS contrast ranking | AUTHORITATIVE + PUBLISHED | corrected Stage-4 run `33090126353` | `results/stage4/` |
| Weight robustness / rank acceptability | AUTHORITATIVE + PUBLISHED | 10,000 Dirichlet weight draws | Stage-4 documentation/results |
| Preference/scaling sensitivity | AUTHORITATIVE + PUBLISHED | validated sensitivity run | Stage-4 documentation/results |
| SOM socioeconomic/demographic profiling | PLANNED | not yet frozen | to be created after Stage 5 execution |

## Important E2SFCA status

The repository contains a complete two-step floating catchment implementation, including female-population demand weighting, service-type separation, optional catchment threshold, optional exponential/Gaussian decay, observed-capacity or unit-presence supply modes, and explicit preservation of zero-access origins.

The corrected E2SFCA execution is now authoritative as a **complementary** analysis. The frozen reference choices are:

1. `unit_presence` supply, separately by service type;
2. 120-minute reference catchment;
3. no additional reference decay parameter;
4. female-population-weighted municipal aggregation among routing-ready origins;
5. no synthetic zero for coverage-limited origins;
6. four explicitly labeled sensitivity/diagnostic configurations.

The published maps and tables are in `results/e2sfca/`. This result remains separate from the frozen direct-OD criteria used by the MCDM.

## Relationship between OD indicators and E2SFCA

The final MCDM does **not** derive its four network-access criteria from an E2SFCA score. The authoritative access criteria are direct summaries of the corrected OD surface:

- reachable-service fraction;
- fraction of services within 120 minutes;
- nearest reachable-service time;
- median reachable-service time.

E2SFCA is a complementary accessibility model that adds population competition and service supply to travel-time impedance. It can be reported as a separate accessibility analysis or used as a sensitivity/interpretive layer, but it must not be retroactively described as the source of the already-frozen MCDM criteria.

## Publication rule

Any newly closed method must receive, at minimum:

- a methodology page with equations/assumptions;
- exact source/run/artifact provenance;
- machine-readable output tables;
- summary/diagnostic tables;
- figures and maps when spatially meaningful;
- validation metadata;
- explicit statement of limitations and missingness;
- cartographic elements defined in `docs/methodology/README.md` for every final map.

This register must be updated whenever a component changes from **IMPLEMENTED / NOT YET AUTHORITATIVE** or **PLANNED** to an authoritative study output.
