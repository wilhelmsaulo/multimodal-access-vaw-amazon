# Stage 3 sociodemographic selection decision

## Purpose

This note records the final sociodemographic decision made before MCDM specification. Demographic and socioeconomic composition is not interpreted as a proxy for violence incidence, reporting propensity, or demand. The MCDM is restricted to access, institutional response and territorial rurality; broader socioeconomic and demographic descriptors are reserved for SOM and subsequent profile interpretation.

## Census source and coverage

The frozen IBGE Census 2022 sector artifact contains 16,714 Pará census sectors covering all 144 municipalities. Observed female population totals 4,065,139. There are 486 sectors where female population is unavailable and 649 geometry-only zero-population sectors. No unavailable count is synthetically filled.

The 220 sectors with missing `SITUACAO` carry zero observed female population, so the observed rural female share can be aggregated without inventing an urban/rural class for populated sectors.

Female age-band information is less complete: 12,014 sectors have the required female age bands complete and 4,700 do not. Municipal coverage of observed female population by age-complete sectors ranges from 0.6123 to 1.0000 (median 0.9274; mean 0.9126). This uneven coverage precludes use of age structure as a core MCDM criterion.

## Final decisions

### Retain in MCDM candidate set

`criterion__rural_female_share`

Definition: observed female population in Census 2022 rural sectors divided by observed female population in the municipality.

Reason: rurality is treated here as a territorial condition directly related to the practical organization of access and institutional reach in the Amazonian context, rather than as a generic socioeconomic vulnerability score.

Statistical audit with the eight pre-existing candidate criteria:

- available for all 144 municipalities;
- VIF = 1.4883;
- no Pearson or Spearman correlation reaches the 0.80 redundancy threshold;
- strongest Pearson association = 0.4478 with absence of specialized security;
- strongest Spearman association = 0.4256 with absence of specialized security;
- strongest absolute association with an accessibility criterion is 0.2769 (Spearman, nearest reachable service time);
- mean rural female share = 0.3752, median = 0.3900, range = 0.0027–0.7923.

### Reserve for SOM / descriptive profiling, not MCDM

The following socioeconomic and demographic information will not directly determine municipal priority in the MCDM:

- income / poverty;
- education / literacy;
- race / color / ethnicity;
- female age structure;
- other socioeconomic composition variables that may be added later for profile characterization.

Rationale: these variables are analytically valuable for identifying and interpreting municipal profiles and structural inequalities, but using them directly as ranking criteria would introduce stronger normative assumptions, potential double counting of vulnerability, and in some cases ethically problematic interpretations. The SOM will be used to characterize patterns rather than to reproduce the MCDM ranking.

Female age structure among age-covered population remains available for SOM / diagnostic analysis:

- female 15–29 share;
- female 30–59 share;
- female 60+ share.

Age composition must not be interpreted as a direct VAW-risk score.

### Exclude from core MCDM criteria

Female population total.

Reason: population magnitude is already used as an aggregation/weighting support for accessibility. Adding it as an MCDM criterion would risk double counting municipal size/exposure.

## Final MCDM candidate set after Stage 3

The MCDM proceeds with nine candidate criteria:

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

## Stage 3 gate decision

The statistical and conceptual indicator-consolidation gate is closed. Broader socioeconomic/demographic descriptors are reserved for SOM. The next formal step is MCDM specification: criterion direction/scaling, explicit handling of structural missing access values, final temporal-compatibility statement, method comparison/selection, and weighting/robustness strategy.
