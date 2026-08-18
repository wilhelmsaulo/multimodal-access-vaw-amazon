# Census-sector origin-point strategy

## Purpose

Stage 2 requires one defensible population origin for each analytical census sector while preserving the sector-level female population as the demand quantity. A geometric polygon centroid is not assumed to represent where residents actually live, especially in large rural and riverine sectors.

## Official evidence layers

### IBGE Censo Demográfico 2022 — Localidades do Brasil

The 2025 release identifies named permanent inhabited localities and provides category, municipality, unique locality code, latitude and longitude. Pará contains 4,837 localities across cities, villages, settlements, rural nuclei, `Agrovilas do PA`, Indigenous localities, Quilombola localities, urban nuclei and other localities.

The project spatially assigns every Pará locality to its 2022 census sector and audits sectors containing zero, one or multiple official localities. Locality points are evidence of inhabited places; they are not automatically assigned the whole sector population when multiple localities occur in one sector.

### IBGE CNEFE 2022 — georeferenced addresses

CNEFE 2022 is the preferred evidence layer for deriving a single inhabited representative point because it includes census-sector identifiers and georeferenced addresses collected during the 2022 Census. The IBGE documents that the 2022 CNEFE was the first census address register with complete georeferencing coverage, while also warning that coordinate precision varies and that some failed coordinates were estimated from other observations, street-face midpoints or, as a last fallback, sector centroids.

The field `NV_GEO_COORD` records the coordinate geocoding level. The project therefore audits actual Pará values before defining accepted quality levels.

## Proposed decision rule, pending CNEFE schema audit

1. Keep exactly one demand total (`female_population`) per census sector.
2. Do not replicate sector population across multiple locality points.
3. Derive a representative inhabited point from residential-address coordinates whenever the CNEFE schema audit supports an unambiguous residential-species filter.
4. Prefer an observed residential address medoid or an equivalent robust representative point over a raw arithmetic centroid, so the final point remains anchored in an inhabited location.
5. Use `NV_GEO_COORD` to report coordinate-quality composition and to exclude or flag low-quality fallback geocodes where defensible.
6. Use official IBGE locality points as an independent validation layer and as a fallback only under an explicit documented rule.
7. Never treat an unvalidated rural polygon centroid as the final analytical origin.

## Privacy and reproducibility

Raw address-level CNEFE coordinates are not committed to the repository. The reproducible workflow downloads the official data at runtime and may publish only sector-level derived representative points, quality summaries and checksums when redistribution is defensible. Individual addresses are unnecessary for the final article and should not appear in results.

## Required audit before finalization

The origin rule is finalized only after reporting:

- CNEFE field names and residential-species categories;
- distribution of `NV_GEO_COORD` quality levels;
- number of residential address records by sector;
- sectors with no eligible residential coordinates;
- distance between the derived sector origin and official IBGE locality points where available;
- urban/rural differences in those diagnostics.
