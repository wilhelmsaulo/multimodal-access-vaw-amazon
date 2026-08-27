# Stage 5 — SOM socioeconomic and demographic profiling

## Status

**STARTED.** Stage 4 MCDM is closed on the corrected multimodal network and corrected Stage-3 matrix. Stage 5 begins with a separate profiling objective: characterize municipal socioeconomic/demographic profiles without feeding those variables back into the MCDM ranking.

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

### Additional official municipal data to acquire/audit

1. Race/color composition — IBGE Census 2022 universe results. Official IBGE dissemination identifies SIDRA table 9605 among the 2022 race/color result tables.
2. Literacy/education — Census 2022 literacy universe results at municipality level; exact SIDRA table/variable selection must be resolved from official metadata before acquisition.
3. Income/poverty — use only a 2022 Census municipal indicator with explicit definition and municipality coverage. No substitution with a different survey/year merely to fill the block.
4. Optional household-deprivation variables (water/sewer/refuse/internet) may be audited only as a sensitivity/profile extension, not automatically included.

## Pre-SOM quality gate

No SOM is trained until the candidate table passes:

1. 144-municipality key integrity;
2. variable-definition/provenance audit;
3. missingness and disclosure/suppression audit;
4. temporal compatibility review (target baseline: Census 2022 for socioeconomic/demographic variables);
5. scale/outlier audit;
6. redundancy/correlation review within the SOM feature set;
7. explicit decision on whether highly compositional variables are represented as raw shares, reduced contrasts, or transformed features;
8. standardization fitted only after the final feature set is frozen.

## SOM training plan after the gate

- Train multiple grid sizes and seeds rather than selecting one map visually.
- Evaluate quantization error and topographic error.
- Audit cluster stability / mapping stability across seeds and nearby grid sizes.
- Interpret component planes and municipal profiles; do not label clusters as violence-risk groups.
- Cross-tab SOM profiles against corrected PROMETHEE II priority ranks/top-quartile membership only **after** SOM training, preserving the exploratory/profile role.

## Immediate next action

Resolve and acquire the official Census 2022 municipal socioeconomic tables (race/color, literacy/education, income/poverty), build the 144-municipality candidate SOM matrix, and run the pre-SOM quality gate before any neural-map training.
