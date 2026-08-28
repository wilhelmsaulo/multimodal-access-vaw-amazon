# Integrated E2SFCA–MCDM–SOM synthesis specification

## Purpose

This step is a publication-quality synthesis of already frozen analytical outputs. It is not a new model.

## Frozen inputs

1. Reference E2SFCA municipal scores under the registered 120-minute configuration, by service type.
2. Corrected frozen PROMETHEE-II Stage-4 ranking and net flows.
3. Frozen Stage-5 SOM macroprofile assignments P1–P4.

No upstream model is recalculated during integration.

## E2SFCA harmonization for visualization

Raw E2SFCA scores remain available and are never overwritten. Because the four service types have distinct score distributions, a within-service municipal percentile is calculated for visualization and cross-service descriptive comparison. A municipality-level mean of those percentiles is calculated **only when all four service types are observed**.

This mean percentile is not an E2SFCA replacement, not a new accessibility index and not a new MCDM criterion.

## Missingness rule

Missing E2SFCA coverage remains missing. No synthetic zero is permitted. In the current frozen integration, 143 municipalities have complete four-service E2SFCA coverage and Afuá remains incomplete.

## Descriptive cross-method pattern

For complete cases, the first and third quartiles of the mean within-service percentile are used only to identify lower/intermediate/higher E2SFCA accessibility patterns in figures and tables. These labels are descriptive bins and do not modify PROMETHEE or SOM classes.

A concordant descriptive case is defined as a municipality simultaneously in the frozen PROMETHEE top quartile and in the lower quartile of the complete-case cross-service E2SFCA percentile summary. This is not a new priority class.

## Interpretation constraints

- P1–P4 are neutral SOM profiles, not ordinal risk or vulnerability levels.
- Cross-profile E2SFCA differences do not imply demographic causation.
- PROMETHEE–E2SFCA associations are expected to be partly structurally related because accessibility information is conceptually present in the multicriteria framework.
- Rural female share appears in both SOM and MCDM and must be acknowledged when discussing cross-method association.
- Service-specific E2SFCA patterns should be reported individually; the cross-service percentile summary must never conceal heterogeneity between CREAS, health, justice and security.

## Reproducibility gate

The workflow validates:

- 144 municipality rows in the integrated SOM/PROMETHEE table;
- four SOM profiles;
- non-negative complete/incomplete E2SFCA coverage counts summing to 144;
- no synthetic E2SFCA zeros for missing coverage;
- no SOM retraining;
- no PROMETHEE reranking;
- no new integrated ranking.

The official reproducible outputs are indexed under `results/integrated_synthesis/README.md`.
