# 07 — MCDM, robustness and Stage-4 results

## Objective

The MCDM stage prioritizes municipalities according to the final nine-criterion matrix while preserving uncertainty and model sensitivity. PROMETHEE II is the primary method; TOPSIS is an independent contrast.

## Criteria and direction

The model represents **priority need/burden**. Lower accessibility and greater institutional/territorial burden increase priority.

Final criteria:

1. reachable-service fraction;
2. services within 120 min fraction;
3. nearest reachable-service time;
4. median reachable-service time;
5. specialized health absence;
6. CREAS absence;
7. specialized security absence;
8. specialized justice absence;
9. rural female share.

Before MCDM, all criteria are transformed to a common priority-need direction and normalized according to the declared specification.

## Reference weights

The transparent reference configuration uses equal criterion weights:

`w_j = 1/9`

This is a neutral reference, not a claim that substantive importance is known exactly. Under equal criterion weights, accessibility contributes 4/9, institutional/service deficits 4/9 and rurality 1/9.

## PROMETHEE II

PROMETHEE II is the primary outranking method. The reference preference specification uses a linear V-shape with `q = 0` and `p = 1` after need scaling.

The net flow is used as the reference priority score. Higher net flow corresponds to higher modeled priority need.

The corrected reference ranking begins:

1. Senador José Porfírio
2. Santa Cruz do Arari
3. Santa Maria das Barreiras
4. Bannach
5. Trairão
6. Piçarra
7. Pau D'Arco
8. Bagre
9. Palestina do Pará
10. Sapucaia
11. Colares

The complete authoritative table is published at:

[`results/stage4/tables/promethee_ii_full_ranking.csv`](../../results/stage4/tables/promethee_ii_full_ranking.csv)

## TOPSIS contrast

TOPSIS is computed as an independent contrast on complete alternatives. Afuá is not assigned invented accessibility values merely to force completeness; therefore TOPSIS is interpreted on the 143 complete municipalities.

PROMETHEE II and TOPSIS have Spearman agreement of approximately **0.9984** over those 143 comparable municipalities.

The complete TOPSIS table is published at:

[`results/stage4/tables/topsis_full_ranking.csv`](../../results/stage4/tables/topsis_full_ranking.csv)

## Weight uncertainty

Weight robustness is assessed with **10,000 draws** from `Dirichlet(1,...,1)` over the nine criteria, seed `20260827`.

Agreement with the equal-weight PROMETHEE II reference across random weights is approximately:

- median Spearman: **0.8913**;
- 5th percentile: **0.6855**;
- 95th percentile: **0.9741**.

Rank acceptability/top-k probabilities are therefore more informative than treating the equal-weight rank as uniquely true.

## Preference/scaling sensitivity

A 12-scenario sensitivity audit combines:

- three scaling regimes: reference min-max, winsorized 5th/95th min-max and percentile/rank scaling;
- four PROMETHEE preference mappings: linear V-shape `p=1`, stronger V-shape `p=0.5`, strong V-shape `p=0.25`, and usual preference as a discontinuous stress test.

Across these scenarios relative to the locked reference:

- minimum Spearman: **0.8700**;
- median Spearman: **0.9176**;
- minimum top-10 overlap: **7/10**;
- minimum top-quartile overlap: **27/36**;
- maximum individual rank shift: **71** positions under the most aggressive stress specifications.

A stable high-priority core appears across all 12 scenarios: Senador José Porfírio, Bagre, Bannach, Santa Maria das Barreiras, Piçarra and Trairão remain in the top 10 in 100% of scenarios.

## Special interpretation cases

### Santa Cruz do Arari

It remains highly prioritized after network correction because of very long modeled travel times and institutional deficits, not because of artificial disconnection.

### Colares

Its invalid pre-correction first position is superseded. After restoring the documented ferry connection, Colares falls to 11th in the corrected PROMETHEE II reference.

### Afuá

Afuá is coverage/scope-limited. PROMETHEE II retains it using pairwise-comparable observed criteria while explicitly flagging reduced evidence completeness. It must not be interpreted as directly equivalent to complete alternatives solely by numerical rank.

## Public maps

### PROMETHEE II

![PROMETHEE II statewide rank](../../results/stage4/figures/promethee_ii_rank_map.png)

Vector version: [`promethee_ii_rank_map.svg`](../../results/stage4/figures/promethee_ii_rank_map.svg)

### TOPSIS

![TOPSIS statewide rank](../../results/stage4/figures/topsis_rank_map.png)

Vector version: [`topsis_rank_map.svg`](../../results/stage4/figures/topsis_rank_map.svg)

These maps are publication outputs and should follow the cartographic standard defined in the methodology index: **title, legend, scale, north/orientation and source/year**.

## Authoritative workflow runs

- corrected network/OD: `33089335405`;
- corrected Stage 3 / Stage 4 recomputation: `33090126353`;
- preference/scaling sensitivity: `33090728785`;
- validated corrected Stage-4 workflow path: `33090888653`;
- Stage-4 public-results publication: `33106412102`.

## Core implementation

- `src/analysis/stage4_mcdm.py`
- `.github/workflows/stage4-mcdm.yml`
- `.github/workflows/stage4-preference-scaling-sensitivity.yml`
- `src/analysis/publish_stage4_results.py`
- `.github/workflows/publish-stage4-results.yml`

Full technical specification:

[`docs/stage4_mcdm_specification.md`](../stage4_mcdm_specification.md)

## Interpretation for manuscript/reuse

The Stage-4 result should not be communicated as a deterministic claim that municipality rank 1 is intrinsically different from rank 2. The robust result is the combination of:

- reference PROMETHEE II rank;
- TOPSIS cross-method agreement;
- weight-driven rank acceptability;
- preference/scaling stability;
- explicit scope limitations.
