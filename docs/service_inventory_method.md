# Service inventory method for Stage 2

Reference date: 2026-08-18.

## Purpose

Build a defensible destination inventory for the presence-based E2SFCA accessibility model without assuming that all facilities are equivalent or that unit presence measures operational capacity.

## Primary official sources

### Health — CNES / Ministry of Health

The CNES open-data portal is active and was updated on 2026-08-18. It offers API/CSV/JSON/XML resources and daily updates. The primary health layer must filter establishments by functions relevant to VAW response rather than include every health unit. The primary model assigns one unit of supply to every validated establishment. Beds, professionals, teams, and registered specialized services are outside the primary cross-category model because they are neither complete nor comparable across service types.

### Social assistance — Censo SUAS / MDS

Use Censo SUAS 2024 as the primary structural source, incorporating published corrections through 2026. CREAS is the primary specialized social-assistance destination category. CRAS may be analyzed as a broader social-assistance layer but must not be treated as functionally interchangeable with CREAS or specialized women's services. Worker counts, team composition, service structure and RMA attendance are not used as primary supply weights.

### Specialized VAW network — Ministry of Women / Ligue 180

The official Rede de Atendimento panel is a living national directory of services for women experiencing violence. It supplies service locations and contacts and should be used to validate specialized women's centers, DEAMs, public-defense/prosecution services and other explicitly listed services. Functional categories must be preserved. Exact confidential shelter locations must never be published.

### Justice — TJPA

The official TJPA service/contacts directory identifies specialized domestic-and-family-violence courts, including units in Belém/Icoaraci, Castanhal and Santarém. The primary justice layer should include units explicitly specialized in violence against women. General courts are not assumed to be equivalent substitutes.

## Primary supply rule

The primary supply rule is `S_j = 1` for every validated routing-ready unit. The resulting score measures territorial availability of service units relative to female population, not operational capacity. Observed capacity, staffing, structure and utilization may only support a future category-specific sensitivity study with separate justification.

Missing capacity is not imputed and is not a blocker for the primary presence-based model.

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
- `primary_supply_weight` (fixed at `1`)
- optional capacity fields retained only as provenance for future sensitivity analyses
- `reference_date`
- `validation_status`
- `redistribution_status`

Only rows with validated public locations can enter the route matrix.
