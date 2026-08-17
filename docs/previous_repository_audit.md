# Audit of reusable assets from preceding repositories

Audit date: 2026-08-17  
Target branch: `agent/repository-bootstrap`

## Repositories inspected

1. [robust-underreporting-vaw-amazon](https://github.com/wilhelmsaulo/robust-underreporting-vaw-amazon), public, MIT license for code and documentation.
2. [explainable-municipal-prioritization-framework](https://github.com/wilhelmsaulo/explainable-municipal-prioritization-framework), public, no explicit repository license found at audit time.

The owner authorized reuse in the new project. File-level origin is retained and the new repository license remains pending until third-party data and reused code are fully reviewed.

## Incorporated now

| New path | Origin | Decision | Adaptation |
|---|---|---|---|
| `src/data/sidra.py` | IEEE Access repository, SIDRA connector | Reuse | Package import changed; no municipal query fixed in code |
| `src/data/provenance.py` | IEEE Access repository | Reuse | Package location changed |
| `src/data/sources.py` | IEEE Access repository | Reuse | Generic registry only |
| `src/data/harmonization.py` | Both preceding repositories | Adapt | Retains only text, numeric, SIDRA payload, and IBGE-code cleaning |
| `src/network/source_catalog.py` | IEEE Access repository | Reuse | Moved to the new network package |
| `src/network/download.py` | IEEE Access repository | Reuse | Import updated to the new catalog location |
| `references/legacy_sources/*.json` | IEEE Access repository | Snapshot | Historical source and download audit; not analysis inputs |

## Available but deliberately deferred

| Asset | Reason |
|---|---|
| CNES collectors | Useful source knowledge, but existing output is municipal; the new study needs facility-level destinations and relevant functions |
| TJPA collector | Existing routine aggregates municipal availability; destination coordinates and regional jurisdiction require redesign |
| Social-assistance collectors | Existing outputs are municipal indicators; facility-level CREAS and service status must be retained |
| Ligue 180 parser and geocoder | Candidate starting point, but approximate or municipal-seat geocoding cannot be accepted as final destination coordinates |
| MapBiomas road indicator builder | Calculates municipal density/coverage, not a connected routable road graph |
| ANTAQ/DECEA non-road indicator builder | Produces municipal indicators, not schedules, edges, transfers, or travel times |
| Simplified municipal GeoJSON | Web visualization derivative simplified to 2%; unsuitable for analytical routing or census-sector processing |

## Excluded from the new repository

- police records and police-processing routines;
- ELECTRE TRI-B, TOPSIS, PROMETHEE II, SMAA, Pareto, weights, rankings, and scenario outputs;
- previous integrated municipal matrices and article results;
- territorial barriers based on representative municipal points or geodesic distance;
- dashboards and manuscript figures;
- raw or restricted datasets;
- confidential shelter locations.

## Practical consequence

The new repository inherits acquisition and provenance infrastructure, not the preceding municipal analytical model. The first new data workflow will use the SIDRA/IBGE utilities to construct census-sector origins and attach female population, after official sector-level tables and disclosure rules are verified.
