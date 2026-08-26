# Origin routing coverage recovery audit

Status: **recovery evidence classified; primary E2SFCA remains gated**.

This audit reconciles all 15,743 upstream origins with the 12,673 frozen routing-ready endpoints. It does not change the closed Stage 2 OD matrix and does not promote any connector.

## Main findings

- 3,070 origins representing 573,258 women are not routing-ready.
- 1,765 origins (309,339 women) are direct-primary upper-regime residuals that require empirical attachment validation.
- 917 origins (192,568 women) have a local OSM path but require modal and cartographic-alignment validation.
- 84 origins (23,064 women) are hydro-priority residuals lacking route evidence.
- 304 origins (48,287 women) remain unresolved network gaps.
- Ten municipalities have less than 50% female-population routing coverage.
- Afuá has 44 origins and 18,057 women in the audited layer, but no routing-ready origin: 27 direct upper-regime residuals, 14 local-path residuals and 3 hydro-priority residuals.

## Interpretation safeguard

`non-routing-ready` is an evidence status, not proof that the population is physically unable to reach services. No nearest-node snap, Euclidean-time conversion, OSM `service`-path speed or hydro route was inferred.

## Files

- `origin_routing_coverage_recovery_audit.json`: machine-readable totals, recovery classes and safeguards.
- `routing_population_coverage_by_municipality.csv`: municipality-level origin and female-population coverage.
- `non_routing_ready_origins_recovery_audit.csv.gz`: origin-level recovery evidence for sensitivity design.

The next task is to specify explicit connector sensitivity bounds for the lowest-coverage municipalities while keeping the frozen primary OD unchanged.
