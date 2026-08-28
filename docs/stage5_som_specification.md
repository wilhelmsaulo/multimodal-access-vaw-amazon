# Stage 5 — SOM socioeconomic and demographic profiling

## Status

**COMPLETED THROUGH DATA AUDIT, SOM TRAINING, PROFILE INTERPRETATION, SPATIALIZATION AND POST-HOC MCDM CROSS-TAB.** Stage 4 MCDM remains closed and unchanged. Stage 5 characterizes socioeconomic/demographic municipal profiles and examines their exploratory association with the frozen priority results.

## Analytical separation locked

- MCDM answers which Pará municipalities present higher priority need/burden under accessibility, institutional availability and rural female territorial context.
- SOM answers which socioeconomic and demographic municipal profiles co-occur across the 144 municipalities.
- Income, literacy, race/color and female age structure were **not** added retroactively to MCDM.
- PROMETHEE-II results were joined only after SOM training/profile construction; there is no feedback from SOM into ranking.

## Final official data blocks

1. **Female rural share** — retained from the frozen Stage-3 municipal analytical matrix. Its overlap with MCDM is explicit and interpretive only.
2. **Female literacy (15+)** — IBGE Census 2022, SIDRA table 9543, municipality level; 144/144 municipalities and zero missing cells.
3. **Household per-capita mean income** — IBGE Census 2022, SIDRA table 10295, municipality level; 144/144 and zero missing cells. This is a sample-based mean-income estimate and is **not** called poverty.
4. **Female age structure** — IBGE Census 2022 universe, SIDRA table 9514, municipality level, women. The earlier partial sector-derived age candidates were replaced for SOM by complete municipal data. Training composition: under 15 (derived residual), 15–29, 30–59 and 60+.
5. **Female race/color composition** — IBGE Census 2022 universe, SIDRA table 9606, municipality level, women/all ages. Categories: branca, preta, parda, amarela and indígena. The earlier total-population table 9605 is retained only as an audit artifact and is not a final SOM input.

## Compositional representation

Raw complete share vectors are not fed mechanically into the SOM.

### Female age

The three published candidate shares (15–29, 30–59, 60+) are completed with the female under-15 residual:

`under15 = 1 - (share15_29 + share30_59 + share60_plus)`

The resulting four-part composition is represented by three orthonormal sequential ILR coordinates.

### Female race/color

The five female race/color parts are represented by four orthonormal sequential ILR coordinates. Eight raw zero count cells occur across amarela/indígena. For the log-ratio transformation only, a Jeffreys additive pseudo-count of 0.5 is applied before closure. Raw observed counts/shares remain unchanged in the acquisition audit. No racial category is a normative reference and the ILR coordinate signs/orders are mathematical parameterization choices only.

## Final feature matrix and gate

The frozen SOM matrix contains 10 standardized dimensions:

- female rural share;
- female literacy rate 15+;
- mean household per-capita income;
- 3 female-age ILR coordinates;
- 4 female-race/color ILR coordinates.

Quality-gate results:

- municipalities: 144;
- missing final cells: 0;
- maximum absolute Pearson correlation: 0.76735;
- maximum absolute Spearman correlation: 0.76363;
- pairs with |r| >= 0.80: 0;
- maximum VIF: 7.21375;
- standardization: z-score fitted once on the frozen 144-municipality matrix;
- SOM training: **authorized**.

## SOM training and model selection

Thirty SOM models were trained:

- grids: 5×5, 6×6, 7×7;
- seeds: 10 per grid;
- 6,000 iterations per model.

Selection was not visual. Candidate grids were compared using equal-weight normalized criteria:

1. median quantization error;
2. median topographic error;
3. median mapping instability across seeds.

Mapping stability is the Spearman agreement of all pairwise municipal BMU distances across seeds, normalized by the grid diagonal, which is invariant to rotations/reflections of equivalent maps.

### Selected SOM

- grid: **5×5**;
- representative seed: **5**;
- seed quantization error: **1.69219**;
- seed topographic error: **0.00000**;
- seed mapping stability: **0.88321**;
- median 5×5 mapping stability across seeds: **0.85668**.

## Macroprofile construction

