# Multimodal Access to VAW Services in the Brazilian Amazon

Reproducible research repository for an intra-municipal framework to estimate multimodal, door-to-door travel-time accessibility of women to services that respond to violence against women (VAW) in the Brazilian Amazon.

## Research question

How do multimodal travel times to VAW protection and response services vary within and across the municipalities of Pará, and which female populations remain at greater territorial disadvantage under different operational and seasonal conditions?

## Scope

- Study area: 144 municipalities of Pará, Brazil.
- Origins: census sectors, localities, rural communities, riverine communities, or other defensible intra-municipal population points.
- Population: female resident population.
- Destinations: relevant health, social assistance, public security, justice, specialized protection, and shelter services.
- Modes: walking, road, river, transfers between modes, and air transport only in explicitly justified scenarios.
- Travel time: access + waiting + in-vehicle travel + transfer + egress.
- Scenarios: theoretical minimum, locally accessible, motorized, operational, emergency, flood season, and dry season.

## Scientific boundaries

This project measures territorial accessibility. Its outputs must not be interpreted as direct measures of violence incidence, individual risk, underreporting, service quality, or service effectiveness.

## Repository status

Initial project scaffold. Data inventories, network construction, routing, validation, and analytical outputs are not yet complete.

## Planned workflow

1. Audit the three methodological reference studies and their reusable data/code.
2. Inventory and geocode service destinations.
3. Build intra-municipal female-population origins.
4. Construct connected road–river multimodal networks.
5. Implement door-to-door travel-time scenarios.
6. Run and validate a pilot study.
7. Scale the validated workflow to Pará.
8. Estimate accessibility and intra-municipal inequality.
9. Publish reproducible data products, code, figures, and documentation.

## Data policy

Raw third-party and restricted data are not committed. Each source must be documented with provenance, reference date, license or access conditions, processing steps, and known limitations. Generated or redistributable derived products will be published only after disclosure and licensing checks.

## Repository structure

- `config/`: parameters and scenario definitions.
- `data/`: documented raw, external, interim, and processed data zones.
- `docs/`: project scope, methods, data inventory, and decisions.
- `notebooks/`: exploratory analyses only.
- `references/`: bibliographic metadata and reading notes.
- `results/`: generated figures and tables.
- `src/`: reusable data, network, accessibility, and validation code.
- `tests/`: automated checks.

## Reproducibility

Create the environment with `conda env create -f environment.yml`, activate it with `conda activate multimodal-access-vaw`, and run `pytest`. Pipeline commands will be added after the pilot workflow is implemented.

## License

Licensing is pending a review of third-party datasets and reused code. No license is granted for repository contents until an explicit license file is added.
