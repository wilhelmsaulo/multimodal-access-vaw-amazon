# 03 — Origin–destination matrix

## Objective

The OD stage evaluates temporal accessibility between routing-ready population origins and the frozen service universe using the corrected multimodal network.

## Authoritative corrected run

The authoritative corrected OD workflow is run `33089335405` (`rebuild-corrected-reference-od`).

Reference dimensions:

- routing-ready origins: **12,673**;
- service destinations: **225**;
- OD pairs: **2,851,425**;
- reachable pairs: **1,542,802**;
- unreachable pairs: **1,308,623**.

The OD matrix is therefore sparse in the substantive sense that not every origin can reach every modeled service through the declared reference network.

## Interpretation of reachability

`reachable` means that a valid temporal path exists in the declared multimodal graph. `unreachable` means that the graph contains no authorized path under the current model scope.

Unreachability must not be read automatically as real-world physical isolation. It can reflect model-scope limitations, missing defensible temporal evidence or service destinations outside the declared reference universe.

## Special cases after correction

### Colares

- origin–service pairs: 7,425;
- reachable: 4,851;
- corrected status: routed/reachable.

### Santa Cruz do Arari

- origin–service pairs: 1,800;
- reachable: 1,176;
- corrected status: routed/reachable.

### Afuá

Afuá has no routing-ready origin under the locked Pará-only ordinary-surface model. It is reported as a coverage/scope limitation rather than assigned synthetic OD times.

## Downstream use

The OD matrix supports two related analytical uses:

1. construction of municipal accessibility indicators used in MCDM;
2. accessibility/E2SFCA calculations where origin–service travel times are combined with population and service supply definitions.

The OD matrix is not itself a priority score.

## Reproducibility components

- `.github/workflows/rebuild-corrected-reference-od.yml`
- `src/analysis/generate_corrected_reference_od.py`
- corrected network materialization described in [`02_multimodal_network.md`](02_multimodal_network.md)

## Required published artifacts

The documentation bundle should expose:

- OD summary table;
- reachability counts by municipality;
- distribution of finite travel times;
- map of municipal reachable-service fractions;
- map of nearest reachable-service time;
- compact extract/example of the OD matrix with a clear note that the full matrix is much larger.

Maps must include **title, legend, scale, north/orientation and source/year**.