The selected 25-node codebook was partitioned with k-means candidates k=2..6. A solution is preferred when every macroprofile contains at least 8 municipalities, and the eligible solution with the highest codebook silhouette is selected.

Selected solution:

- **4 macroprofiles**;
- silhouette: **0.36398**;
- sizes: P1=30, P2=33, P3=53, P4=28 municipalities.

P1–P4 are neutral mathematical identifiers and are **not ordinal risk classes**.

## Interpretable profile signatures

Profile signatures are calculated after training from the original 11 interpretable municipal variables. For each profile, mean values are standardized relative to the complete Pará municipal distribution. The three largest positive and negative standardized differences are retained as concise descriptors.

- **P1:** distinctly lower rural female share; higher household per-capita income, female branca share and female 30–59 share.
- **P2:** higher female 60+ and parda shares; lower female preta and 15–29 shares.
- **P3:** higher female preta share and moderately higher rural female share; most other dimensions remain comparatively intermediate.
- **P4:** higher female 15–29 and rural shares; lower household per-capita income and lower female 30–59 and 60+ shares.

These signatures are descriptive. They are not causal interpretations, vulnerability scores or violence-risk labels.

## Representative and extreme municipalities

To avoid selecting case examples visually, municipalities are ranked within each profile by Euclidean distance to the corresponding profile centroid in the globally standardized 11-variable interpretable space.

The three nearest municipalities are used as representative cases:

- P1: Xinguara, Paragominas, Tucuruí;
- P2: Primavera, São Francisco do Pará, São Caetano de Odivelas;
- P3: Breu Branco, Eldorado do Carajás, Itupiranga;
- P4: Ipixuna do Pará, Curralinho, Breves.

The three farthest municipalities per profile are retained as within-profile heterogeneity diagnostics. They are not automatically classified as statistical outliers.

## Spatialization

The frozen P1–P4 assignments are joined to the official **IBGE Malha Municipal Digital 2022 — Pará**. The spatial gate requires exactly 144 unique municipal polygons and 144 profile assignments before map publication.

Spatialization is descriptive and does not add geographic proximity to the SOM objective after the fact. In other words, neighboring municipalities may or may not share a profile because the SOM was trained on socioeconomic/demographic characteristics, not spatial coordinates.

## Post-hoc association with frozen PROMETHEE II

Only after SOM profile construction were the profiles joined to the corrected Stage-4 PROMETHEE-II outputs. The exploratory top-quartile shares are:

- P1: 10.0%;
- P2: 15.15%;
- P3: 26.42%;
- P4: 50.0%.

This pattern is an exploratory association between socioeconomic/demographic profiles and the independently frozen MCDM prioritization. It is not a causal claim and does not redefine the MCDM ranking.

## Principal reproducible outputs

### Gate and model
- `results/stage5/tables/stage5_final_feature_gate.json`
- `results/stage5/tables/stage5_som_final_standardized_matrix.csv`
- `results/stage5/tables/stage5_som_training_audit.json`
- `results/stage5/tables/stage5_som_selected_mapping.csv`

### Profile interpretation
- `results/stage5/tables/stage5_som_interpretation_audit.json`
- `results/stage5/tables/stage5_som_profile_characteristics.csv`
- `results/stage5/tables/stage5_som_profile_signatures.csv`
- `results/stage5/tables/stage5_som_profile_representative_extreme_municipalities.csv`
- `results/stage5/tables/stage5_som_profile_promethee_summary.csv`
- `results/stage5/tables/stage5_spatial_interpretation_audit.json`

### Figures
- `results/stage5/figures/stage5_som_component_planes.png`
- `results/stage5/figures/stage5_som_profile_map.png`
- `results/stage5/figures/stage5_som_profiles_pará_map.png`
- `results/stage5/figures/stage5_som_profile_characteristics_heatmap.png`
- `results/stage5/figures/stage5_som_mcdm_profile_association.png`
- `results/stage5/figures/stage5_final_som_interpretation_panel.png`
- PDF equivalents are published for the spatial/profile figures and final panel.

## Stage-5 closure

Stage 5 modeling and first-order interpretation are now closed. Any subsequent work should be treated as manuscript synthesis, sensitivity extension or focused case-study analysis. New variables must not be inserted into the already frozen SOM without reopening the Stage-5 feature gate and retraining the model from the beginning.
