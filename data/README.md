# Data zones

Data are separated by provenance and processing stage.

- `raw/`: immutable original acquisitions. Never edit in place.
- `external/`: third-party resources managed outside the main pipeline.
- `interim/`: intermediate products that can be regenerated.
- `processed/`: analysis-ready derived products.

Large, raw, restricted, sensitive, or non-redistributable data are ignored by Git. Each zone contains its own instructions. Never commit personal data, precise confidential shelter locations, credentials, or restricted police records.
