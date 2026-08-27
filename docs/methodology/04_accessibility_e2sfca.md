# 04 — Accessibility and E2SFCA

## Role in the pipeline

The accessibility layer transforms origin–service travel times into measures of practical service access before municipal decision analysis. The E2SFCA implementation is designed to preserve competition between population demand and service supply while accounting for travel-time impedance.

The executable E2SFCA implementation currently exists in repository history on branch `agent/stage1-stage2-accessibility` at `src/accessibility/e2sfca.py`. This documentation makes the model logic explicit in the current methodological pathway; migration of the executable file into the consolidated branch is a reproducibility housekeeping task, not a change to the model definition.

## Inputs

For each origin `i`, service `j`, service type `k` and scenario `s`, the implementation uses:

- `t_ij`: travel time from origin to service;
- `P_i`: female population associated with origin `i`;
- `S_j`: service supply/capacity for service `j` when defensible capacity exists;
- service type, so functionally different services are not treated as substitutes;
- optional catchment threshold;
- optional travel-time decay function.

Two supply modes are implemented:

- `observed_capacity`: use an observed, defensible capacity value;
- `unit_presence`: use one unit per service when capacity data are not defensibly comparable.

## Travel-time decay

The implementation supports no decay (`w=1`) or explicit decay functions. Included options are exponential and Gaussian decay.

A generic travel-time weight is represented as:

`w_ij = f(t_ij)`

where `f(.)` is non-increasing with travel time under the selected specification.

## Step 1 — service supply-to-demand ratio

For each service `j` within service type `k` and scenario `s`, weighted demand is:

`D_j = Σ_i P_i * w_ij`

The service ratio is then:

`R_j = S_j / D_j`

when weighted demand is positive.

This means a service serving a larger weighted population has a lower supply-to-demand ratio, all else equal.

## Step 2 — origin accessibility score

For each origin `i`, the E2SFCA score within service type and scenario is:

`A_i = Σ_j R_j * w_ij`

The score therefore combines the supply-demand pressure around reachable services with travel-time impedance from the origin.

## Zero-access preservation

A critical implementation safeguard is that origins with no eligible reachable service are retained explicitly with `e2sfca_score = 0`. They are not dropped from the output.

Dropping zero-access origins would bias subsequent municipal summaries upward, especially in rural, riverine or structurally disconnected areas.

## Thresholds and scenarios

The implementation permits a maximum catchment time when a threshold is substantively justified. Scores are computed separately by scenario and service type.

Season-comparison utilities exist in the historical implementation, but flood/dry labels are not asserted in the current reference model unless temporal evidence supports those scenarios. The Stage-2 reference model explicitly avoided fabricated seasonal labels.

## Relationship to municipal MCDM indicators

E2SFCA and the municipal access indicators answer related but distinct questions.

The current core MCDM accessibility criteria are:

1. reachable-service fraction;
2. fraction of services within 120 minutes;
3. nearest reachable-service time;
4. median reachable-service time.

These are transparent municipal network-access summaries. E2SFCA adds a supply-demand accessibility perspective and should be documented as an accessibility model layer rather than silently conflated with any one of those four criteria.

## Required output documentation

The reproducibility package should publish:

- an E2SFCA two-step flow diagram;
- compact example matrices for travel time, weighted demand and service ratios;
- service-ratio summary tables;
- origin/sector E2SFCA score tables;
- municipal aggregation tables when used;
- statewide accessibility maps by service type/scenario when the corresponding model run is authoritative;
- sensitivity figures for threshold/decay/supply mode when used in the final analysis.

Every final map must include **title, legend, scale, north/orientation and source/year**.

## Code reference

Historical executable implementation:

`agent/stage1-stage2-accessibility:src/accessibility/e2sfca.py`

Core functions:

- `e2sfca(...)`
- `exponential_decay(...)`
- `gaussian_decay(...)`
- `compare_seasons(...)`

No additional E2SFCA result should be declared authoritative until its exact input OD/network version and supply specification are recorded alongside the output.
