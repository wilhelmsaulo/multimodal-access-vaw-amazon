# E2SFCA routing-coverage sensitivity

Status: **executed and audited; not authorized as final municipal E2SFCA**.

The frozen `reference_network` OD matrix was evaluated separately for CREAS, health, specialized justice and specialized security. Every service has unit supply (`S_j = 1`). Six provisional specifications combine 120, 240 and 480 minute thresholds with exponential and Gaussian decay. Both decay functions are calibrated to weight a trip at the threshold by 0.10; trips beyond the threshold are excluded.

The execution retains all 144 municipalities through the routing-coverage uncertainty envelope. It does not relabel the reference network as flood or dry season and does not impute travel times for non-routing-ready origins.

## Outputs

- `municipal_e2sfca_coverage_envelopes.csv.gz`: 3,456 municipal/service/specification envelopes.
- `service_supply_demand_ratios.csv.gz`: unit-supply ratios from the validated routing-ready population.
- `e2sfca_coverage_sensitivity_manifest.json`: parameters, counts, safeguards and checksums.
- `e2sfca_specification_rank_stability.csv`: pairwise Spearman summaries across the six specifications.
- `e2sfca_coverage_sensitivity_audit.json`: coverage and envelope-width audit.

## Interpretation

Supply conservation passed with maximum error zero. Parameter agreement is generally high, but coverage uncertainty remains material. Only Curionópolis, Quatipuru and Sapucaia have complete female-population routing coverage; Afuá has no observed sector score and therefore spans the full empirical sensitivity envelope in every category and specification.

The lower and upper values are deterministic stress-test completions, not confidence intervals. The upper endpoint is deliberately extreme and uses the largest observed sector score in the same service/specification stratum. Neither endpoint corrects unknown connector effects on service competition. A single point from these outputs must not yet be passed to MCDM or SOM.
