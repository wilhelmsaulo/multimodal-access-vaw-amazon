# Data inventory

This file is the authoritative registry for every dataset considered by the project. Update it before adding or processing a source.

| Domain | Candidate source | Existing asset | Required for new study | Current status | Main limitation |
|---|---|---:|---:|---|---|
| Municipal boundaries | IBGE | Yes | Yes | Source and 2022 visualization derivative audited; acquire original analytical geometry | Prior derivative was simplified for web display |
| Female population | IBGE Census 2022 / SIDRA | Municipal query and reusable SIDRA connector available | Yes | Sector-level workflow implemented and audited | 486 demographic rows have unavailable female counts |
| Census sectors | IBGE Census 2022 | Definitive Pará GeoPackage acquired and audited | Yes | Workflow implemented; 16,714 unique sectors | Polygon geometry alone is not an inhabited origin |
| Inhabited localities | IBGE Censo 2022 — Localidades do Brasil | Acquisition/audit workflow implemented | Yes, origin validation | Official Pará locality points are spatially assigned to sectors; expected total 4,837 | Multiple localities can occur in one sector; sector population must not be duplicated across points |
| Georeferenced addresses | IBGE CNEFE 2022 | Privacy-preserving schema/quality audit workflow implemented | Yes, origin derivation | Pará state ZIP audited at runtime before representative origins are generated | Coordinate quality varies; raw address-level coordinates are not published |
| Health services | CNES / DEMAS | Acquisition and candidate-screening pipeline implemented | Yes | Active Pará establishments plus hospital-bed capacity source integrated | Candidate function still requires VAW-relevance validation |
| Social assistance | MDS / Censo SUAS 2024 | Acquisition/normalization pipeline implemented | Yes | CREAS resources discovered, filtered to Pará and consolidated | Unit-level capacity mapping still requires validation |
| Justice services | TJPA | Official-directory parser implemented | Yes | Specialized VAW units extracted as candidates | Capacity and some coordinates may be unavailable |
| Specialized VAW services | Ministério das Mulheres / Ligue 180 | Official publication audit implemented | Yes | Public panel/resources audited; curated extract allowed when source is validated | Living directory; confidential shelter locations must not be exposed |
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

## Origin reconstruction policy

A polygon centroid is not accepted as the default population origin for large rural/riverine sectors. The project now combines two official IBGE evidence layers: `Localidades do Brasil` to identify permanent inhabited localities and CNEFE 2022 to derive a single residentially anchored representative point per sector where the audited address schema and coordinate quality permit. Raw CNEFE address coordinates are not committed. Sector-level female population remains a single demand quantity and is never replicated across multiple localities.
