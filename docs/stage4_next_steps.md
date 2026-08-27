# Stage 4 next steps

## Network correction closure — 2026-08-27

The first Stage 4 ranking is superseded and must not be used. A bounded post-ranking plausibility audit identified two omitted real-world transfers and one scope-limited municipality.

Authoritative corrected routing inputs:
- corrected backbone run: `33089335405`
- corrected backbone artifact: `pa-corrected-multimodal-backbone`
- corrected OD artifact: `pa-corrected-reference-od`
- corrected OD pairs: 2,851,425
- reachable pairs: 1,542,802
- unreachable pairs: 1,308,623
- Afuá: no synthetic edge; retained as coverage/scope-limited
- Colares: evidence-backed Penhalonga/Furo da Laura ferry edge, 10 min reference impedance, waiting excluded
- Santa Cruz do Arari: evidence-backed Belém passenger-hydro edge, 420 min official reference impedance, waiting excluded

The statewide hydro/ferry anomaly screen was bounded and closed; no additional municipality met the declared critical-case rule.

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

Colares is no longer structurally unreachable: reachable-service fraction 0.653333; services within 120 min about 0.14693; nearest reachable service about 47.8 min; median reachable-service time about 177.7 min. Its reference PROMETHEE II rank is 11.

PROMETHEE II versus TOPSIS remains the principal/cross-method design. The 10,000-draw weight robustness audit is retained.

## Remaining Stage 4 work

1. Run preference-function / scaling sensitivity around the locked corrected PROMETHEE II reference.
2. Include bounded sensitivity for the two reopened transfer impedances if needed for manuscript robustness; do not reopen the statewide route search.
3. Summarize top-10/top-quartile rank acceptability and unstable municipalities.
4. Preserve Afuá as coverage/scope-limited in all outputs and discussion.
5. Freeze the manuscript-level MCDM specification after sensitivity closure.
6. Proceed to SOM/profile analysis using the socioeconomic/demographic block reserved for SOM.
