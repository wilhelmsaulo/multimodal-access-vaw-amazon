from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def q(x: pd.Series) -> dict:
    v = pd.to_numeric(x, errors='coerce').dropna()
    if v.empty:
        return {'n': 0}
    return {
        'n': int(len(v)),
        'min': float(v.min()),
        'median': float(v.median()),
        'p90': float(v.quantile(.90)),
        'p95': float(v.quantile(.95)),
        'max': float(v.max()),
    }


def main() -> None:
    origin_ev = pd.read_csv('artifacts/origin_network_access_evidence/origin_network_access_evidence.csv.gz', low_memory=False)
    service_ev = pd.read_csv('artifacts/service_local_access_primary_motor_audit/service_local_access_to_primary_motor.csv.gz', low_memory=False)

    residual_origin_classes = {'residual_unresolved_network_gap', 'residual_hydro_priority_candidate'}
    ro = origin_ev[origin_ev['origin_access_evidence_class'].isin(residual_origin_classes)].copy()
    if len(ro) != 388:
        raise ValueError(f'Expected 388 residual origins, found {len(ro)}')

    rs = service_ev[(~service_ev['nearest_osm_node_in_primary_motor_graph'].astype(bool)) & (~service_ev['local_osm_topologically_connected_to_primary_motor'].astype(bool))].copy()
    if len(rs) != 1:
        raise ValueError(f'Expected 1 disconnected service, found {len(rs)}')

    outdir = Path('artifacts/remaining_access_residuals')
    outdir.mkdir(parents=True, exist_ok=True)
    ro.to_csv(outdir / 'residual_origins.csv.gz', index=False, compression='gzip')
    rs.to_csv(outdir / 'disconnected_service.csv', index=False)

    mun_col = 'municipality_name' if 'municipality_name' in ro.columns else None
    top_municipalities = {}
    if mun_col:
        top_municipalities = ro[mun_col].fillna('NA').value_counts().head(20).astype(int).to_dict()

    audit = {
        'residual_origin_count': int(len(ro)),
        'residual_origin_class_counts': ro['origin_access_evidence_class'].value_counts().astype(int).to_dict(),
        'residual_female_population': float(pd.to_numeric(ro.get('female_population', 0), errors='coerce').fillna(0).sum()) if 'female_population' in ro.columns else None,
        'top_residual_municipalities': top_municipalities,
        'residual_origin_distance_to_road_m': q(ro['distance_to_nearest_osm_road_m']) if 'distance_to_nearest_osm_road_m' in ro.columns else {'n': 0},
        'residual_origin_distance_to_waterway_m': q(ro['distance_to_nearest_waterway_m']) if 'distance_to_nearest_waterway_m' in ro.columns else {'n': 0},
        'disconnected_service_count': int(len(rs)),
        'disconnected_service_records': rs[[c for c in ['service_id','physical_site_id','service_type','municipality_name','address_public','nearest_osm_node_id','nearest_nonmotor_incident_highway_classes','distance_to_nearest_osm_node_m','nearest_primary_motor_node_id','distance_to_nearest_primary_motor_node_m'] if c in rs.columns]].to_dict(orient='records'),
        'distance_threshold_used_for_promotion': False,
        'hydro_candidate_promoted': False,
        'service_connector_promoted': False,
        'travel_time_assigned': False,
        'scientific_policy': (
            'Remaining access residuals are isolated for diagnosis only. Residual origin classes and the single disconnected service are preserved explicitly; '
            'no Euclidean threshold, hydro proximity, nearest-node relation, or service proximity is converted into a routing connector or travel time.'
        ),
    }
    (outdir / 'remaining_access_residuals_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
