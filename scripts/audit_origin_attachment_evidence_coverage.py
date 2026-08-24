from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def main() -> None:
    ev = pd.read_csv('artifacts/origin_network_access_evidence/origin_network_access_evidence.csv.gz', low_memory=False)
    inter = pd.read_csv('artifacts/origin_cartographic_topology_intersection/origin_cartographic_topology_intersection.csv.gz', low_memory=False)
    ped = pd.read_csv('artifacts/pedestrian_local_access_times/pedestrian_local_access_times.csv.gz', low_memory=False)

    x = ev.merge(inter[['origin_id','cartographic_topology_class']], on='origin_id', how='left')
    ped_ids = set(ped['origin_id'].astype(str))
    x['temporally_resolved_pedestrian_path'] = x['origin_id'].astype(str).isin(ped_ids)
    x['structural_attachment_resolved'] = x['cartographic_topology_class'].eq('local_alignment_and_primary_motor_topology')
    x['access_attachment_evidence_resolved'] = x['structural_attachment_resolved'] | x['temporally_resolved_pedestrian_path']

    direct = x['origin_access_evidence_class'].eq('nearest_local_osm_node_in_primary_motor_graph')
    local = x['origin_access_evidence_class'].eq('local_osm_topology_connects_to_primary_motor')
    residual = x['origin_access_evidence_class'].isin(['residual_unresolved_network_gap','residual_hydro_priority_candidate'])

    audit = {
        'origin_count': int(len(x)),
        'resolved_structural_attachment_count': int(x['structural_attachment_resolved'].sum()),
        'resolved_pedestrian_temporal_access_count': int(x['temporally_resolved_pedestrian_path'].sum()),
        'resolved_access_evidence_union_count': int(x['access_attachment_evidence_resolved'].sum()),
        'resolved_access_evidence_fraction': float(x['access_attachment_evidence_resolved'].mean()),
        'direct_primary_motor_origins_total': int(direct.sum()),
        'direct_primary_motor_with_structural_alignment': int((direct & x['structural_attachment_resolved']).sum()),
        'direct_primary_motor_without_independent_cartographic_alignment': int((direct & ~x['structural_attachment_resolved']).sum()),
        'local_path_origins_total': int(local.sum()),
        'local_path_origins_with_resolved_pedestrian_time': int((local & x['temporally_resolved_pedestrian_path']).sum()),
        'local_path_origins_remaining_unresolved': int((local & ~x['temporally_resolved_pedestrian_path']).sum()),
        'residual_origin_count': int(residual.sum()),
        'attachment_rule_fully_resolved': False,
        'nearest_primary_node_alone_promoted': False,
        'distance_cutoff_generalized_from_nominal_alignment': False,
        'scientific_policy': (
            'This audit distinguishes topological proximity from independently corroborated attachment evidence. '
            'An origin whose nearest OSM node already belongs to the primary motor graph is not treated as resolved unless independent cartographic alignment or an evidence-backed physical local path rule exists. '
            'The same-name empirical boundary is not generalized to origins lacking nominal evidence.'
        ),
    }
    out = Path('artifacts/origin_attachment_evidence_coverage')
    out.mkdir(parents=True, exist_ok=True)
    x.to_csv(out/'origin_attachment_evidence_coverage.csv.gz', index=False, compression='gzip')
    (out/'origin_attachment_evidence_coverage_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
