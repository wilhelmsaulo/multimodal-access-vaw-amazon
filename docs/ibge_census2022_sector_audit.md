# IBGE Census 2022 census-sector input audit

Audit date: 2026-08-17

## Official inputs acquired

| Input | Size | SHA-256 |
|---|---:|---|
| `PA_setores_CD2022.gpkg` | approximately 44 MB | `de6fd053e6705285895e7f8f4583fcdc4a8d97a355495e86fa9474175c39568e` |
| `Agregados_por_setores_demografia_BR.zip` | approximately 22 MB | `f8486233ce2f6559de76299390577c58d05f35cad07c46098e6e565949c8b269` |
| `dicionario_de_dados_agregados_por_setores_censitarios_20260520.xlsx` | approximately 116 KB | `0b8aedece57f6125d785b6aa2234cfd587e92dfb6ce5ca6ace8c67f140831344` |

Raw files are ignored by Git. URLs and checksums are declared in
`config/ibge_census2022_sectors.yml`.

## Confirmed variables

| Variable | Official description | Use |
|---|---|---|
| `V01006` | Quantidade de moradores | Total population check |
| `V01007` | Sexo masculino | Male population check |
| `V01008` | Sexo feminino | Primary female-population weight |
| `V01020`–`V01030` | Female population by age group | Optional stratified analyses |

The primary female-population value is `V01008`. Age groups must not be summed
as a replacement because some sector-level age cells are unavailable while the
female total remains available.

## Observed structure for Pará

- 18,635 source geometry features;
- 16,714 unique census-sector codes;
- 248 census sectors represented by more than one geometry feature;
- 1,921 geometry features beyond the unique-sector count;
- maximum of 247 geometry parts associated with one sector code;
- 144 municipalities;
- CRS EPSG:4674, SIRGAS 2000;
- 16,065 demographic rows for Pará;
- no duplicated demographic sector key;
- 649 geometry sectors absent from the demographic file, all with basic
  population `v0001 = 0`;
- 486 demographic rows with female population unavailable;
- 4,065,139 women across sectors where `V01008` is observed;
- 4,037,539 men across sectors where `V01007` is observed;
- no inconsistency in `total = male + female` where all three values exist.

## Processing decisions

1. Dissolve geometry by `CD_SETOR` before joining population.
2. Use `V01008` directly as the female-population weight.
3. Assign zero only to geometry-only sectors whose official basic population is zero.
4. Preserve unavailable female values as missing.
5. Do not infer a missing female count by subtracting male from total.
6. Label every sector with a population-data status.
7. Validate the 144 municipalities and one-to-one sector join.
8. Do not use polygon centroids as final population origins without a separate
   inhabited-location assessment.

## Remaining issue

The sector polygons and population weights are sufficient to establish the
intra-municipal analytical universe. They do not yet identify the best origin
point inside large rural and riverine sectors. That requires the next stage:
testing representative points against IBGE localities, CNEFE addresses,
settlements, buildings, or another defensible inhabited-location layer.
