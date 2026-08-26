# Routing-coverage uncertainty contract

## Purpose

The frozen OD matrix contains validated travel times for 12,673 of 15,743 audited origins. Non-routing-ready origins are not automatically physically unreachable; their connectors are unobserved or fail the locked evidence policy. A point estimate that silently excludes them would be selection-biased, while assigning travel times or average accessibility would fabricate evidence.

## Partial-identification sensitivity envelope

After E2SFCA is calculated for a service type and scenario, municipal aggregation must retain the full 15,743-origin female-population roster. For every municipality:

- the observed component is the female-population-weighted E2SFCA score among origins with a calculated score;
- the lower sensitivity completion assigns zero to non-observed origins;
- the upper sensitivity completion assigns the largest observed sector score in the same service-type/scenario stratum to non-observed origins;
- the reported coverage fraction is observed female population divided by total audited female population.

These endpoints are empirical stress-test completions. They are not confidence intervals and must not be described as statistical uncertainty bounds on the true accessibility value.

## Limitation retained explicitly

The post-E2SFCA envelope does not reconstruct unknown travel times and does not correct the service-demand denominator for populations whose connector is unknown. Consequently, it cannot authorize final E2SFCA results by itself. It answers a narrower question: how strongly can municipal aggregation change under extreme score completions, conditional on the validated OD calculation?

## Decision rule

- Fully observed municipalities have identical lower and upper envelopes.
- Partially observed municipalities retain both endpoints and the continuous coverage fraction.
- A single municipal point estimate must not be passed to MCDM or SOM while the envelope is materially wide.
- Ranking stability must later be evaluated under both endpoints and any separately justified connector scenario.
- No missing origin may be reclassified as truly unreachable solely because it lacks a validated connector.
