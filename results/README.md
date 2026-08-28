# Results

This directory contains the permanent, human-readable publication bundles generated from validated analytical artifacts. Final analytical outputs should be regenerated from code and documented inputs rather than edited manually.

## Navigation

### Stage 2 — corrected multimodal network

[`stage2_network/`](stage2_network/)

Contains:
- statewide corrected multimodal-network map;
- detailed Colares transfer-correction map;
- detailed Belém–Santa Cruz do Arari correction map;
- network-component summary;
- validated transfer-terminal table;
- bounded correction table;
- cartographic node-validation table;
- provenance and reconstruction safeguards.

### Stage 2 — corrected OD matrix documentation

[`stage2_od/`](stage2_od/)

Contains permanent summaries and visualizations of the authoritative corrected origin–service OD matrix. The complete 2,851,425-pair matrix remains in its workflow artifact instead of being duplicated in Git.

### Stage 3 — municipal analytical matrix and statistical audit

[`stage3/`](stage3/)

Contains:
- complete municipal analytical matrix;
- completeness/missingness diagnostics;
- Pearson and Spearman correlation matrices;
- VIF diagnostics;
- criterion distributions;
- maps for the nine final MCDM criteria;
- special-municipality audit outputs.

### Stage 4 — MCDM rankings and robustness

[`stage4/`](stage4/)

Contains:
- complete PROMETHEE II ranking;
- complete TOPSIS contrast ranking;
- final statewide rank maps;
- publication metadata and links to robustness/sensitivity documentation.

## E2SFCA

The E2SFCA implementation and mathematical model are documented in [`../docs/methodology/04_accessibility_e2sfca.md`](../docs/methodology/04_accessibility_e2sfca.md).

At present there is **no final corrected E2SFCA execution declared authoritative**, so this directory intentionally does not contain an empirical E2SFCA result bundle yet. This prevents a non-frozen supply/threshold/decay specification from being mistaken for a final study result.

The execution/publication status of every analytical component is tracked in [`../docs/methodology/08_reproducibility_status.md`](../docs/methodology/08_reproducibility_status.md).

## Cartographic standard

All final maps must include title, legend, cartographic scale, north/orientation, geographic latitude/longitude coordinates, source/year and coordinate-reference information. The current Pará statewide standard uses SIRGAS 2000 / Brazil Polyconic (EPSG:5880) for metric rendering/scale and SIRGAS 2000 geographic (EPSG:4674) for coordinate labels/graticule.
