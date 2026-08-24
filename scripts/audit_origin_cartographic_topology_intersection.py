from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--alignment', type=Path, default=Path('artifacts/empirical_origin_cartographic_alignment/empirical_origin_cartographic_alignment.csv.gz'))
    p.add_argument('--network-evidence', type=Path, default=Path('artifacts/origin_network_access_evidence/origin_network_access_evidence.csv.gz'))
    p.add_argument('--output-dir', type=Path, default=Path('artifacts/origin_cartographic_topology_intersection'))
    args = p.parse_args()

    a = pd.read_csv(args.alignment, dtype={'origin_id': 'string'}, low_memory=False)
    n = pd.read_csv(args.network_evidence, dtype={'origin_id': 'string'}, low_memory=False)
    keep = ['origin_id', 'empirical_local_cartographic_alignment', 'distance_to_any_same_name_osm_m', 'empirical_alignment_boundary_m']
    x = n.merge(a[keep], on='origin_id', how='left', validate='one_to_one')
    x['empirical_local_cartographic_alignment'] = x['empirical_local_cartographic_alignment'].fillna(False).astype(bool)

    aligned = x['empirical_local_cartographic_alignment']
    direct = x['origin_access_evidence_class'].eq('nearest_local_osm_node_in_primary_motor_graph')
    local = x['origin_access_evidence_class'].eq('local_osm_topology_connects_to_primary_motor')
    residual_h = x['origin_access_evidence_class'].eq('residual_hydro_priority_candidate')
    residual_u = x['origin_access_evidence_class'].eq('residual_unresolved_network_gap')

    x['cartographic_topology_class'] = 'outside_empirical_local_alignment_regime'
    x.loc[aligned & direct, 'cartographic_topology_class'] = 'local_alignment_and_primary_motor_topology'
    x.loc[aligned & local, 'cartographic_topology_class'] = 'local_alignment_but_physical_local_osm_path_required'
    x.loc[aligned & residual_h, 'cartographic_topology_class'] = 'local_alignment_but_hydro_priority_residual'
    x.loc[aligned & residual_u, 'cartographic_topology_class'] = 'local_alignment_but_topology_gap_residual'

    # This audit does not yet materialize a routing attachment. It only identifies the subset
    # for which non-temporal cartographic attachment is methodologically eligible for the next step.
    x['eligible_for_non_temporal_cartographic_attachment_audit'] = aligned & direct
    x['non_temporal_cartographic_attachment_materialized'] = False
    x['physical_local_access_still_required'] = aligned & (local | residual_h | residual_u)
    x['travel_time_assigned'] = False
    x['euclidean_distance_converted_to_time'] = False

    args.output_dir.mkdir(parents=True, exist_ok=True)
    x.to_csv(args.output_dir / 'origin_cartographic_topology_intersection.csv.gz', index=False, compression='gzip')

    counts = x['cartographic_topology_class'].value_counts().to_dict()
    female = pd.to_numeric(x.get('female_population'), errors='coerce')
    female_by_class = {
        str(k): float(female[x['cartographic_topology_class'].eq(k)].sum()) for k in counts
    }
    local_paths = pd.to_numeric(x.loc[aligned & local, 'local_osm_path_distance_to_primary_motor_m'], errors='coerce').dropna()
    audit = {
        'origin_count': int(len(x)),
        'empirical_local_alignment_count': int(aligned.sum()),
        'aligned_primary_motor_topology_count': int((aligned & direct).sum()),
        'aligned_local_osm_path_required_count': int((aligned & local).sum()),
        'aligned_hydro_priority_residual_count': int((aligned & residual_h).sum()),
        'aligned_topology_gap_residual_count': int((aligned & residual_u).sum()),
        'eligible_for_non_temporal_cartographic_attachment_audit_count': int((aligned & direct).sum()),
        'cartographic_topology_class_counts': {str(k): int(v) for k, v in counts.items()},
        'female_population_by_cartographic_topology_class': female_by_class,
        'aligned_local_osm_path_distance_m_quantiles': {
            'min': float(local_paths.min()) if not local_paths.empty else None,
            'median': float(local_paths.median()) if not local_paths.empty else None,
            'p75': float(local_paths.quantile(.75)) if not local_paths.empty else None,
            'p90': float(local_paths.quantile(.90)) if not local_paths.empty else None,
            'p95': float(local_paths.quantile(.95)) if not local_paths.empty else None,
            'max': float(local_paths.max()) if not local_paths.empty else None,
        },
        'hydro_priority_origin_absorbed_by_cartographic_alignment_count': int((aligned & residual_h).sum()),
        'non_temporal_cartographic_attachment_materialized': False,
        'travel_time_assigned': False,
        'euclidean_distance_converted_to_time': False,
        'scientific_policy': (
            'The empirically supported same-street local alignment regime is intersected with independently audited OSM topology. '
            'Only origins already topologically represented in the primary motor graph become eligible for a subsequent non-temporal cartographic attachment audit. '
            'Origins requiring local OSM paths or remaining residual retain explicit physical-access status. Hydro-priority residuals are not overridden. '
            'No travel time, straight-line speed conversion, or routing attachment is created here.'
        ),
    }
    (args.output_dir / 'origin_cartographic_topology_intersection_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
