from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd

WATERWAYS = Path('artifacts/multimodal_graph_inputs/waterways.gpkg')
OBS = Path('artifacts/antaq_hydro_temporal_observations_pa/antaq_hydro_temporal_observations_pa.csv.gz')
OUT = Path('artifacts/hydro_temporal_matching_pa')


def norm(v: object) -> str:
    if v is None or pd.isna(v):
        return ''
    s = unicodedata.normalize('NFKD', str(v)).encode('ascii', 'ignore').decode().lower().strip()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def find_col(cols, names):
    low = {c.lower(): c for c in cols}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    w = gpd.read_file(WATERWAYS, layer='waterways').reset_index(drop=True)
    o = pd.read_csv(OBS, low_memory=False)
    cols = [str(c) for c in w.columns if c != 'geometry']

    hid = find_col(cols, ('idhidrovia','idantaq','hydro_id'))
    river = find_col(cols, ('nome_rio','river_name','nome'))
    mo = find_col(cols, ('mun_origem','origin_municipality'))
    md = find_col(cols, ('mun_estino','destination_municipality'))

    obs = o.copy()
    obs['hid_n'] = obs['hydro_id'].map(norm)
    obs['river_n'] = obs['river_name'].map(norm)
    obs['mo_n'] = obs['origin_municipality'].map(norm)
    obs['md_n'] = obs['destination_municipality'].map(norm)

    id_map = {}
    for k, g in obs[obs.hid_n.ne('')].groupby('hid_n'):
        vals = g['travel_time_min_observed'].dropna().unique()
        if len(vals) == 1:
            id_map[k] = float(vals[0])

    key_map = {}
    obs['route_key'] = obs['river_n']+'|'+obs['mo_n']+'|'+obs['md_n']
    for k, g in obs[obs.route_key.ne('||')].groupby('route_key'):
        vals = g['travel_time_min_observed'].dropna().unique()
        if len(vals) == 1:
            key_map[k] = float(vals[0])

    rows=[]
    for i,r in w.iterrows():
        h = norm(r[hid]) if hid else ''
        rk = '|'.join([norm(r[river]) if river else '', norm(r[mo]) if mo else '', norm(r[md]) if md else ''])
        t=None; method='unmatched'
        if h and h in id_map:
            t=id_map[h]; method='exact_hydro_id'
        elif rk in key_map and rk != '||':
            t=key_map[rk]; method='exact_river_origin_destination'
        rows.append({'waterway_index':i,'travel_time_min_observed':t,'match_method':method})
    m=pd.DataFrame(rows)
    m.to_csv(OUT/'waterway_temporal_match_audit.csv',index=False)
    vc=m.match_method.value_counts().to_dict()
    matched=int(m.travel_time_min_observed.notna().sum())
    audit={
        'canonical_waterway_segments':int(len(w)),
        'observed_temporal_rows':int(len(obs)),
        'matched_segments':matched,
        'unmatched_segments':int(len(w)-matched),
        'matched_fraction':float(matched/len(w)) if len(w) else None,
        'match_method_counts':{str(k):int(v) for k,v in vc.items()},
        'canonical_columns':cols,
        'detected_fields':{'hydro_id':hid,'river':river,'origin_municipality':mo,'destination_municipality':md},
        'policy':'Only unique exact identifier or exact normalized river-origin-destination matches are accepted. No fuzzy or nearest-geometric match is promoted and no unmatched segment receives imputed time.',
        'time_imputation_applied':False,
        'ready_for_hydro_matching_model_decision':True,
    }
    (OUT/'hydro_temporal_matching_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
