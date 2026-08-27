# 02 — Multimodal temporal network

## Objective

The network stage creates the temporal surface-transport graph used to estimate travel time between population origins and service destinations. The reference network combines road and hydro components while preserving documented transfer structure and avoiding synthetic temporal assumptions.

## Reference design principles

The reference graph follows these safeguards:

- road and hydro edges are temporal edges, not simple cartographic proximity;
- cartographic distance is not converted to time unless a defensible temporal rule exists;
- no invented vessel speed is used;
- waiting time is excluded consistently from the reference baseline;
- ordinary-access air routing is excluded from the primary surface model;
- transfer connections must be structurally justified;
- a missing modeled transfer is not automatically interpreted as real-world isolation.

## Frozen reference backbone

The original frozen multimodal backbone contained the validated road and hydro directed edges plus exact terminal aliases and component-membership records. Three explicitly validated road–hydro transfer terminals were present in the initial frozen representation: Muaná, Soure and Moju.

This was correctly treated as a **coverage warning**, not as a statement that only those transfers exist in reality.

## Post-ranking network plausibility audit

The first Stage-4 ranking exposed two evidence-backed structural omissions that materially affected accessibility:

### Colares

A ferry transfer on the PA-238/Furo da Laura corridor was restored between frozen graph nodes:

`3648185532 <-> 3678212692`

The reference crossing impedance is 10 minutes, supported as a documented temporal reference. No additional waiting time was fabricated.

### Santa Cruz do Arari

A documented passenger-hydro connection between Santa Cruz do Arari and Belém was restored between frozen graph nodes:

`4799782642 <-> 7983414759`

The reference impedance is 420 minutes (approximately 7 h), retained as a documented reference rather than claimed as a contemporaneous measured duration. Waiting time remains excluded.

### Afuá

Afuá is retained as a coverage/scope-limited case. No sufficiently documented Pará-bound ordinary surface temporal edge was authorized under the locked reference scope, and no synthetic edge or penalty was introduced.

The detailed correction record is in [`docs/reopened_multimodal_network_audit.md`](../reopened_multimodal_network_audit.md).

## Corrected network effect

The corrected backbone adds four directed transfer edges corresponding to two bidirectional connections. These edges remove the artificial structural isolation of Colares and Santa Cruz do Arari without changing the declared network assumptions for the rest of the state.

The corrected network is the only network version authorized for downstream Stage-3/Stage-4 results.

## Executable components

Key implementation and workflow components include:

- `src/analysis/materialize_corrected_transfer_backbone.py`
- `.github/workflows/rebuild-corrected-reference-od.yml`
- the earlier frozen network assembly scripts/workflows retained in repository history/branches.

## Required visual documentation

The final network documentation bundle should contain:

1. statewide multimodal network map;
2. road-only network map;
3. hydro-only network map;
4. explicit transfer-terminal map;
5. detailed correction insets for Colares and Santa Cruz do Arari;
6. a network-construction flow diagram.

Every final cartographic figure must contain **title, legend, scale, north/orientation and source/year**. Transfer maps should also identify whether a connection belongs to the frozen original graph or to the bounded evidence-backed correction.
