# Stage 5 SOM data audit — acquisition and pre-training gate

## Status

**IN PROGRESS.** Stage 4 MCDM remains closed and authoritative. Stage 5 is restricted to socioeconomic and demographic profiling and does not feed new variables back into the MCDM ranking.

The current frozen Census 2022 sector artifact already supports female rurality and partial female age composition. It does **not** currently materialize municipal income, literacy/education, or race/color features. Those blocks must be acquired from official Census 2022 municipal dissemination and audited separately before SOM training.

The SOM data build must preserve the 144 Pará municipalities, explicit source/year metadata, and suppression/missingness without synthetic filling.

## Official-source resolution completed

### Race/color

Official source family: IBGE Census 2022 — Population by color or race, universe results.

- SIDRA table **9605**: `População residente, por cor ou raça, nos Censos Demográficos`.
- The official IBGE 2022 dissemination explicitly identifies SIDRA table 9605 among the color/race universe tables.
- Municipality is an available territorial level.
- This table is appropriate for a municipal **total-population composition** profile, but it does not by itself provide a female-only composition. Therefore, Stage 5 must not label 9605-derived shares as female race/color shares.

Initial SOM candidate representation from table 9605:

- share branca;
- share preta;
- share parda;
- share amarela;
- share indígena.

These shares are compositional and must not automatically all enter the SOM in raw form. The pre-SOM gate will compare raw-share representation against a reduced or compositional representation before the feature set is frozen.

### Literacy/education

Official source family: IBGE Census 2022 — Literacy, universe results.

The official Census 2022 literacy publication confirms municipal literacy/analfabetism indicators for persons aged 15 years or older. Exact SIDRA table and category identifiers still need to be locked from official metadata before automated acquisition. No proxy from another survey/year is authorized.

### Income/poverty

Official source family: IBGE Census 2022 — Trabalho e Rendimento, sample results.

SIDRA table **10295** is officially identified for 2022 municipal mean monthly household per-capita income. It is a viable income-profile candidate, subject to the following audit caveat: it comes from Census 2022 sample estimates (preliminary weighting-area dissemination in the cited release), not the universe results. It may therefore be retained as an audited profile variable only after coverage, definition and comparability checks; it must not be described as a direct poverty measure.

A separate poverty/deprivation variable will only be admitted if an explicit Census 2022 municipal definition is resolved. Low income and poverty are not treated as interchangeable concepts.

## Priority for acquisition

1. race/color composition — table 9605, municipality level, 2022;
2. literacy/education — exact Census 2022 universe SIDRA table/category selection to be locked;
3. income — table 10295 candidate, followed by explicit definition/coverage audit;
4. optional household-deprivation variables (water/sewer/refuse/internet) only as a later sensitivity/profile extension.

## Already materialized SOM candidates

From the frozen sector-level Census 2022 artifact:

- female 15–29 share among age-covered female population;
- female 30–59 share among age-covered female population;
- female 60+ share among age-covered female population;
- female rural share;
- age-population coverage fraction retained as a quality field, not a clustering feature.

## Pre-SOM quality gate

No SOM training is authorized until all candidate data pass:

1. 144-municipality key integrity;
2. source, year, denominator and variable-definition audit;
3. missingness, suppression and disclosure audit;
4. temporal compatibility review, with 2022 as the target demographic/socioeconomic baseline;
5. scale and outlier audit;
6. redundancy/correlation review;
7. explicit treatment of compositional variables, especially race/color and age shares;
8. explicit decision on whether sample-based income is retained;
9. standardization only after the final feature set is frozen.

## Interpretation guardrails

- Race/color composition, age, literacy and income are profile descriptors, not violence-risk scores.
- No racial group is treated as a normative reference or as intrinsically vulnerable/protective.
- Female-only labels are used only when the underlying source is actually sex-specific.
- The SOM will characterize municipal profiles; association with PROMETHEE II priority is examined only after unsupervised training.

## Immediate next action

Implement the reproducible municipal acquisition layer for table 9605 and its 144-municipality audit; resolve the exact literacy SIDRA identifiers; then add the 10295 income candidate and close the candidate-matrix quality gate before SOM training.
