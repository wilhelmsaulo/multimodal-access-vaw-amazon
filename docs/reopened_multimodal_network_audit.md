# Reopened multimodal network audit — Colares, Santa Cruz do Arari and Afuá

## Why the Stage 4 ranking was invalidated

A post-MCDM plausibility check revealed that Colares and Santa Cruz do Arari were classified as unreachable in the frozen reference graph despite documented real-world ferry/passenger-hydro connections. Afuá had no routing-ready origin even though its transport system is hydro-dominant. These are upstream network-representation problems; they cannot be repaired at the MCDM layer.

The frozen final backbone artifact also contains only three materialized road–hydro terminal identities: **Muaná, Soure and Moju**. This requires a statewide transfer-terminal re-audit before a corrected reference OD is frozen.

## Colares

- 33 routing-ready origins were present in the frozen endpoint artifact.
- Origins were correctly attached to local primary-road nodes.
- The missing element is the PA-238 road–ferry–road transfer across the Furo da Laura at Penhalonga.
- State road definitions explicitly include `Colares - Travessia Furo da Laura (Penhalonga) - PA-140` in PA-238.
- The Municipality of Colares states that current continental access is by ferry while the bridge is under construction.
- A user-supplied Google Maps reference identifies Porto da Balsa Penhalonga/Colares near -0.9949506, -48.1932262. This point is used only for terminal disambiguation; no geometry is converted into travel time.

**Status:** topology/existence validated; current crossing duration and waiting rule remain pending. Colares must not be assigned zero reachability in a corrected network merely because this transfer is absent.

## Santa Cruz do Arari

- 8 routing-ready origins were present in the frozen endpoint artifact.
- The uploaded technical report places Santa Cruz do Arari about 115 km in straight line from Belém and reports about 13 hours by ship in its historical reference period.
- The report states that access to Belém is by launch and documents real service-referral flows to Belém, Soure and Cachoeira do Arari.
- The same report documents strongly hydro-dependent intra-municipal access, including rabeta, voadeira, rented boats and a fluvial health unit.
- Current 2026 public terminal schedules list Santa Cruz do Arari repeatedly among Belém passenger-hydro services, independently validating that the intermunicipal route remains active.
- Historical state regulatory material also records an authorized Belém/Santa Cruz do Arari passenger line using the Belém Hydro Terminal and the municipal port.

**Status:** route existence/current operation validated; current travel duration and exact terminal/boarding identity remain pending. The historical ~13 h value is evidence, not automatically a 2026 impedance.

## Afuá

- The frozen endpoint artifact contains 0 routing-ready origins for Afuá.
- Current municipal information states that Afuá is an island and that regular line boats connect Afuá with Macapá; the same current municipal page lists Belém–Afuá access by small-aircraft operator rather than a regular passenger boat.
- The study's primary scope is now explicitly locked to destination services located in Pará, with ordinary-access air routing disabled. Macapá functional influence is therefore discussion/context, not a primary accessibility destination.

**Status:** origin logic must be rebuilt as hydro-first. However, a current Pará-bound passenger surface route has not yet been validated. If one cannot be documented for the reference period, Afuá must remain a transparent scope/coverage-limited case in the Pará-only ordinary-access model; connectivity must not be fabricated.

## Scientific safeguards

1. Do not infer boat/ferry speed from distance.
2. Do not assign an arbitrary waiting time.
3. Do not use the future Colares bridge until operational availability is evidenced for the reference period.
4. Do not use Macapá services in the primary model.
5. Do not convert absence of a modeled transfer into evidence of real-world isolation.
6. Regenerate OD only after added transfer edges have evidence-backed temporal impedance.
7. After network correction, regenerate accessibility/E2SFCA outputs affected by routing, rerun Stage 3 diagnostics, then rerun PROMETHEE II/TOPSIS/robustness.
