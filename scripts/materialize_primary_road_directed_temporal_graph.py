from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ARTIFACTS = Path('artifacts')
OUT = ARTIFACTS / 'primary_road_directed_temporal_graph'

FORWARD_ONEWAY = {'yes','true','1'}
REVERSE_ONEWAY = {'-1','reverse'}
EXPLICIT_TWOWAY = {'no','false','0'}


def find_unique(name: str) -> Path:
    hits=sorted(ARTIFACTS.rglob(name))
    if not hits:
        raise FileNotFoundError(name)
    return hits[0]


def norm(v: object) -> str:
    if v is None or pd.isna(v):
        return ''
    return str(v).strip().lower()


def main() -> None:
    OUT.mkdir(parents=True,exist_ok=True)
    src=find_unique('primary_motor_edges_with_times.csv.gz')
    df=pd.read_csv(src,low_memory=False)
    required={'u','v','travel_time_min','length_m','oneway','junction'}
    missing=required-set(df.columns)
    if missing:
        raise RuntimeError(f'Missing required road fields: {sorted(missing)}')
    times=pd.to_numeric(df['travel_time_min'],errors='coerce')
    if times.isna().any() or (times<=0).any():
        raise RuntimeError('All primary road source segments must have positive travel_time_min')

    rows=[]
    source_forward=source_reverse=source_twoway=0
    for idx,r in df.iterrows():
        ow=norm(r['oneway'])
        junction=norm(r['junction'])
        if ow in REVERSE_ONEWAY:
            dirs=[(r['v'],r['u'],'reverse_from_osm_oneway_minus1')]
            source_reverse+=1
        elif ow in FORWARD_ONEWAY:
            dirs=[(r['u'],r['v'],'forward_from_explicit_osm_oneway')]
            source_forward+=1
        elif ow in EXPLICIT_TWOWAY:
            dirs=[(r['u'],r['v'],'forward_from_explicit_osm_twoway'),(r['v'],r['u'],'reverse_from_explicit_osm_twoway')]
            source_twoway+=1
        elif junction in {'roundabout','circular'}:
            dirs=[(r['u'],r['v'],'forward_from_osm_roundabout_semantics')]
            source_forward+=1
        else:
            dirs=[(r['u'],r['v'],'forward_from_default_osm_twoway'),(r['v'],r['u'],'reverse_from_default_osm_twoway')]
            source_twoway+=1
        for a,b,rule in dirs:
            rec=r.to_dict()
            rec['source_edge_index']=int(idx)
            rec['from_node']=int(a)
            rec['to_node']=int(b)
            rec['direction_rule']=rule
            rec['directed_edge_id']=f'road:{idx}:{a}:{b}'
            rows.append(rec)

    out=pd.DataFrame(rows)
    out.to_csv(OUT/'primary_road_directed_edges.csv.gz',index=False,compression='gzip')

    counts=out['direction_rule'].value_counts().to_dict()
    audit={
        'source_segment_count':int(len(df)),
        'directed_edge_count':int(len(out)),
        'source_explicit_or_roundabout_oneway_count':int(source_forward),
        'source_reverse_oneway_count':int(source_reverse),
        'source_twoway_count':int(source_twoway),
        'direction_rule_counts':{str(k):int(v) for k,v in counts.items()},
        'travel_time_min_positive_all':bool(pd.to_numeric(out['travel_time_min'],errors='coerce').gt(0).all()),
        'source_travel_time_changed':False,
        'new_speed_assumption_used':False,
        'restricted_edges_promoted':False,
        'track_promoted':False,
        'scientific_policy':(
            'Primary-road source segments are expanded into directed routing edges using explicit OSM oneway semantics. '
            'oneway=yes/true/1 keeps u-to-v, oneway=-1/reverse keeps v-to-u, explicit no/false/0 creates both directions, '
            'and OSM roundabout/circular junction semantics are treated as forward one-way unless explicitly overridden. '
            'Other segments are represented in both directions. The validated source travel time is copied unchanged to each permitted direction; no new speed or time assumption is introduced.'
        )
    }
    (OUT/'primary_road_directed_temporal_graph_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
