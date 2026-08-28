# Stage 5 — SOM validation and artifact index

Stage 5 is complete through data acquisition, compositional feature treatment, SOM training/model selection, macroprofile interpretation, spatialization, real neural-map diagnostics and post-hoc comparison with the frozen PROMETHEE-II results. Stage 4 MCDM remains unchanged.

## Validation checkpoints

1. **Female race/color acquisition** — `tables/stage5_female_race_color_audit.json`
   - IBGE Census 2022, SIDRA 9606, women/all ages;
   - 144 municipalities;
   - zero missing share cells.

2. **Final feature gate** — `tables/stage5_final_feature_gate.json`
   - 10 frozen SOM dimensions;
   - 144 municipalities, zero missing;
   - max |Pearson| = 0.76735;
   - max VIF = 7.21375;
   - training authorized.

3. **SOM training/model selection** — `tables/stage5_som_training_audit.json`
   - 30 models: 5×5, 6×6, 7×7 × 10 seeds;
   - selected 5×5, seed 5;
   - QE = 1.69219; topographic error = 0; mapping stability = 0.88321.

4. **Profile interpretation** — `tables/stage5_som_interpretation_audit.json`
   - selected 4 macroprofiles by codebook silhouette;
   - sizes P1=30, P2=33, P3=53, P4=28;
   - profile identifiers are neutral, non-ordinal.

5. **Post-hoc PROMETHEE association** — `tables/stage5_som_profile_promethee_summary.csv`
   - P1 top-quartile share: 10.0%;
   - P2: 15.15%;
   - P3: 26.42%;
   - P4: 50.0%;
   - comparison occurs only after profile construction and never feeds back into MCDM.

6. **Spatial interpretation audit** — `tables/stage5_spatial_interpretation_audit.json`
   - official IBGE Municipal Digital Mesh 2022;
   - 144/144 Pará municipal polygons validated;
   - representative and extreme municipalities selected by standardized distance to each profile centroid;
   - profile signatures derived from standardized differences from the Pará municipal mean;
   - spatial and SOM×MCDM figures published in PNG and PDF.

7. **Real SOM visual diagnostics** — `tables/stage5_som_real_visual_audit.json`
   - generated directly from the frozen selected 5×5 codebook, BMU counts and macroprofile assignments;
   - 25 neurons, 144 municipalities, 10 component planes;
   - U-Matrix = mean Euclidean codebook distance to valid Moore-neighborhood cells;
   - no model retraining, no profile reclassification and no MCDM feedback;
   - all plotted neural-map values are calculated from frozen SOM outputs, not illustrative graphics.

## Real SOM diagnostics

The publication-ready neural-map diagnostics are now separated from the earlier conceptual illustration. The real outputs are computed from `stage5_som_selected_codebook.csv`, `stage5_som_node_profiles.csv` and `stage5_som_municipal_profiles.csv`.

The U-Matrix shows the strongest local codebook separation around neuron row 3 / column 4 in 1-based display coordinates (raw index 2,3; mean neighbor distance 1.84217), while the lowest local separation occurs at raw index 4,4 (1.17321). BMU occupancy ranges from 1 to 11 municipalities per neuron and sums exactly to 144.

## Profile signatures

The profile labels P1–P4 remain neutral mathematical identifiers. The most distinguishing profile-average characteristics are stored in `tables/stage5_som_profile_signatures.csv`.

- **P1:** lower rural female share; higher household per-capita income, higher female branca share and higher female 30–59 share.
- **P2:** higher female 60+ and parda shares, with lower female preta and 15–29 shares.
- **P3:** higher female preta share and moderately higher rural female share; otherwise comparatively intermediate characteristics.
- **P4:** higher female 15–29 and rural shares and lower household per-capita income, female 30–59 and 60+ shares.

These are descriptive profile signatures, not violence-risk labels and not causal interpretations.

## Representative and extreme municipalities

`tables/stage5_som_profile_representative_extreme_municipalities.csv` contains three municipalities nearest to and three farthest from each profile centroid in the globally standardized 11-variable interpretable space.

Representative municipalities:

- P1: Xinguara, Paragominas, Tucuruí;
- P2: Primavera, São Francisco do Pará, São Caetano de Odivelas;
- P3: Breu Branco, Eldorado do Carajás, Itupiranga;
- P4: Ipixuna do Pará, Curralinho, Breves.

Extreme municipalities are retained for within-profile heterogeneity diagnostics; they are not labelled outliers automatically.

## Main tables

### Data and feature gate
- `tables/stage5_som_final_unstandardized_matrix.csv`
- `tables/stage5_som_final_standardized_matrix.csv`
- `tables/stage5_final_vif.csv`
- `tables/stage5_final_feature_gate.json`

### SOM training
- `tables/stage5_som_training_runs.csv`
- `tables/stage5_som_grid_selection.csv`
- `tables/stage5_som_selected_mapping.csv`
- `tables/stage5_som_selected_codebook.csv`
- `tables/stage5_som_training_audit.json`

### Interpretation and MCDM comparison
- `tables/stage5_som_profile_k_selection.csv`
- `tables/stage5_som_municipal_profiles.csv`
- `tables/stage5_som_profile_characteristics.csv`
- `tables/stage5_som_profile_standardized_characteristics.csv`
- `tables/stage5_som_profile_signatures.csv`
- `tables/stage5_som_profile_representative_extreme_municipalities.csv`
- `tables/stage5_som_profiles_with_promethee.csv`
- `tables/stage5_som_profile_promethee_summary.csv`
- `tables/stage5_som_promethee_top_quartile_crosstab.csv`
- `tables/stage5_spatial_interpretation_audit.json`

### Real neural-map diagnostics
- `tables/stage5_som_real_node_diagnostics.csv`
- `tables/stage5_som_real_visual_audit.json`

## Figures

### Real neural-map diagnostics
- `figures/stage5_som_real_umatrix.png` / `.pdf`
- `figures/stage5_som_real_hits.png` / `.pdf`
- `figures/stage5_som_real_macroprofiles.png` / `.pdf`
- `figures/stage5_som_real_component_planes.png` / `.pdf`
- `figures/stage5_som_real_diagnostic_panel.png` / `.pdf`

### Earlier neural/profile diagnostics
- `figures/stage5_som_component_planes.png`
- `figures/stage5_som_profile_map.png`

### Spatial/profile interpretation
- `figures/stage5_som_profiles_pará_map.png`
- `figures/stage5_som_profiles_para_map.pdf`
- `figures/stage5_som_profile_characteristics_heatmap.png`
- `figures/stage5_som_profile_characteristics_heatmap.pdf`
- `figures/stage5_som_mcdm_profile_association.png`
- `figures/stage5_som_mcdm_profile_association.pdf`

### Final publication panel
- `figures/stage5_final_som_interpretation_panel.png`
- `figures/stage5_final_som_interpretation_panel.pdf`

## Reproducibility entry points

- `src/analysis/build_stage5_final_som_features.py` — feature freeze/compositional treatment;
- `src/analysis/train_stage5_som.py` — multi-grid/multi-seed SOM training;
- `src/analysis/interpret_stage5_som.py` — macroprofile construction and post-hoc PROMETHEE cross-tab;
- `src/analysis/publish_stage5_spatial_interpretation.py` — representative/extreme municipalities, signatures and spatial artifacts;
- `src/analysis/publish_stage5_real_som_diagnostics.py` — real U-Matrix, BMU hits, macroprofile lattice and ten component planes;
- `src/analysis/publish_stage5_final_visual_panel.py` — consolidated spatial/profile publication panel.

For methodological details see `docs/stage5_som_specification.md`.
