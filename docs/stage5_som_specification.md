# Stage 5 — SOM socioeconomic and demographic profiling

## Status

**STARTED — PRE-TRAINING DATA BUILD IN PROGRESS.** Stage 4 MCDM is closed on the corrected multimodal network and corrected Stage-3 matrix. Stage 5 has a separate profiling objective: characterize municipal socioeconomic/demographic profiles without feeding those variables back into the MCDM ranking.

## Analytical separation locked

- MCDM answers: which Pará municipalities present higher priority need/burden under accessibility, institutional availability and rural female territorial context.
- SOM answers: which socioeconomic and demographic municipal profiles co-occur with those priority patterns.
- Income/poverty, education, race/color and female age structure are **not** retroactively added to MCDM.
- Female population total remains an aggregation/support quantity rather than a SOM feature by default, to avoid making municipality size dominate profile geometry.

## Candidate SOM feature blocks

### Already materialized from frozen Census 2022 sector data

1. Female age structure on age-covered sectors:
   - female 15–29 share;
   - female 30–59 share;
   - female 60+ share;
   - female age-population coverage fraction retained as a quality field, not a clustering feature.
2. Female rural share may be used for SOM profiling, even though it is also a locked MCDM territorial criterion; interpretation must acknowledge this overlap.

### Additional official municipal data

1. **Race/color composition — acquisition starting.** IBGE Census 2022 universe results, SIDRA table 9605. Table 9605 supports municipal total-population composition by color/race. It must not be described as female-specific unless a sex-disaggregated official table is separately resolved. Candidate categories are branca, preta, parda, amarela and indígena.
2. **Literacy/education — official female-specific route confirmed, exact identifiers pending.** The Census 2022 literacy universe dissemination is available at municipality level and is disaggregated by sex, age group and color/race for persons aged 15 years or older. The preferred candidate is therefore female literacy/illiteracy among women aged 15+, provided the exact SIDRA categories can be resolved reproducibly.
3. **Income — candidate identified.** SIDRA table 10295 provides 2022 municipal mean monthly household per-capita income in the Census Trabalho e Rendimento dissemination. Because it is sample-estimated rather than a universe indicator, it requires an explicit coverage/definition audit before inclusion.
4. **Poverty/deprivation — not synonymous with income.** A poverty/deprivation feature will only be included if an explicit Census 2022 municipal definition is identified and audited.
5. Optional household-deprivation variables (water/sewer/refuse/internet) may be audited only as a sensitivity/profile extension, not automatically included.

## Compositional-variable rule

Race/color and age shares are compositional. The final SOM must not mechanically include a full set of raw shares without checking the induced linear dependence and geometry. Before freezing features, compare:

- raw shares with one redundant component removed;
- reduced interpretable contrasts;
- an appropriate compositional transformation if it materially improves stability and interpretability.

No racial category is a normative reference; any omitted category in a reduced representation is a mathematical parameterization choice only.

## Pre-SOM quality gate

No SOM is trained until the candidate table passes:

1. 144-municipality key integrity;
2. variable-definition/provenance audit;
3. missingness and disclosure/suppression audit;
4. temporal compatibility review (target baseline: Census 2022 for socioeconomic/demographic variables);
5. scale/outlier audit;
6. redundancy/correlation review within the SOM feature set;
7. explicit decision on compositional representation;
8. explicit decision on retention of sample-based income;
9. standardization fitted only after the final feature set is frozen.

## SOM training plan after the gate

- Train multiple grid sizes and seeds rather than selecting one map visually.
- Evaluate quantization error and topographic error.
- Audit cluster stability / mapping stability across seeds and nearby grid sizes.
- Interpret component planes and municipal profiles; do not label clusters as violence-risk groups.
- Cross-tab SOM profiles against corrected PROMETHEE II priority ranks/top-quartile membership only **after** SOM training, preserving the exploratory/profile role.

## Immediate next action

Run the reproducible acquisition/audit of Census 2022 race/color composition for all 144 Pará municipalities, lock the female-literacy SIDRA categories, acquire/audit the income candidate, then construct and audit the complete Stage-5 candidate matrix before any neural-map training.
