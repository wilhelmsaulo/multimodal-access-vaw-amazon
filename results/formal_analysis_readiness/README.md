# Formal analysis readiness audit

Status: **E2SFCA blocked by routing-population coverage; formal Stage 1 still blocked**.

The validated Stage 2 routing layer is closed and usable as a `reference_network` impedance matrix: 12,673 origins, 225 routing-ready services and 2,851,425 origin-destination pairs. This does not by itself authorize an E2SFCA result.

## Findings

- No versioned analytical indicator table and no explicit indicator-block declaration were found. Therefore Spearman, VIF, PCA, block-variance and implicit-weight results cannot yet be produced reproducibly.
- The frozen service access policy contains 236 service rows, of which 225 are usable for the primary routing set.
- The frozen service policy and routing endpoints do not require operational-capacity fields because the primary estimand is presence-based territorial accessibility.
- The current OD scenario is `reference_network`. It is not a flood/dry comparison and excludes waiting time.
- Service types must remain separate; they are not substitutes.
- The frozen OD covers 12,673 of the 15,743 origins in the upstream network-access evidence (80.50%) and 3,491,303 of 4,064,561 women represented there (85.90%).
- Afuá has no routing-ready origin in the frozen OD. Several other riverine municipalities have low female-population coverage, including Chaves (24.06%), Limoeiro do Ajuru (30.61%) and Melgaço (37.08%).

## Model decision recorded

The primary E2SFCA model uses `S_j = 1` for every validated routing-ready unit and is calculated separately by service type. It measures territorial availability relative to female population; it does not measure throughput, quality, staffing, waiting time or utilization.

Observed or mixed capacity proxies are excluded from the primary model because complete and conceptually comparable capacity data are not available across health, CREAS, specialized security and specialized justice.

## Execution gate

Missing operational capacity no longer blocks presence-based E2SFCA. Final numerical execution is nevertheless stopped because using only the routable subset would omit 14.10% of the female population represented in the upstream access-evidence layer and would exclude Afuá entirely. This is a coverage/selection issue, not a numerical E2SFCA error.

Before final execution, the study must version a defensible rule for non-routing-ready origins and quantify its effect. Formal Stage 1 also remains stopped until both are versioned:

1. the analytical indicator table plus declared blocks;
2. the final E2SFCA municipal indicators selected after routing-coverage, sensitivity and stability auditing.

See `routing_population_coverage_audit.json` for the machine-readable coverage gate.

The subsequent recoverability classification is stored under `results/origin_routing_coverage_recovery/`. It separates direct upper-regime, local-path, hydro-priority and unresolved-network residuals without interpreting any of them as true unreachability or promoting unsupported connectors.

See `formal_analysis_readiness_audit.json` for the machine-readable decision record.
