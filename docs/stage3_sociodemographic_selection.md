# Stage 3 sociodemographic selection decision

## Purpose

This note records the restrained sociodemographic decision made before final MCDM specification. Demographic composition is not interpreted as a proxy for violence incidence, reporting propensity, or demand. Variables are retained only when they have a defensible analytical role and survive missingness/redundancy review.

## Census source and coverage

The frozen IBGE Census 2022 sector artifact contains 16,714 Pará census sectors covering all 144 municipalities. Observed female population totals 4,065,139. There are 486 sectors where female population is unavailable and 649 geometry-only zero-population sectors. No unavailable count is synthetically filled.

The 220 sectors with missing `SITUACAO` carry zero observed female population, so the observed rural female share can be aggregated without inventing an urban/rural class for populated sectors.

Female age-band information is less complete: 12,014 sectors have the required female age bands complete and 4,700 do not. Municipal coverage of observed female population by age-complete sectors ranges from 0.6123 to 1.0000 (median 0.9274; mean 0.9126). This uneven coverage precludes automatic promotion of age structure into the core MCDM matrix at this stage.

## Decisions

### Retain for final criterion-consolidation review

`criterion__rural_female_share`

Definition: observed female population in Census 2022 rural sectors divided by observed female population in the municipality.

Reason: rurality expresses territorial context that can constrain practical access and institutional reach, while remaining conceptually distinct from the municipal network-accessibility summaries.

Statistical audit with the eight pre-existing candidate criteria:

- available for all 144 municipalities;
- VIF = 1.4883;
- no Pearson or Spearman correlation reaches the 0.80 redundancy threshold;
- strongest Pearson association = 0.4478 with absence of specialized security;
- strongest Spearman association = 0.4256 with absence of specialized security;
- strongest absolute association with an accessibility criterion is 0.2769 (Spearman, nearest reachable service time);
- mean rural female share = 0.3752, median = 0.3900, range = 0.0027–0.7923.

Interpretation: rural female share is not a statistical duplicate of the current accessibility or institutional indicators. It remains a candidate, not yet an automatically weighted MCDM criterion.

### Retain for SOM / diagnostic sensitivity, not core MCDM

Female age structure among age-covered population:

- female 15–29 share;
- female 30–59 share;
- female 60+ share.

Reason: useful for descriptive/unsupervised pattern exploration, but municipal age coverage is uneven because suppressed/unavailable sector bands are not inferred. Age composition must not be treated as a direct VAW-risk score.

### Exclude from core MCDM criteria

Female population total.

Reason: population magnitude is already used as an aggregation/weighting support for accessibility. Adding it as an MCDM criterion would risk double counting municipal size/exposure.

### Deferred pending dedicated source/theory audit

Income, literacy/education, race/color/ethnicity and other socioeconomic variables.

Reason: they should not enter simply because official Census tables exist. Before inclusion, each needs an explicit construct, denominator, suppression/missingness rule, temporal compatibility assessment, ethical interpretation, and redundancy analysis against rurality/access/institutional indicators.

## Current candidate set after this decision

The statistical audit currently evaluates nine candidate criteria:

1. reachable service fraction;
2. services reachable within 120 minutes fraction;
3. nearest reachable service time;
4. median reachable service time;
5. absence of specialized health response;
6. absence of CREAS;
7. absence of specialized security;
8. absence of specialized justice;
9. rural female share.

Across these nine candidates, no pair exceeds the configured absolute correlation threshold of 0.80, no VIF reaches 5, maximum VIF is 3.3861, and PCA is not required.

## Remaining requirement before MCDM

The nine-variable set is statistically admissible under the configured diagnostics, but final MCDM readiness still requires conceptual indicator consolidation, criterion direction/scaling decisions, treatment of structural missing access values (Afuá versus true unreachable cases), explicit temporal-compatibility statement, and then selection of the MCDM method and weighting/robustness strategy.
