# Post-hoc statistical assessment of SOM profile associations

This block evaluates outcomes that were **not used to construct the SOM profiles**: the four service-specific E2SFCA accessibility outputs, frozen PROMETHEE-II outputs, and the robustness-derived probability of top-quartile membership.

It is an association analysis, not an independent inferential validation of the socioeconomic/demographic variables used to train the SOM.

## Primary inferential strategy

- global comparison across P1–P4: Kruskal–Wallis;
- familywise correction across the seven global outcome tests: Holm;
- effect size: epsilon-squared (ε²);
- pairwise follow-up: Dunn with Holm correction;
- categorical P1–P4 × PROMETHEE top-quartile membership: Pearson chi-square + Cramér's V;
- sensitivity only: Welch one-way ANOVA;
- heteroscedasticity diagnostic: Brown–Forsythe/Levene centered at the median.

Pairwise comparisons should be emphasized in the manuscript only for outcomes whose global test remains significant after the across-outcome Holm correction. CREAS and health have raw global p < 0.05 but adjusted p = 0.05943, so their pairwise contrasts are retained in the audit table as exploratory diagnostics rather than confirmatory results.

## Main results after global Holm correction

| Outcome | Kruskal–Wallis p (Holm) | ε² | Magnitude |
|---|---:|---:|---|
| E2SFCA specialized justice | 1.02e-06 | 0.228 | large |
| E2SFCA specialized security | 3.15e-05 | 0.167 | large |
| PROMETHEE-II net flow | 3.15e-05 | 0.170 | large |
| PROMETHEE-II rank | 3.15e-05 | 0.170 | large |
| Robust top-quartile probability | 2.48e-06 | 0.211 | large |
| E2SFCA CREAS | 0.05943 | 0.043 | small; not retained after Holm |
| E2SFCA health | 0.05943 | 0.038 | small; not retained after Holm |

The profile × PROMETHEE top-quartile contingency test is also significant: χ²(3)=14.697, p=0.002095, Cramér's V=0.319.

## Pairwise patterns to report

Among globally Holm-significant outcomes:

- **Specialized justice E2SFCA:** P1–P4, P2–P3, P2–P4 and P3–P4 differ after Dunn–Holm; P1–P2 narrowly does not (pHolm=0.0534).
- **Specialized security E2SFCA:** P1–P4, P2–P4 and P3–P4 differ after Dunn–Holm.
- **PROMETHEE-II net flow/rank:** P1–P3, P1–P4 and P2–P4 differ after Dunn–Holm.
- **Robust top-quartile probability:** P1–P3, P1–P4, P2–P3 and P2–P4 differ after Dunn–Holm.

These contrasts do **not** imply that P1–P4 form an ordinal risk scale. P1–P4 remain neutral SOM profile identifiers.

## Reproducible artifacts

### Tables
- `tables/posthoc_global_tests.csv`
- `tables/posthoc_dunn_holm.csv`
- `tables/posthoc_chi_square_top_quartile.csv`
- `tables/posthoc_top_quartile_contingency.csv`
- `tables/posthoc_group_descriptives.csv`
- `tables/posthoc_publication_summary.csv`
- `tables/posthoc_statistics_audit.json`

### Figure
- `figures/posthoc_global_tests_effects.png`
- `figures/posthoc_global_tests_effects.pdf`

### Manuscript-oriented text
- `posthoc_statistical_results.md`

### Code/workflow
- `src/analysis/publish_posthoc_som_association_statistics.py`
- `.github/workflows/posthoc-som-association-statistics.yml`

## Interpretation constraints

- Statistical significance is interpreted together with effect size.
- E2SFCA missingness is not converted to zero; Afuá remains missing where E2SFCA coverage is unavailable.
- The SOM is not retrained, PROMETHEE is not reranked, and E2SFCA is not recomputed.
- The rural female share overlaps conceptually between SOM and MCDM; therefore PROMETHEE associations are not described as fully independent of every SOM input.
