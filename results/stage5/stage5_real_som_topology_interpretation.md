# Stage 5 — Real SOM topology interpretation

This note interprets the **frozen selected 5×5 SOM (seed 5)** using only its real codebook vectors, BMU topology and frozen P1–P4 macroprofile assignments. No model retraining, profile reclassification or MCDM feedback is performed.

## 1. What is being measured

Two neurons are considered neighbors when they share the Moore neighborhood on the rectangular 5×5 map (horizontal, vertical or diagonal adjacency). A **profile boundary** occurs when two adjacent neurons belong to different frozen macroprofiles. Boundary strength is the Euclidean distance between their 10-dimensional standardized codebook vectors.

This is a topological description of the SOM. Larger boundary distance means a sharper multivariate transition between adjacent prototypes; it does **not** mean greater violence, vulnerability or policy priority.

## 2. Observed macroprofile adjacency

Five cross-profile boundaries occur in the selected SOM topology:

| Profile pair | Boundary edges | Mean distance | Median | Minimum | Maximum |
|---|---:|---:|---:|---:|---:|
| P2–P4 | 5 | 1.8933 | 1.8450 | 1.4812 | 2.2029 |
| P1–P2 | 4 | 1.8304 | 1.7787 | 1.6012 | 2.1631 |
| P3–P4 | 7 | 1.7609 | 1.8344 | 1.4374 | 2.1389 |
| P2–P3 | 3 | 1.6606 | 1.4799 | 1.4181 | 2.0837 |
| P1–P3 | 6 | 1.5621 | 1.4144 | 0.9688 | 2.2675 |

**P1 and P4 are not directly adjacent.** In the selected two-dimensional SOM topology, transitions between these two macroprofiles occur through P2 and/or P3 rather than across a direct shared neural boundary. This is descriptive of the trained map geometry, not a causal sequence.

The sharpest average boundary is **P2–P4**, followed by **P1–P2**. The most gradual average cross-profile boundary is **P1–P3**, although individual P1–P3 edges remain heterogeneous and include the largest single edge distance among these pairs.

## 3. Which SOM dimensions distinguish each boundary

Feature contributions are measured as the mean absolute standardized codebook difference across all neural edges forming the corresponding profile boundary. They are descriptive decompositions and are not inferential effect sizes.

### P1–P2

The three strongest boundary contrasts are:

1. household per-capita income — 0.7632;
2. race/color ILR2 — 0.7564;
3. female literacy 15+ — 0.6684.

The raw profile summaries help translate the non-compositional dimensions: P1 has substantially higher mean household per-capita income and higher female literacy than P2. The race/color ILR coordinate is retained as a compositional balance; it should not be interpreted as a single race/color category without back-transformation.

### P1–P3

The three strongest contrasts are:

1. rural female share — 0.8070;
2. household per-capita income — 0.7044;
3. age ILR1 — 0.6020.

This boundary is therefore strongly territorial/socioeconomic in the real neural map. In the original interpretable profile summaries, P1 is less rural and has higher mean income than P3. The age ILR coordinate represents a balance among the complete female age composition and is not equivalent to one isolated age band.

### P2–P3

The three strongest contrasts are:

1. race/color ILR2 — 0.7472;
2. age ILR1 — 0.6674;
3. race/color ILR3 — 0.5835.

This transition is dominated by compositional structure rather than literacy or rurality. In the raw profile summaries, P2 has an older female age structure and lower female preta share than P3, but the ILR coordinates themselves remain multivariate balances.

### P2–P4

The three strongest contrasts are:

1. age ILR3 — 0.9051;
2. age ILR2 — 0.8984;
3. age ILR1 — 0.7325.

This is the clearest finding of the component-plane transition analysis: **the sharpest average macroprofile boundary in the SOM is predominantly an age-composition transition**. This is consistent with the original profile summaries: P2 has the highest mean female 60+ share, whereas P4 has the highest mean female 15–29 share and the lowest mean 60+ share.

### P3–P4

The three strongest contrasts are:

1. race/color ILR3 — 0.7565;
2. age ILR2 — 0.6617;
3. race/color ILR2 — 0.6124.

Thus the P3–P4 boundary is primarily compositional, combining race/color and female age-structure balances. Raw profile summaries show that P3 has the highest mean female preta share, while P4 has a younger female structure and greater mean parda/Indigenous representation. These raw differences are descriptive and must not be interpreted as causal drivers of violence or access priority.

## 4. Integrated reading of the SOM topology

The selected SOM does not arrange P1–P4 as a simple ordinal ladder. Instead, it forms a two-dimensional topology with multiple transition pathways:

- P1 connects directly to P2 and P3;
- P2 connects to P1, P3 and P4;
- P3 connects to P1, P2 and P4;
- P4 connects directly to P2 and P3, but not to P1.

This supports retaining the neutral P1–P4 identifiers rather than assigning ordinal labels. The map structure indicates that profile differentiation is multidimensional: income/literacy/rurality dominate some boundaries, whereas compositional age and race/color balances dominate others.

## 5. Relationship to the MCDM result

These topology diagnostics remain entirely inside the SOM interpretation layer. They do not modify PROMETHEE-II ranks, E2SFCA results, MCDM weights or the Stage-4 analytical matrix. The previously observed increase in PROMETHEE top-quartile membership from P1 to P4 remains a post-hoc association only. The absence of a direct P1–P4 neural boundary is further evidence that the SOM profiles should not be treated as an ordinal risk scale.

## 6. Reproducibility artifacts

Tables:

- `tables/stage5_som_real_topology_edges.csv`
- `tables/stage5_som_real_profile_transition_summary.csv`
- `tables/stage5_som_real_transition_feature_contributions.csv`
- `tables/stage5_som_real_profile_codebook_centroids.csv`
- `tables/stage5_som_real_topology_interpretation_audit.json`

Figures:

- `figures/stage5_som_real_profile_transition_matrix.png` / `.pdf`
- `figures/stage5_som_real_transition_feature_contributions.png` / `.pdf`

Code/workflow:

- `src/analysis/interpret_stage5_real_som_topology.py`
- `.github/workflows/stage5-real-som-topology-interpretation.yml`
