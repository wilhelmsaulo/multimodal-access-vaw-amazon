# Post-hoc statistical assessment of SOM profile associations
The tests in this section are applied to outcomes that were not used to construct the SOM profiles: E2SFCA service-specific accessibility, frozen PROMETHEE-II outputs, and the robustness-derived probability of top-quartile membership. They do not provide an independent inferential validation of the socioeconomic/demographic variables used to train the SOM.
Kruskal–Wallis is the primary global test because the groups are unequal in size and several outcomes are bounded, ranked, zero-inflated, or asymmetric. Dunn pairwise comparisons are performed only after a significant global result and are Holm-adjusted. Epsilon-squared (ε²) is reported as the rank-based effect size. Welch one-way ANOVA is retained only as a sensitivity analysis.
## Global tests
- **E2SFCA CREAS percentile:** H(3)=8.968, p=0.02972, Holm(global)=0.05943, ε²=0.043 (small); Welch sensitivity p=0.03192.
- **E2SFCA health percentile:** H(3)=8.256, p=0.041, Holm(global)=0.05943, ε²=0.038 (small); Welch sensitivity p=0.09044.
- **E2SFCA specialized justice percentile:** H(3)=34.642, p=1.45e-07, Holm(global)=1.015e-06, ε²=0.228 (large); Welch sensitivity p=2.621e-16.
- **E2SFCA specialized security percentile:** H(3)=26.277, p=8.343e-06, Holm(global)=3.153e-05, ε²=0.167 (large); Welch sensitivity p=2.095e-05.
- **PROMETHEE-II net flow:** H(3)=26.858, p=6.305e-06, Holm(global)=3.153e-05, ε²=0.170 (large); Welch sensitivity p=2.134e-05.
- **PROMETHEE-II rank:** H(3)=26.858, p=6.305e-06, Holm(global)=3.153e-05, ε²=0.170 (large); Welch sensitivity p=1.291e-05.
- **Robust top-quartile probability:** H(3)=32.482, p=4.141e-07, Holm(global)=2.485e-06, ε²=0.211 (large); Welch sensitivity p=2.59e-05.

For SOM profile × PROMETHEE top-quartile membership, χ²(3)=14.697, p=0.002095, Cramér's V=0.319.

## Pairwise Dunn–Holm results
- **E2SFCA CREAS percentile:** P1–P4 (pHolm=0.02827).
- **E2SFCA health percentile:** P2–P4 (pHolm=0.03508).
- **E2SFCA specialized justice percentile:** P1–P4 (pHolm=0.001801), P2–P3 (pHolm=0.001801), P2–P4 (pHolm=3.95e-08), P3–P4 (pHolm=0.006794).
- **E2SFCA specialized security percentile:** P1–P4 (pHolm=3.157e-06), P2–P4 (pHolm=0.01117), P3–P4 (pHolm=0.0006978).
- **PROMETHEE-II net flow:** P1–P3 (pHolm=0.0003829), P1–P4 (pHolm=2.016e-05), P2–P4 (pHolm=0.007696).
- **PROMETHEE-II rank:** P1–P3 (pHolm=0.0003829), P1–P4 (pHolm=2.016e-05), P2–P4 (pHolm=0.007696).
- **Robust top-quartile probability:** P1–P3 (pHolm=0.003936), P1–P4 (pHolm=0.0004735), P2–P3 (pHolm=0.0001628), P2–P4 (pHolm=1.85e-05).

## Interpretation guardrails
- Statistical differences between P1–P4 do not make the profile IDs ordinal risk levels.
- P-values are interpreted together with ε² or Cramér's V.
- The rural female share is shared conceptually between SOM and MCDM, so PROMETHEE associations are not treated as fully independent of every SOM input.
- E2SFCA missingness is preserved; Afuá is excluded only from tests requiring an observed E2SFCA value and never receives a synthetic zero.
- These analyses are post-hoc association tests and do not alter SOM training, MCDM weights/ranking, or E2SFCA outputs.
