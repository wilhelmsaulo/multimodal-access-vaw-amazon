# Stage 4 MCDM specification

## Decision objective

Prioritize the 144 municipalities of Pará according to observed deficits in multimodal access, specialized response-system presence, and rural territorial exposure. The score is a prioritization-support construct; it is not an estimate of violence incidence, individual risk, reporting propensity, or causal effect.

## Primary and contrast methods

- Primary: PROMETHEE II.
- Contrast: TOPSIS on alternatives with complete transformed scores.
- Robustness: 10,000 weight draws from Dirichlet(1,...,1), fixed seed 20260827.

PROMETHEE II is used because the study requires a complete prioritization ordering while preserving pairwise preference logic and an explicit treatment of structural missingness. TOPSIS is retained as an independent contrast rather than a second co-primary ranking.

## Locked nine-criterion set

1. reachable service fraction;
2. services reachable within 120 minutes fraction;
3. nearest reachable service time;
4. median reachable service time;
5. absence of specialized health response;
6. absence of CREAS;
7. absence of specialized security;
8. absence of specialized justice;
9. rural female share.

Income/poverty, education, race/color/ethnicity and female age structure are reserved for SOM/profile analysis and are not part of the core MCDM.

## Direction and scaling

All transformed values are oriented so higher means greater prioritization need.

- Reachable-service fractions: `1 - observed fraction`.
- Finite travel times: min-max scaling among finite observed municipal times.
- Tested-unreachable travel-time state: ordered as worse than every finite observed time using normalized state 1; no synthetic number of minutes is created.
- Institutional absence criteria: identity binary deficit (1 = absence).
- Rural female share: identity proportion; interpreted as territorial exposure/context, not VAW risk.

PROMETHEE preference function: linear V-shape on the locked [0,1] priority-need scale, q=0 and p=1.

## Reference weights

Reference configuration uses equal criterion weights: 1/9 each.

This implies macro totals of:

- multimodal access: 4/9;
- institutional response: 4/9;
- rural territorial context: 1/9.

No subjective macro-weight vector is treated as truth. Weight uncertainty is evaluated explicitly in robustness analysis.

## Structural missingness

### Afuá

Afuá is a network-coverage limitation, not observed inaccessibility. Its unavailable access criteria remain NA. In PROMETHEE pairwise comparisons, unavailable criteria are excluded and weights are renormalized over mutually observed criteria. The resulting rank is always flagged as coverage-limited and cannot be interpreted as having the same evidential completeness as fully comparable municipalities. TOPSIS does not rank Afuá.

### Colares and Santa Cruz do Arari

Both municipalities have routing-ready origins and the full frozen service set was tested, with zero reachable pairs. Their observed reachability fractions remain zero. Travel-time summaries remain undefined in minutes; for MCDM ordering only, the tested-unreachable state is treated as worse than any finite observed travel time. This is an ordinal rule and does not impute a finite or infinite travel time.

## First successful execution

GitHub Actions run: `33071726376`.

Artifact: `stage4-mcdm-reference-and-robustness`.

Reference top positions:

1. Colares;
2. Santa Cruz do Arari;
3. Senador José Porfírio;
4. Santa Maria das Barreiras;
5. Bannach;
6. Trairão;
7. Bagre;
8. Piçarra;
9. Pau D'Arco;
10. Palestina do Pará.

Afuá is 16th in the reference PROMETHEE execution, but the rank is explicitly coverage-limited and based on partial criterion comparability; its mean pairwise comparable reference-weight fraction is approximately 0.556.

PROMETHEE II versus TOPSIS Spearman correlation among the 143 TOPSIS-comparable municipalities is approximately 0.9981.

## Weight robustness

10,000 Dirichlet weight draws were executed.

Spearman correlation of each draw against the equal-weight PROMETHEE reference ranking:

- median: 0.8945;
- 5th percentile: 0.7042;
- 95th percentile: 0.9710.

Selected top-10 probabilities:

- Colares: 0.9999;
- Senador José Porfírio: 0.9614;
- Santa Cruz do Arari: 0.9516;
- Bannach: 0.8787;
- Santa Maria das Barreiras: 0.8638;
- Trairão: 0.8156;
- Piçarra: 0.7475;
- Bagre: 0.7100.

The broad Dirichlet stress test intentionally permits highly uneven criterion weights. Therefore extreme best/worst ranks are sensitivity information rather than point-estimate uncertainty intervals.

## Interpretation gate

The current result is the locked Stage 4 reference execution, not yet the manuscript-final policy ranking. Before final manuscript interpretation, the next analysis should audit scale/preference-function sensitivity and summarize rank acceptability/stability, particularly for municipalities whose ranking is highly weight-sensitive and for Afuá's coverage-limited comparison.
