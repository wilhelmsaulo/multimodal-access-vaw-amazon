# Data inventory

This file is the authoritative registry for every dataset considered by the project. Update it before adding or processing a source.

| Domain | Candidate source | Existing asset | Required for new study | Current status | Main limitation |
|---|---|---:|---:|---|---|
| Municipal boundaries | IBGE | Yes | Yes | Source and 2022 visualization derivative audited; acquire original analytical geometry | Prior derivative was simplified for web display |
| Female population | IBGE Census 2022 / SIDRA | Municipal query and reusable SIDRA connector available | Yes | Next workflow: verify and extract sector-level data | Sector-level availability and disclosure rules must be confirmed |
| Census sectors and localities | IBGE Census 2022 | Definitive Pará GeoPackage acquired and audited | Yes | Workflow implemented; 16,714 unique sectors | Rural polygons still need defensible inhabited origins |
| Health services | CNES | Partial municipal inventory | Yes | Recover, geocode, validate | Presence does not guarantee relevant service |
| Social assistance | MDS / Censo SUAS | Partial municipal inventory | Yes | Recover, geocode, validate | Function and operating status may vary |
| Justice services | TJPA | Partial municipal inventory | Yes | Recover, geocode, validate | Coverage may be regional |
| Specialized VAW services | Ligue 180 and official directories | Partial municipal inventory | Yes | Recover, geocode, validate | Living directories and sensitive locations |
| Municipal institutions | MUNIC 2023 | Yes | Contextual | Reuse after audit | Not an accessibility outcome |
| Road infrastructure | DNIT / MapBiomas / other official layers | Source catalog and audited download manifest copied | Yes | Reacquire originals, then convert to routable graph | Previous indicators were municipal aggregates |
| River network | Rocha et al. / official hydrography | Partial layers available | Yes | Acquire and test routing dataset | Navigability and seasonality |
| Ports and crossings | ANTAQ and official sources | Source catalog and download audit copied | Yes | Reacquire, validate, and connect | Schedules and informal stops incomplete |
| Air infrastructure | DECEA / ICA | Available | Scenario-specific | Keep disabled by default | Infrastructure is not service availability |
| Police records 2022–2025 | SEGUP / CODEC-CIAC | Processed municipal data | Contextual only | Do not use as demand proxy | Not incidence or hidden demand |

## Mandatory metadata for each acquired dataset

- official title and provider;
- access URL or acquisition procedure;
- download and reference dates;
- spatial and temporal coverage;
- original coordinate reference system;
- license or access restriction;
- raw checksum;
- processing script and output;
- known omissions and uncertainties;
- redistribution decision.

## Previous-repository audit status

The audit and selective copy are documented in `docs/previous_repository_audit.md`. Copied JSON files under `references/legacy_sources/` are historical acquisition records only; they are not treated as current data or analytical inputs. Every operational source will be revalidated and reacquired with a new checksum before use.

## IBGE 2022 sector acquisition completed

On 2026-08-17, the official Pará sector GeoPackage, national sector-demography ZIP, and updated data dictionary were acquired and checksummed. The raw files remain ignored. The audit confirmed `V01008` as female population, 16,714 unique Pará sectors, 649 zero-population geometry-only sectors, and 486 demographic rows with unavailable female counts. Processing rules and hashes are versioned in `config/ibge_census2022_sectors.yml`.
