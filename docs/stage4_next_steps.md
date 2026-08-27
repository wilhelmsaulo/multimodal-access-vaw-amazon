# Stage 4 next steps

## Network correction closure — 2026-08-27

The first Stage 4 ranking is superseded and must not be used. A bounded post-MCDM plausibility audit identified two omitted real-world transfers and one scope-limited municipality.

Authoritative corrected routing inputs:
- corrected backbone/OD run: `33089335405`;
- corrected backbone artifact: `pa-corrected-multimodal-backbone`;
- corrected OD artifact: `pa-corrected-reference-od`;
- corrected OD pairs: 2,851,425;
- reachable pairs: 1,542,802;
- unreachable pairs: 1,308,623;
- Afuá: no synthetic edge; retained as coverage/scope-limited;
- Colares: Penhalonga/Furo da Laura ferry restored with 10-min reference impedance and no waiting;
- Santa Cruz do Arari: Belém passenger-hydro connection restored with 420-min official reference impedance and no waiting.

The statewide hydro/ferry anomaly screen is closed; no additional municipality met the declared critical-case rule.

## Corrected Stage 3 / Stage 4

Authoritative recomputation run: `33090126353`.

Stage 3 after the network correction:
- 144 municipalities retained;
- 9 MCDM candidate criteria;
- 0 redundancy pairs at |r| >= 0.80;
- 0 VIF flags at VIF >= 5;
- maximum VIF = 3.282640463;
- PCA not recommended;
- Afuá is the only coverage-limited alternative;
- Colares and Santa Cruz do Arari are both `routed_reachable`.

Corrected PROMETHEE II reference ranking begins:
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

Santa Cruz do Arari remains highly prioritized for observed model reasons rather than artificial graph disconnection: reachable-service fraction 0.653333; no service within 120 min; nearest reachable service about 425.6 min; median reachable-service time about 575.0 min; all four modeled specialized institutional pillars absent.

Colares is no longer structurally unreachable: reachable-service fraction 0.653333; services within 120 min about 0.14693; nearest reachable service about 47.8 min; median reachable-service time about 177.7 min. Its corrected reference PROMETHEE II rank is 11.

The 10,000 weight draws remain part of the MCDM robustness analysis. Corrected Spearman versus the equal-weight PROMETHEE II reference: median ~0.8913, p05 ~0.6855, p95 ~0.9741.

## Remaining Stage 4 work

1. Run preference-function / scaling sensitivity around the locked corrected PROMETHEE II reference.
2. If useful for manuscript robustness, run a bounded sensitivity around the two reopened transfer impedances; do not reopen the statewide route search.
3. Summarize top-10/top-quartile rank acceptability and identify unstable municipalities.
4. Preserve Afuá as coverage/scope-limited in every output and discussion.
5. Freeze the manuscript-level MCDM specification after sensitivity closure.
6. Proceed to SOM/profile analysis using the socioeconomic/demographic block reserved for SOM.
