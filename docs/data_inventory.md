# Data inventory

This file is the authoritative registry for every dataset considered by the project. Update it before adding or processing a source.

| Domain | Candidate source | Existing asset | Required for new study | Current status | Main limitation |
|---|---|---:|---:|---|---|
| Municipal boundaries | IBGE | Yes | Yes | Reuse after audit | Municipal scale only |
| Female population | IBGE Census 2022 / SIDRA | Municipal totals available | Yes | Needs intra-municipal extraction | Sector-level availability must be confirmed |
| Census sectors and localities | IBGE Census 2022 | Not confirmed | Yes | Acquire and audit | Rural centroids may misrepresent habitation |
| Health services | CNES | Partial municipal inventory | Yes | Recover, geocode, validate | Presence does not guarantee relevant service |
| Social assistance | MDS / Censo SUAS | Partial municipal inventory | Yes | Recover, geocode, validate | Function and operating status may vary |
| Justice services | TJPA | Partial municipal inventory | Yes | Recover, geocode, validate | Coverage may be regional |
| Specialized VAW services | Ligue 180 and official directories | Partial municipal inventory | Yes | Recover, geocode, validate | Living directories and sensitive locations |
| Municipal institutions | MUNIC 2023 | Yes | Contextual | Reuse after audit | Not an accessibility outcome |
| Road infrastructure | DNIT / MapBiomas / other official layers | Spatial layers available | Yes | Convert to routable graph | Geometry is not yet a temporal network |
| River network | Rocha et al. / official hydrography | Partial layers available | Yes | Acquire and test routing dataset | Navigability and seasonality |
| Ports and crossings | ANTAQ and official sources | Partial layers available | Yes | Recover and connect | Schedules and informal stops incomplete |
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
