from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ARTIFACTS = Path('artifacts')
OUT_DEFAULT = ARTIFACTS / 'primary_road_directed_temporal_graph'
FORWARD_ONEWAY = {'yes','true','1'}
REVERSE_ONEWAY = {'-1','reverse'}
EXPLICIT_TWOWAY = {'no','false','0'}
KEEP_OPTIONAL = ['way_id','highway','speed_kmh','speed_source','surface']


def norm_series(s: pd.Series) -> pd.Series:
    return s.fillna('').astype(str).str.strip().str.lower()


def directed_frame(src: pd.DataFrame, from_col: str, to_col: str, rule: str) -> pd.DataFrame:
    cols=['source_edge_index','travel_time_min','length_m']+[c for c in KEEP_OPTIONAL if c in src.columns]
    out=src[cols].copy()
    out['from_node']=pd.to_numeric(src[from_col],errors='raise').astype('int64').to_numpy()
    out['to_node']=pd.to_numeric(src[to_col],errors='raise').astype('int64').to_numpy()
    out['direction_rule']=rule
    out['directed_edge_id']='road:'+out['source_edge_index'].astype(str)+':'+out['from_node'].astype(str)+':'+out['to_node'].astype(str)
    return out


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument('--edges',type=Path,default=ARTIFACTS/'primary_motor_edges_with_complete_times.csv.gz')
    p.add_argument('--output-dir',type=Path,default=OUT_DEFAULT)
    args=p.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    if not args.edges.exists():
        raise FileNotFoundError(args.edges)

    df=pd.read_csv(args.edges,low_memory=False)
    required={'u','v','travel_time_min','length_m','oneway','junction'}
    missing=required-set(df.columns)
    if missing:
        raise RuntimeError(f'Missing required road fields: {sorted(missing)}')
    times=pd.to_numeric(df['travel_time_min'],errors='coerce')
    if times.isna().any() or (times<=0).any():
        raise RuntimeError('All primary road source segments must have positive travel_time_min')
    df=df.copy()
    df['travel_time_min']=times
    df['length_m']=pd.to_numeric(df['length_m'],errors='coerce')
    df['source_edge_index']=np.arange(len(df),dtype=np.int64)

    ow=norm_series(df['oneway'])
    junction=norm_series(df['junction'])
    m_rev=ow.isin(REVERSE_ONEWAY)
    m_fwd=ow.isin(FORWARD_ONEWAY)
    m_explicit_two=ow.isin(EXPLICIT_TWOWAY)
    m_round=(~m_rev & ~m_fwd & ~m_explicit_two & junction.isin({'roundabout','circular'}))
    m_default_two=~(m_rev|m_fwd|m_explicit_two|m_round)

    frames=[
        directed_frame(df.loc[m_rev],'v','u','reverse_from_osm_oneway_minus1'),
        directed_frame(df.loc[m_fwd],'u','v','forward_from_explicit_osm_oneway'),
        directed_frame(df.loc[m_round],'u','v','forward_from_osm_roundabout_semantics'),
        directed_frame(df.loc[m_explicit_two],'u','v','forward_from_explicit_osm_twoway'),
        directed_frame(df.loc[m_explicit_two],'v','u','reverse_from_explicit_osm_twoway'),
        directed_frame(df.loc[m_default_two],'u','v','forward_from_default_osm_twoway'),
        directed_frame(df.loc[m_default_two],'v','u','reverse_from_default_osm_twoway'),
    ]
    out=pd.concat(frames,ignore_index=True)
    out.to_csv(args.output_dir/'primary_road_directed_edges.csv.gz',index=False,compression='gzip')

    counts=out['direction_rule'].value_counts().to_dict()
    audit={
        'input_edges_file':str(args.edges),
        'source_segment_count':int(len(df)),
        'directed_edge_count':int(len(out)),
        'source_explicit_or_roundabout_oneway_count':int((m_fwd|m_round).sum()),
        'source_reverse_oneway_count':int(m_rev.sum()),
        'source_twoway_count':int((m_explicit_two|m_default_two).sum()),
        'direction_rule_counts':{str(k):int(v) for k,v in counts.items()},
        'travel_time_min_positive_all':bool(pd.to_numeric(out['travel_time_min'],errors='coerce').gt(0).all()),
        'source_travel_time_changed':False,
        'new_speed_assumption_used':False,
        'restricted_edges_promoted':False,
        'track_promoted':False,
        'output_columns':list(out.columns),
        'scientific_policy':(
            'Primary-road source segments are expanded into directed routing edges using explicit OSM oneway semantics. '
            'oneway=yes/true/1 keeps u-to-v, oneway=-1/reverse keeps v-to-u, explicit no/false/0 creates both directions, '
            'and OSM roundabout/circular junction semantics are treated as forward one-way unless explicitly overridden. '
            'Other segments are represented in both directions. Validated source travel time is copied unchanged to each permitted direction; no new speed or time assumption is introduced.'
        )
    }
    (args.output_dir/'primary_road_directed_temporal_graph_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
