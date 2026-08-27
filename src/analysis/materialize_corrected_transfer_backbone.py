from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

PATCHES = [
    {
        'name': 'Colares - Penhalonga',
        'from_node': '3648185532',
        'to_node': '3678212692',
        'travel_time_min': 10.0,
        'mode': 'ferry',
        'edge_role': 'evidence_backed_reopened_transfer',
        'evidence': 'OSM ferry way 360220760 + documented local crossing duration approximately 10 min',
    },
    {
        'name': 'Belém - Santa Cruz do Arari',
        'from_node': '4799782642',
        'to_node': '7983414759',
        'travel_time_min': 420.0,
        'mode': 'scheduled_passenger_hydro',
        'edge_role': 'evidence_backed_reopened_transfer',
        'evidence': 'OSM ferry way 977036991 + official TRE-PA approximately 7 h launch reference',
    },
]


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument('--backbone-dir', type=Path, default=Path('artifacts/backbone'))
    p.add_argument('--output-dir', type=Path, default=Path('artifacts/corrected_backbone'))
    args=p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    road_path=args.backbone_dir/'final_road_directed_edges.csv.gz'
    hydro_path=args.backbone_dir/'final_hydro_directed_edges.csv.gz'
    if not road_path.exists() or not hydro_path.exists():
        raise FileNotFoundError('Frozen backbone files are incomplete')

    # Confirm every patch endpoint already exists in the frozen road-node namespace.
    needed={x for pch in PATCHES for x in (pch['from_node'],pch['to_node'])}
    found=set()
    for c in pd.read_csv(road_path, usecols=['from_node','to_node'], dtype=str, chunksize=600_000):
        found.update(set(c['from_node']).intersection(needed))
        found.update(set(c['to_node']).intersection(needed))
    missing=sorted(needed-found)
    if missing:
        raise RuntimeError(f'Patch endpoints missing from frozen road graph: {missing}')

    out_road=args.output_dir/'final_road_directed_edges.csv.gz'
    first=True
    original_rows=0
    for c in pd.read_csv(road_path, dtype={'from_node':str,'to_node':str}, chunksize=600_000):
        original_rows += len(c)
        c.to_csv(out_road,index=False,compression='gzip',mode='wt' if first else 'at',header=first)
        first=False

    rows=[]
    for pch in PATCHES:
        for a,b in [(pch['from_node'],pch['to_node']),(pch['to_node'],pch['from_node'])]:
            rows.append({
                'from_node':a,
                'to_node':b,
                'travel_time_min':pch['travel_time_min'],
                'mode':pch['mode'],
                'edge_role':pch['edge_role'],
            })
    pd.DataFrame(rows).to_csv(out_road,index=False,compression='gzip',mode='at',header=False)

    # Preserve the frozen hydro file byte-for-byte at the semantic level (decompress/recompress not needed).
    import shutil
    shutil.copy2(hydro_path,args.output_dir/'final_hydro_directed_edges.csv.gz')

    patch_manifest=[]
    for pch in PATCHES:
        patch_manifest.append({**pch,'bidirectional':True,'waiting_time_min':0.0,'waiting_time_included':False})
    audit={
        'source_frozen_backbone_run_id':32920014705,
        'original_road_directed_edges':int(original_rows),
        'added_directed_edges':len(rows),
        'corrected_road_directed_edges':int(original_rows+len(rows)),
        'patches':patch_manifest,
        'all_patch_endpoints_preexisting_in_frozen_graph':True,
        'synthetic_speed_used':False,
        'distance_converted_to_time':False,
        'waiting_time_included':False,
        'afua_edge_added':False,
        'scientific_policy':(
            'This is a bounded reopening of the frozen Stage-2 backbone. Only two real-world transfers whose topology and temporal '
            'impedance are independently documented are materialized. All four endpoints are exact OSM ferry-terminal nodes already '
            'present in the frozen road namespace, so no spatial snap, zero-time connector, distance-to-time conversion or new speed '
            'assumption is introduced. Afuá remains coverage/scope-limited and receives no synthetic edge.'
        ),
    }
    (args.output_dir/'corrected_backbone_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
