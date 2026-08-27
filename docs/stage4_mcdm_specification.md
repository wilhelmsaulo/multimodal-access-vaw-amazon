# Stage 4 MCDM specification

## Status

**REVALIDATED / ready for final sensitivity closure.** The first PROMETHEE II/TOPSIS numerical execution is superseded and must not be used. The authoritative corrected recomputation is workflow run `33090126353`, based on corrected backbone/OD run `33089335405`.

PROMETHEE II remains the primary ranking method, TOPSIS the independent contrast, and 10,000 weight draws the weight-robustness layer.

## Locked analytical safeguards

- decision universe: 144 municipalities of Pará;
- destination service universe: services located in Pará;
- interstate functional influences: discussion/context only;
- ordinary-access air routing excluded;
- no synthetic travel times or hydro edges;
- no cartographic-distance-to-time conversion;
- no invented vessel speed;
- waiting time excluded consistently with the reference baseline;
- a missing modeled transfer is never interpreted automatically as real-world isolation.

## Nine MCDM criteria

Accessibility:
1. `criterion__reachable_service_fraction`
2. `criterion__services_within_120_fraction`
3. `criterion__nearest_reachable_service_time_min`
4. `criterion__median_reachable_service_time_min`

Institutional/service deficits:
5. `criterion__health_specialized_absence`
6. `criterion__creas_absence`
7. `criterion__specialized_security_absence`
8. `criterion__specialized_justice_absence`

Territorial context:
9. `criterion__rural_female_share`

Income, poverty, schooling, race/color and female age structure are reserved for SOM/profile analysis rather than direct MCDM criteria. Female population size is a support/aggregation quantity, not a priority criterion.

## Priority direction

The model represents **priority need/burden**. Lower reachable-service fraction and lower share within 120 min increase priority need; larger nearest/median travel times increase priority need; institutional absence increases priority need; and larger female rural share represents greater territorial burden. The implementation transforms criteria to a common priority direction before PROMETHEE/TOPSIS.

## Reference weights and robustness

Reference weights are equal at criterion level (`1/9` each) as a transparent neutral reference, not as a claim of substantive truth. This gives 4/9 to accessibility criteria, 4/9 to institutional deficits and 1/9 to rurality under the reference configuration.

Weight uncertainty is assessed with 10,000 draws from `Dirichlet(1,...,1)` over the nine criteria, seed `20260827`. In the corrected run, Spearman agreement with the equal-weight PROMETHEE II reference across random weights is approximately:
- median: 0.8913;
- 5th percentile: 0.6855;
- 95th percentile: 0.9741.

## TOPSIS contrast

TOPSIS is a cross-method check on complete transformed alternatives. Afuá is not given invented accessibility values merely to force TOPSIS completeness. PROMETHEE II remains primary because its implementation can retain Afuá using only pairwise-comparable observed criteria while explicitly flagging its reduced evidence completeness.

## Bounded network correction

A post-ranking plausibility audit identified exactly two evidence-backed omitted transfers. A bounded statewide screen was then closed; no additional municipality met the declared rule requiring both concrete hydro/ferry dependence and an OD anomaly.

### Colares
- route: `Colares - Penhalonga`, PA-238/Furo da Laura;
- exact frozen-graph nodes: `3648185532 <-> 3678212692`;
- reference impedance: 10 min;
- waiting excluded;
- corrected classification: `routed_reachable`.

Corrected municipal accessibility indicators include reachable-service fraction 0.653333, services within 120 min about 0.14693, nearest reachable service about 47.8 min, and median reachable-service time about 177.7 min.

### Santa Cruz do Arari
- route: `Belém - Santa Cruz do Arari`;
- exact frozen-graph nodes: `4799782642 <-> 7983414759`;
- reference impedance: 420 min, based on the official approximately 7 h launch reference;
- current 2026 evidence independently validates route existence, while 420 min is retained as a documented reference impedance rather than claimed as a contemporaneous measured duration;
- waiting excluded;
- corrected classification: `routed_reachable`.

Corrected municipal accessibility indicators include reachable-service fraction 0.653333, no services within 120 min, nearest reachable service about 425.6 min, and median reachable-service time about 575.0 min.

### Afuá
Afuá is retained as a **coverage/scope-limited** municipality. No sufficiently documented Pará-bound ordinary surface temporal edge was authorized under the locked Pará-only service-destination scope. Known Afuá–Macapá functional access remains discussion/context only.

No synthetic connection or penalty is assigned. Accessibility criteria remain missing where routing evidence is unavailable, Afuá is not described as real-world isolated, and all ranking outputs explicitly flag its reduced comparability. No further route search is required for the primary model.

## Corrected OD

Authoritative corrected OD run: `33089335405`.
- origins: 12,673;
- services: 225;
- OD pairs: 2,851,425;
- reachable pairs: 1,542,802;
- unreachable pairs: 1,308,623;
- added directed transfer edges: 4 (two bidirectional transfers);
- Afuá synthetic edges: 0.

## Corrected Stage 3

Authoritative corrected Stage-3/Stage-4 run: `33090126353`.
- municipalities retained: 144;
- candidate criteria: 9;
- maximum missing fraction: 1/144 (`0.006944...`);
- redundant pairs at threshold 0.80: 0;
- VIF indicators >= 5: 0;
- maximum VIF: 3.282640463;
- PCA: not recommended;
- Colares: `routed_reachable`;
- Santa Cruz do Arari: `routed_reachable`;
- Afuá: only coverage-limited alternative.

## Corrected PROMETHEE II reference

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

Santa Cruz do Arari remains highly prioritized because of its observed long travel times and institutional deficits, not because of artificial graph disconnection. Colares falls from the invalid pre-correction first position to 11th after the real ferry connection is restored.

This corrected reference ranking is authorized for the final sensitivity stage but is **not yet the final manuscript policy ranking**. Preference-function/scaling sensitivity and final rank-stability summaries must be closed before the MCDM stage is frozen for manuscript reporting.
