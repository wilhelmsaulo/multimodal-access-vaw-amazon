# 06 — Statistical audit and criterion selection

## Objective

Before MCDM, the municipality-level candidate matrix is audited for missingness, redundancy, multicollinearity and the possible need for dimensionality reduction.

This stage is a diagnostic safeguard. Correlation, VIF or PCA are not used mechanically to remove variables; statistical flags are interpreted together with the conceptual role of each criterion.

## Corrected authoritative audit

The corrected Stage-3/Stage-4 recomputation is workflow run `33090126353`.

Final Stage-3 status:

- municipalities retained: **144**;
- final candidate criteria: **9**;
- maximum criterion missing fraction: **1/144**;
- redundant Pearson/Spearman pairs at threshold `|r| >= 0.80`: **0**;
- VIF indicators `>= 5`: **0**;
- maximum VIF: **3.282640463**;
- PCA: **not recommended** for the final criterion set.

## Redundancy logic

Pairwise Pearson and Spearman associations are examined to detect near-duplicate information. A threshold of 0.80 is treated as an audit flag rather than an automatic exclusion rule.

The final nine-criterion set contains no pair exceeding the declared redundancy threshold.

## VIF logic

Variance inflation factors are used to assess multicollinearity in the candidate matrix. A VIF threshold of 5 is treated as a practical warning threshold.

No final criterion reaches that threshold. The final maximum VIF is approximately 3.283.

## PCA decision

PCA is considered only if the candidate structure shows sufficient redundancy or dimensional compression need. Because the final criteria remain conceptually distinct and pass the correlation/VIF audit, PCA is not recommended as a replacement for the interpretable criterion set.

PCA may still be used as a diagnostic/sensitivity tool in future exploratory work, but not as an undocumented substitution for the core MCDM criteria.

## Sociodemographic selection decision

Rural female share remains in MCDM as a territorial context criterion after statistical and conceptual review.

Income/poverty, schooling, race/color and female age structure remain outside the core MCDM and are reserved for SOM/profile analysis. This separation is methodological, not a consequence of data convenience alone.

## Special missingness case

Afuá retains reduced evidence completeness because the locked network scope does not provide defensible access-time criteria. Pairwise PROMETHEE comparison can preserve the municipality without inventing values, while TOPSIS is restricted to the 143 complete alternatives.

## Core implementation

- `src/analysis/stage3_statistical_audit.py`
- `.github/workflows/stage3-statistical-audit.yml`
- `.github/workflows/recompute-stage3-stage4-after-network-fix.yml`

Detailed supporting documents:

- [`docs/stage3_indicator_consolidation.md`](../stage3_indicator_consolidation.md)
- [`docs/stage3_sociodemographic_selection.md`](../stage3_sociodemographic_selection.md)

## Required published artifacts

The documentation bundle should expose:

- missingness summary table;
- Pearson correlation matrix;
- Spearman correlation matrix;
- VIF table;
- criterion distribution plots;
- PCA diagnostic summary, explicitly marked as not selected for the reference model;
- a final criterion-selection table documenting retain/exclude/defer decisions.

Figures should have self-contained titles, legends where needed, source/reference information and enough annotation to be interpretable outside the code context.
