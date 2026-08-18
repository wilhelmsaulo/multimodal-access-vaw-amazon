# Service inventory method for Stage 2

Reference date: 2026-08-18.

## Purpose

Build a defensible destination inventory for the E2SFCA accessibility model without assuming that all facilities are equivalent or that simple presence measures operational capacity.

## Primary official sources

### Health — CNES / Ministry of Health

The CNES open-data portal is active and was updated on 2026-08-18. It offers API/CSV/JSON/XML resources and daily updates. The primary health layer must filter establishments by functions relevant to VAW response rather than include every health unit. Candidate capacity measures include beds, professionals, teams, and registered specialized services. Presence alone is a fallback sensitivity specification, not the preferred main capacity measure.

### Social assistance — Censo SUAS / MDS

Use Censo SUAS 2024 as the primary structural source, incorporating published corrections through 2026. CREAS is the primary specialized social-assistance destination category. CRAS may be analyzed as a broader social-assistance layer but must not be treated as functionally interchangeable with CREAS or specialized women's services. Censo SUAS worker counts, team composition, service structure, and RMA attendance measures are candidate capacity proxies.

### Specialized VAW network — Ministry of Women / Ligue 180

The official Rede de Atendimento panel is a living national directory of services for women experiencing violence. It supplies service locations and contacts and should be used to validate specialized women's centers, DEAMs, public-defense/prosecution services and other explicitly listed services. Functional categories must be preserved. Exact confidential shelter locations must never be published.

### Justice — TJPA

The official TJPA service/contacts directory identifies specialized domestic-and-family-violence courts, including units in Belém/Icoaraci, Castanhal and Santarém. The primary justice layer should include units explicitly specialized in violence against women. General courts are not assumed to be equivalent substitutes.

## Capacity hierarchy

For each service, use the strongest defensible information available, in this order:

1. observed operational capacity directly tied to the service;
2. documented staffing/team capacity;
3. documented structural proxy (e.g. beds, specialized teams);
4. documented activity proxy when conceptually appropriate;
5. unit presence = 1 only as an explicit fallback/sensitivity specification.

Missing capacity must never be replaced by invented values.

## Geolocation hierarchy

1. official coordinates supplied by the source;
2. validated official full address geocoded reproducibly;
3. manually verified public institutional address;
4. exclude from route-level analysis until validated.

Approximate municipal centroids are not acceptable substitutes for service locations in the E2SFCA model.

## Functional non-substitutability

E2SFCA is computed separately by service type. A hospital, CREAS, DEAM, specialized court, public-defense unit and women's reference center are not treated as interchangeable services. Any later synthesis across categories requires a separate substantive justification.

## Sensitive locations

Shelters and other protected facilities may appear in source directories. If an exact location is confidential or safety-sensitive, it must not be committed or published. Such services can only be represented at a disclosure-safe geography if scientifically justified and consistent with source restrictions.

## Next acquisition outputs

The acquisition workflow should produce a harmonized public derived table with at least:

- `service_id`
- `service_name`
- `service_type`
- `provider_source`
- `municipality_code`
- `municipality_name`
- `address_public`
- `latitude`
- `longitude`
- `capacity`
- `capacity_type`
- `capacity_source`
- `reference_date`
- `validation_status`
- `redistribution_status`

Only rows with validated public locations can enter the route matrix.
