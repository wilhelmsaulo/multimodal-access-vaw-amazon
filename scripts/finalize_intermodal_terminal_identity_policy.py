from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ARTIFACTS = Path('artifacts')
OUT = ARTIFACTS / 'intermodal_terminal_identity_policy'


def find_unique(name: str) -> Path:
    hits = sorted(ARTIFACTS.rglob(name))
    if not hits:
        raise FileNotFoundError(name)
    return hits[0]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    anchors = pd.read_csv(find_unique('validated_spatial_transfer_anchors.csv'))
    comparison = pd.read_csv(find_unique('front1_anchor_positive_control_comparison.csv'))
    hydro_attach = pd.read_csv(find_unique('validated_anchor_hydro_node_attachments.csv'))

    merged = anchors.merge(
        comparison[['port_name','positive_control_geometry_consistent']],
        on='port_name', how='left', validate='one_to_one'
    ).merge(
        hydro_attach[['anchor_id','hydro_node_id']],
        on='anchor_id', how='left', validate='one_to_one'
    )

    required = {'Muaná','Soure','Moju'}
    if set(merged['port_name']) != required:
        raise RuntimeError(f'Unexpected validated anchor set: {set(merged["port_name"])}')
    if not merged['validation_basis'].astype(str).str.contains('official_endpoint_match').all():
        raise RuntimeError('All terminal identities require official endpoint match evidence')
    if not merged['positive_control_geometry_consistent'].fillna(False).all():
        raise RuntimeError('All terminal identities require positive-control geometric consistency')
    if merged['hydro_node_id'].isna().any():
        raise RuntimeError('All terminal identities require a validated hydro topology node')

    merged['terminal_identity_adopted'] = True
    merged['identity_basis'] = 'official_antaq_terminal_endpoint_semantic_identity'
    merged['creates_temporal_edge'] = False
    merged['transfer_time_assigned'] = False
    merged['zero_time_edge_created'] = False
    merged['cartographic_offset_interpreted_as_physical_travel'] = False
    merged['distance_to_time_conversion_used'] = False
    merged.to_csv(OUT/'intermodal_terminal_identity_policy.csv', index=False)

    audit = {
        'validated_terminal_count': int(len(merged)),
        'terminal_names': merged['port_name'].tolist(),
        'official_endpoint_match_all': True,
        'positive_control_geometry_consistent_all': True,
        'semantic_identity_adopted_all': True,
        'creates_temporal_edge': False,
        'transfer_time_assigned': False,
        'zero_time_edge_created': False,
        'cartographic_offset_interpreted_as_physical_travel': False,
        'distance_to_time_conversion_used': False,
        'scientific_policy': (
            'For the three previously validated ANTAQ transfer terminals, the official terminal and the matched official route endpoint are represented as one semantic terminal identity across terrestrial and hydro layers. '
            'This decision is based on official endpoint matching and positive-control geometric consistency, not on a distance threshold. '
            'The cartographic terminal-to-route offset is not interpreted as physical travel, no connector edge is created, and no transfer time or zero-minute edge is encoded. '
            'Waiting and schedule-related transfer delay remain excluded from the primary impedance model and are reported as a limitation.'
        )
    }
    (OUT/'intermodal_terminal_identity_policy_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
