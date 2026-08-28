# Stage 5 — SOM validation index

Stage 5 is complete through SOM training, macroprofile interpretation and post-hoc comparison with the frozen PROMETHEE-II results. Stage 4 MCDM remains unchanged.

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

## Main tables

- `tables/stage5_som_final_unstandardized_matrix.csv`
- `tables/stage5_som_final_standardized_matrix.csv`
- `tables/stage5_final_vif.csv`
- `tables/stage5_som_training_runs.csv`
- `tables/stage5_som_grid_selection.csv`
- `tables/stage5_som_selected_mapping.csv`
- `tables/stage5_som_selected_codebook.csv`
- `tables/stage5_som_profile_k_selection.csv`
- `tables/stage5_som_municipal_profiles.csv`
- `tables/stage5_som_profile_characteristics.csv`
- `tables/stage5_som_profile_standardized_characteristics.csv`
- `tables/stage5_som_profiles_with_promethee.csv`
- `tables/stage5_som_profile_promethee_summary.csv`

## Figures

- `figures/stage5_som_component_planes.png`
- `figures/stage5_som_profile_map.png`

For methodological details see `docs/stage5_som_specification.md`.
