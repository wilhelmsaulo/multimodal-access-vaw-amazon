from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd

METRIC_CRS = 'EPSG:5880'
MOTOR_HIGHWAYS = {
    'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link',
    'tertiary','tertiary_link','unclassified','residential','living_street','service','road'
}
STREET_TYPES = {'RUA','AV','AVENIDA','TV','TRAV','TRAVESSA','ROD','RODOVIA','EST','ESTRADA','AL','ALAMEDA','PASS','PASSAGEM','PRACA','PCA','VIA','VILA','BECO','RAMAL','CAMINHO','LADEIRA','CONJUNTO'}


def norm(v: object) -> str:
    s = '' if pd.isna(v) else str(v)
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(ch for ch in s if not unicodedata.combining(ch)).upper()
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9]+', ' ', s)).strip()


def core(v: object) -> str:
    t = norm(v).split()
    while t and t[0] in STREET_TYPES:
        t=t[1:]
    return ' '.join(t)


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument('--intersection', type=Path, default=Path('artifacts/origin_cartographic_topology_intersection/origin_cartographic_topology_intersection.csv.gz'))
    p.add_argument('--street-alignment', type=Path, default=Path('artifacts/cnefe_osm_street_name_alignment/cnefe_osm_street_name_alignment.csv.gz'))
    p.add_argument('--roads', type=Path, default=Path('artifacts/multimodal_graph_inputs/roads.gpkg'))
    p.add_argument('--sectors', type=Path, default=Path('data/processed/ibge/pa_census_sectors_2022.gpkg'))
    p.add_argument('--output-dir', type=Path, default=Path('artifacts/aligned_topology_gap_residuals'))
    args=p.parse_args()

    x=pd.read_csv(args.intersection,dtype={'origin_id':'string'},low_memory=False)
    x=x[x['cartographic_topology_class'].eq('local_alignment_but_topology_gap_residual')].copy()
    s=pd.read_csv(args.street_alignment,dtype={'origin_id':'string'},low_memory=False)
    x=x.merge(s[['origin_id','representative_cnefe_street_type','representative_cnefe_street_title','representative_cnefe_street_name','strict_full_name_match_same_municipality','core_name_match_same_municipality']],on='origin_id',how='left',validate='one_to_one')
    x['municipality_code']=x['origin_id'].str[:7]
    x['full_norm']=x.apply(lambda r:norm(' '.join(str(r[c]) for c in ['representative_cnefe_street_type','representative_cnefe_street_title','representative_cnefe_street_name'] if pd.notna(r[c]) and str(r[c]).strip())),axis=1)
    x['core_norm']=x['representative_cnefe_street_name'].map(core)

    sectors=gpd.read_file(args.sectors,layer='pa_census_sectors_2022',columns=['CD_MUN','geometry'])
    mun=sectors[['CD_MUN','geometry']].dissolve(by='CD_MUN',as_index=False)
    roads=gpd.read_file(args.roads,layer='roads',columns=['osm_id','highway','name','geometry'])
    roads=roads[roads['name'].notna() & roads.geometry.notna() & ~roads.geometry.is_empty].copy()
    roads['full_norm']=roads['name'].map(norm); roads['core_norm']=roads['name'].map(core)
    roads['row_id']=roads.index.astype(int)
    rp=roads[['row_id','geometry']].copy(); rp['geometry']=rp.geometry.representative_point()
    if rp.crs!=mun.crs: rp=rp.to_crs(mun.crs)
    j=gpd.sjoin(rp,mun[['CD_MUN','geometry']],how='left',predicate='within')[['row_id','CD_MUN']]
    roads=roads.merge(j,on='row_id',how='left'); roads['municipality_code']=roads['CD_MUN'].astype('string')
    roads_m=roads.to_crs(METRIC_CRS)

    # origin geometry from CNEFE point is reconstructed using the nearest-road diagnostic fields is not sufficient;
    # use sector representative origin coordinates already carried in network evidence when available.
    # The intersection file is derived from that evidence but does not carry coordinates, so read them from CNEFE origins.
    origins=pd.read_csv('data/processed/ibge/pa_cnefe_sector_origins_2022.csv',dtype={'origin_id':'string'},low_memory=False)
    og=gpd.GeoDataFrame(origins[['origin_id']].copy(),geometry=gpd.points_from_xy(origins['longitude'],origins['latitude']),crs='EPSG:4674').to_crs(METRIC_CRS)
    points=dict(zip(og['origin_id'].astype(str),og.geometry))

    rows=[]
    for r in x.itertuples(index=False):
        cand=roads_m[roads_m['municipality_code'].astype(str).eq(str(r.municipality_code))].copy()
        strict=bool(r.strict_full_name_match_same_municipality)
        corem=bool(r.core_name_match_same_municipality)
        mask=pd.Series(False,index=cand.index)
        if strict: mask |= cand['full_norm'].eq(r.full_norm)
        if corem: mask |= cand['core_norm'].eq(r.core_norm)
        cand=cand[mask].copy()
        pt=points.get(str(r.origin_id))
        if pt is None or cand.empty:
            rows.append({'origin_id':r.origin_id,'same_name_candidate_found':False})
            continue
        cand['distance_m']=cand.geometry.distance(pt)
        q=cand.sort_values('distance_m').iloc[0]
        h=str(q['highway']) if pd.notna(q['highway']) else ''
        rows.append({'origin_id':r.origin_id,'same_name_candidate_found':True,'nearest_same_name_osm_id':q['osm_id'],'nearest_same_name_highway':h,'nearest_same_name_distance_m':float(q['distance_m']),'nearest_same_name_is_motor_class':h in MOTOR_HIGHWAYS,'same_name_candidate_count':int(len(cand))})

    out=x.merge(pd.DataFrame(rows),on='origin_id',how='left',validate='one_to_one')
    out['routing_attachment_promoted']=False
    out['travel_time_assigned']=False
    args.output_dir.mkdir(parents=True,exist_ok=True)
    out.to_csv(args.output_dir/'aligned_topology_gap_residuals.csv',index=False)
    audit={
        'residual_count':int(len(out)),
        'same_name_candidate_found_count':int(out['same_name_candidate_found'].fillna(False).sum()),
        'nearest_same_name_motor_class_count':int(out['nearest_same_name_is_motor_class'].fillna(False).sum()),
        'nearest_same_name_highway_counts':{str(k):int(v) for k,v in out['nearest_same_name_highway'].fillna('missing').value_counts().items()},
        'routing_attachment_promoted':False,
        'travel_time_assigned':False,
        'scientific_policy':'The six empirically local but OSM-topology-gap origins are audited individually against same-name OSM features in the same municipality. A motor-class same-name feature is evidence of a local topology/cartography gap only; no attachment or time is promoted by this audit.'
    }
    (args.output_dir/'aligned_topology_gap_residuals_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
