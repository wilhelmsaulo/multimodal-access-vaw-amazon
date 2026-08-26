from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def weak_components_numeric(a: pd.Series, b: pd.Series):
    vals = pd.concat([a, b], ignore_index=True)
    codes, uniques = pd.factorize(vals, sort=False)
    n = len(uniques)
    m = len(a)
    u = codes[:m]
    v = codes[m:]
    data = np.ones(m * 2, dtype=np.uint8)
    mat = coo_matrix((data, (np.r_[u, v], np.r_[v, u])), shape=(n, n)).tocsr()
    count, labels = connected_components(mat, directed=False, return_labels=True)
    return uniques, labels, int(count)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--road-directed', type=Path, default=Path('artifacts/road_directed/primary_road_directed_edges.csv.gz'))
    p.add_argument('--terminal-splits', type=Path, default=Path('artifacts/terminal_splits/intermodal_terminal_road_edge_splits.csv'))
    p.add_argument('--hydro-topology', type=Path, default=Path('artifacts/hydro/hydro_topology_edges.gpkg'))
    p.add_argument('--output-dir', type=Path, default=Path('artifacts/frozen_final_multimodal_backbone'))
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    road = pd.read_csv(args.road_directed, low_memory=False)
    splits = pd.read_csv(args.terminal_splits)
    hydro = gpd.read_file(args.hydro_topology, layer='hydro_topology_edges')

    req_road = {'from_node','to_node','travel_time_min','way_id','source_edge_index'}
    if not req_road.issubset(road.columns):
        raise RuntimeError(f'Missing road fields: {sorted(req_road-set(road.columns))}')
    req_h = {'from_node','to_node','travel_time_min'}
    if not req_h.issubset(hydro.columns):
        raise RuntimeError(f'Missing hydro fields: {sorted(req_h-set(hydro.columns))}')
    if len(splits) != 3:
        raise RuntimeError(f'Expected 3 terminal splits, got {len(splits)}')

    road['from_node'] = pd.to_numeric(road['from_node'], errors='raise').astype('int64')
    road['to_node'] = pd.to_numeric(road['to_node'], errors='raise').astype('int64')
    road['way_id'] = pd.to_numeric(road['way_id'], errors='raise').astype('int64')
    road['source_edge_index'] = pd.to_numeric(road['source_edge_index'], errors='raise').astype('int64')
    road['travel_time_min'] = pd.to_numeric(road['travel_time_min'], errors='raise')
    if not road['travel_time_min'].gt(0).all():
        raise RuntimeError('Road directed graph contains non-positive times')

    replacement_rows = []
    remove = pd.Series(False, index=road.index)
    terminal_meta = []
    for _, s in splits.iterrows():
        u, v, w = int(s.source_u), int(s.source_v), int(s.source_way_id)
        mask = road['way_id'].eq(w) & (
            (road['from_node'].eq(u) & road['to_node'].eq(v))
            | (road['from_node'].eq(v) & road['to_node'].eq(u))
        )
        src = road.loc[mask]
        if src.empty:
            raise RuntimeError(f'No directed source edge found for terminal {s.port_name}')
        # A source OSM segment can contribute one or two directed edges depending on
        # oneway semantics. The matched rows must all refer to one source_edge_index.
        if src['source_edge_index'].nunique() != 1:
            raise RuntimeError(f'Ambiguous directed source segment for terminal {s.port_name}')
        remove |= mask
        term = f"terminal:{s.anchor_id}"
        t1, t2 = float(s.u_to_terminal_time_min), float(s.terminal_to_v_time_min)
        for r in src.itertuples(index=False):
            a, b = int(r.from_node), int(r.to_node)
            if a == u and b == v:
                pieces = [(str(u), term, t1), (term, str(v), t2)]
            elif a == v and b == u:
                pieces = [(str(v), term, t2), (term, str(u), t1)]
            else:
                raise RuntimeError(f'Unexpected directed orientation for terminal {s.port_name}: {a}->{b}')
            for x, y, t in pieces:
                replacement_rows.append({'from_node':x,'to_node':y,'travel_time_min':t,'mode':'road','edge_role':'terminal_split'})
        terminal_meta.append({
            'anchor_id':str(s.anchor_id),
            'port_name':str(s.port_name),
            'terminal_node_id':term,
            'hydro_node_id':str(s.hydro_node_id),
            'source_u':u,
            'source_v':v,
            'source_way_id':w,
            'source_edge_index':int(src['source_edge_index'].iloc[0]),
            'directed_source_edges_replaced':int(len(src)),
        })

    base = road.loc[~remove, ['from_node','to_node','travel_time_min']].copy()
    base['from_node'] = base['from_node'].astype(str)
    base['to_node'] = base['to_node'].astype(str)
    base['mode'] = 'road'
    base['edge_role'] = 'validated_primary_road'
    road_final = pd.concat([base, pd.DataFrame(replacement_rows)], ignore_index=True)
    if not pd.to_numeric(road_final['travel_time_min'], errors='coerce').gt(0).all():
        raise RuntimeError('Final road graph contains non-positive times')

    alias = {x['hydro_node_id']: x['terminal_node_id'] for x in terminal_meta}
    hbase = hydro[['from_node','to_node','travel_time_min']].copy()
    hbase['travel_time_min'] = pd.to_numeric(hbase['travel_time_min'], errors='raise')
    if not hbase['travel_time_min'].gt(0).all():
        raise RuntimeError('Hydro topology contains non-positive times')
    hbase['from_node'] = hbase['from_node'].astype(str).replace(alias)
    hbase['to_node'] = hbase['to_node'].astype(str).replace(alias)
    hrev = hbase.rename(columns={'from_node':'to_node','to_node':'from_node'})[['from_node','to_node','travel_time_min']]
    hydro_final = pd.concat([hbase, hrev], ignore_index=True)
    hydro_final['mode'] = 'hydro'
    hydro_final['edge_role'] = 'official_antaq_reference_bidirectional'

    road_final.to_csv(args.output_dir/'final_road_directed_edges.csv.gz', index=False, compression='gzip')
    hydro_final.to_csv(args.output_dir/'final_hydro_directed_edges.csv.gz', index=False, compression='gzip')
    pd.DataFrame(terminal_meta).to_csv(args.output_dir/'terminal_node_aliases.csv', index=False)

    # Connectivity is computed on the original numeric road backbone because splitting
    # an interior source edge preserves its weak component exactly.
    road_uniques, road_labels, road_cc = weak_components_numeric(road['from_node'], road['to_node'])
    road_label = pd.Series(road_labels, index=road_uniques)
    hydro_uniques, hydro_labels, hydro_cc = weak_components_numeric(hydro_final['from_node'], hydro_final['to_node'])
    hydro_label = pd.Series(hydro_labels, index=hydro_uniques)

    terminal_components = []
    for x in terminal_meta:
        rc = int(road_label.loc[x['source_u']])
        hc = int(hydro_label.loc[x['terminal_node_id']])
        terminal_components.append({**x,'road_weak_component':rc,'hydro_weak_component':hc})
    tc = pd.DataFrame(terminal_components)
    tc.to_csv(args.output_dir/'terminal_component_membership.csv', index=False)

    audit = {
        'road_source_directed_edges': int(len(road)),
        'road_source_directed_edges_replaced': int(remove.sum()),
        'road_terminal_split_directed_edges_created': int(len(replacement_rows)),
        'road_final_directed_edges': int(len(road_final)),
        'hydro_source_topology_edges': int(len(hydro)),
        'hydro_final_directed_edges': int(len(hydro_final)),
        'terminal_identity_count': int(len(alias)),
        'terminal_identity_zero_time_edges_created': False,
        'road_weak_component_count': road_cc,
        'hydro_weak_component_count_before_road_union': hydro_cc,
        'terminals_with_road_component': int(tc['road_weak_component'].notna().sum()),
        'terminals_with_hydro_component': int(tc['hydro_weak_component'].notna().sum()),
        'road_time_positive_all': bool(pd.to_numeric(road_final['travel_time_min']).gt(0).all()),
        'hydro_time_positive_all': bool(pd.to_numeric(hydro_final['travel_time_min']).gt(0).all()),
        'waiting_time_included': False,
        'air_temporal_routing_included': False,
        'new_speed_assumption_used': False,
        'cartographic_distance_converted_to_time': False,
        'ready_for_origin_service_attachment_and_od': True,
        'scientific_policy': (
            'This frozen backbone consumes only previously validated artifacts. Three terminal road edges are replaced by conservative time-preserving splits. '
            'The validated terminal identity aliases the corresponding official ANTAQ hydro node to the same graph node; no zero-time connector edge is created. '
            'Hydro topology is expanded bidirectionally with the same official network-reference impedance, consistent with the locked traversal policy. '
            'No upstream CNEFE, OSM, ANTAQ, service, speed, or attachment audit is recomputed.'
        ),
    }
    (args.output_dir/'frozen_final_multimodal_backbone_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
