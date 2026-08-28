# Integrated synthesis — E2SFCA × PROMETHEE II × SOM

This directory contains the publication-oriented integration of three already frozen analytical blocks. It does **not** create a new ranking, alter PROMETHEE-II weights, retrain the SOM, or redefine E2SFCA.

## Analytical roles

- **E2SFCA** describes potential service accessibility under the registered 120-minute reference configuration, separately for CREAS, health, specialized justice and specialized security.
- **PROMETHEE II** provides the frozen multicriteria municipal prioritization.
- **SOM** provides four neutral socioeconomic-demographic municipal macroprofiles (P1–P4).

The integration is descriptive triangulation. Associations are not interpreted as causal effects of demographic composition.

## Coverage

- Municipalities in SOM/PROMETHEE: **144**.
- E2SFCA service types: **4**.
- Complete E2SFCA coverage across all four service types: **143 municipalities**.
- Incomplete E2SFCA coverage: **1 municipality (Afuá)**.
- Missing E2SFCA coverage is preserved and is never converted to synthetic zero.

## Main integrated pattern

| SOM profile | n | PROMETHEE median rank | PROMETHEE top-quartile share | Median cross-service E2SFCA percentile* | Top-priority + lower-E2SFCA count |
|---|---:|---:|---:|---:|---:|
| P1 | 30 | 118.0 | 10.0% | 0.551 | 1 |
| P2 | 33 | 89.0 | 15.2% | 0.552 | 1 |
| P3 | 53 | 56.0 | 26.4% | 0.520 | 4 |
| P4 | 28 | 36.5 | 50.0% | 0.357 | 10 |

\*The cross-service percentile is a descriptive synthesis aid calculated only for municipalities with complete E2SFCA coverage. It is **not** a new accessibility score or MCDM criterion.

P4 therefore combines the highest concentration of municipalities in the frozen PROMETHEE top quartile with the lowest median cross-service E2SFCA percentile among the four SOM profiles. This is an exploratory cross-method pattern and not evidence that the demographic characteristics defining P4 cause lower accessibility or higher prioritization.

## Service-specific E2SFCA pattern

The profile medians show that P4 has comparatively low E2SFCA percentiles for health, specialized justice and specialized security, while its CREAS percentile is comparatively high. This heterogeneity is important: a municipality or profile should not be described as uniformly inaccessible across all service types.

The service-specific Spearman associations between E2SFCA percentile and frozen PROMETHEE net flow are modest. The largest absolute association is for specialized security (rho ≈ -0.350, n=143), followed by health (rho ≈ -0.307) and specialized justice (rho ≈ -0.271). CREAS shows a weaker association in the opposite direction (rho ≈ +0.152). These correlations are descriptive because accessibility-related information is conceptually related to the MCDM model.

## Illustrative high-priority cases

Among the first ten PROMETHEE municipalities, several also lie in the lower quartile of the complete-case cross-service E2SFCA summary, including Senador José Porfírio, Santa Cruz do Arari, Trairão, Piçarra and Bagre. Other high-priority municipalities do not show the same E2SFCA pattern, reinforcing that PROMETHEE priority is multicriteria rather than a simple reproduction of E2SFCA.

Afuá is PROMETHEE rank 15 and belongs to P4, but its reference E2SFCA coverage remains unassessed. It is explicitly excluded from the complete-case cross-service E2SFCA summary rather than assigned zero accessibility.

## Main tables

- `tables/integrated_municipal_e2sfca_mcdm_som.csv` — municipality-level frozen-result join, raw E2SFCA scores and within-service percentiles.
- `tables/integrated_profile_summary.csv` — concise SOM-profile synthesis.
- `tables/som_profile_e2sfca_service_summary.csv` — E2SFCA by service and SOM profile.
- `tables/e2sfca_promethee_associations.csv` — service-specific descriptive correlations.
- `tables/integrated_top20_promethee_context.csv` — top-20 PROMETHEE municipalities with SOM and E2SFCA context.
- `tables/integrated_synthesis_audit.json` — methodological and coverage audit.

## Figures

- `figures/integrated_e2sfca_mcdm_som_panel.png` / `.pdf` — main integrated publication panel.
- `figures/integrated_som_e2sfca_profile_heatmap.png` / `.pdf` — service accessibility patterns across P1–P4.
- `figures/integrated_som_promethee_top_quartile.png` / `.pdf` — PROMETHEE top-quartile membership by SOM profile.
- `figures/integrated_e2sfca_promethee_som_scatter.png` / `.pdf` — municipal E2SFCA/PROMETHEE relationship stratified by SOM profile.

## Manuscript draft

`integrated_results_synthesis.md` contains a computed, manuscript-oriented results synthesis grounded in the frozen outputs.

## Reproducibility

Official workflow: `.github/workflows/integrated-e2sfca-mcdm-som-synthesis.yml`.

Validated entry point: `src/analysis/publish_integrated_e2sfca_mcdm_som_synthesis_validated.py`.
