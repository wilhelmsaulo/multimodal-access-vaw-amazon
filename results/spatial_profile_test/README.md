# Categorical spatial pattern of Stage-5 SOM profiles

This directory contains the formal spatial test of the frozen Stage-5 SOM macroprofiles P1-P4.

## Why this is not Moran's I

P1-P4 are neutral nominal cluster identifiers. Their numeric labels do not encode an ordered or continuous scale. Therefore a numeric Moran's I calculated directly on values 1, 2, 3, and 4 would impose an artificial distance/order between categories and is not used.

Instead, the analysis uses the same official IBGE Municipal Digital Mesh 2022 for Para previously adopted in Stage 5 and constructs a **Queen-contiguity graph**. The fixed graph contains 144 municipalities, 384 undirected municipal-neighbor edges, and no islands.

## Inference

The null model randomly shuffles the frozen P1-P4 labels over the fixed municipal adjacency graph while preserving the observed group sizes exactly (P1=30, P2=33, P3=53, P4=28). A fixed seed (`20260828`) and 9,999 permutations are used.

Two global measures are evaluated:

1. **Same-profile neighbor share** - proportion of municipal adjacency edges whose two municipalities belong to the same SOM profile.
2. **Nominal assortativity** - Newman's categorical assortativity coefficient for the P1-P4 labels on the Queen graph.

Profile-specific same-profile join counts are also tested. Their four permutation p-values are corrected by Holm.

## Main results

### Global spatial organization

- Observed same-profile neighbor share: **0.5078**.
- Permutation expectation: **0.2639** (SD 0.0218).
- Standardized difference: **z = 11.21**.
- Permutation p-value: **p = 0.0001**.

Thus, just over half of all Queen-contiguity municipal edges connect municipalities belonging to the same SOM macroprofile, compared with approximately 26.4% expected under random spatial allocation of the observed profile labels.

Nominal assortativity is also positive and statistically strong:

- observed assortativity: **r = 0.3248**;
- permutation mean: **-0.0081** (SD 0.0292);
- standardized difference: **z = 11.40**;
- permutation p-value: **p = 0.0001**.

This supports a spatially assortative distribution of the independently constructed socioeconomic-demographic profiles. It does not imply that geographic proximity caused the profiles, because coordinates and adjacency were not SOM inputs.

### Profile-specific spatial enrichment

All four macroprofiles have significantly more same-profile neighbor edges than expected under random label allocation, even after Holm correction:

| Profile | Observed same-profile edges | Permutation mean | Enrichment ratio | Holm-adjusted p |
|---|---:|---:|---:|---:|
| P1 | 29 | 16.15 | 1.80 | 0.0034 |
| P2 | 57 | 19.80 | 2.88 | 0.0004 |
| P3 | 69 | 51.34 | 1.34 | 0.0034 |
| P4 | 40 | 14.04 | 2.85 | 0.0004 |

P2 and P4 show the strongest relative same-profile adjacency enrichment. P3 has the largest number of observed same-profile edges but also has the largest group size, so its enrichment ratio is lower. These statistics characterize spatial arrangement only and do not rank profiles by risk or vulnerability.

## Interpretation rule

The result supports the statement that **municipalities assigned to the same SOM socioeconomic-demographic profile tend to be geographically contiguous more often than expected under random allocation of the profile labels**.

It does **not** support causal statements such as geography generating the profile structure, nor does it introduce spatial coordinates into the already frozen SOM. Spatial testing occurs only after SOM training and macroprofile assignment.

## Reproducible artifacts

### Tables

- `tables/stage5_som_spatial_global_test.csv`
- `tables/stage5_som_spatial_profile_join_tests.csv`
- `tables/stage5_som_spatial_profile_adjacency_matrix.csv`
- `tables/stage5_som_spatial_queen_graph_municipalities.csv`
- `tables/stage5_som_spatial_profile_test_audit.json`

### Figures

- `figures/stage5_som_spatial_assortativity_permutation.png` / `.pdf`
- `figures/stage5_som_spatial_profile_join_enrichment.png` / `.pdf`

### Code and workflow

- `src/analysis/test_stage5_som_profile_spatial_pattern.py`
- `.github/workflows/stage5-som-spatial-profile-test.yml`

## Model integrity

This analysis does not retrain the SOM, change P1-P4 assignments, alter MCDM/PROMETHEE, or recompute E2SFCA. It is a post-training spatial characterization of frozen profile assignments.
