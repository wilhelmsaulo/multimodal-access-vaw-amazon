# Formal analysis readiness audit

Status: **blocked before numerical model execution**.

The validated Stage 2 routing layer is closed and usable as a `reference_network` impedance matrix: 12,673 origins, 225 routing-ready services and 2,851,425 origin-destination pairs. This does not by itself authorize an E2SFCA result.

## Findings

- No versioned analytical indicator table and no explicit indicator-block declaration were found. Therefore Spearman, VIF, PCA, block-variance and implicit-weight results cannot yet be produced reproducibly.
- The frozen service access policy contains 236 service rows, of which 225 are usable for the primary routing set.
- Neither the frozen service policy nor the routing endpoints contain `capacity`, `capacity_type` or `capacity_source`.
- The current OD scenario is `reference_network`. It is not a flood/dry comparison and excludes waiting time.
- Service types must remain separate; they are not substitutes.

## Model decision now required

The primary model should preferably use observed or documented capacity, separately by service type. A mixed hierarchy of observed capacity and documented proxies is admissible only with a type-specific definition and missingness audit.

Assigning `capacity = 1` is allowed only as an explicitly labelled **unit-presence sensitivity analysis**. It must not be presented as observed capacity or silently promoted to the primary E2SFCA specification.

## Execution gate

Numerical Stage 1 and E2SFCA execution remain stopped until both are versioned:

1. the analytical indicator table plus declared blocks;
2. the service-type capacity policy and its service-level capacity table.

See `formal_analysis_readiness_audit.json` for the machine-readable decision record.
