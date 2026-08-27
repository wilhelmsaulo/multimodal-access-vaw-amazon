from __future__ import annotations

import json
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

OVERPASS = 'https://overpass-api.de/api/interpreter'
NOMINATIM = 'https://nominatim.openstreetmap.org/search'
UA = 'multimodal-access-vaw-amazon/1.0 research audit'


def get_json(url: str, params: dict | None = None, timeout: int = 120):
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def post_overpass(query: str):
    data = urllib.parse.urlencode({'data': query}).encode()
    req = urllib.request.Request(OVERPASS, data=data, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def hav(lat1, lon1, lat2, lon2):
    r=6371000.0
    p1,p2=math.radians(lat1),math.radians(lat2)
    dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))


def nearby_osm_nodes(lat: float, lon: float, radius: int=4000):
    q=f'''[out:json][timeout:90];(
      way(around:{radius},{lat},{lon})[highway];
      way(around:{radius},{lat},{lon})[route=ferry];
      node(around:{radius},{lat},{lon})[amenity=ferry_terminal];
      node(around:{radius},{lat},{lon})[public_transport];
    );(._;>;);out body;'''
    d=post_overpass(q)
    nodes={}
    ways=[]
    for e in d.get('elements',[]):
        if e['type']=='node': nodes[int(e['id'])]=(float(e['lat']),float(e['lon']),e.get('tags',{}))
        elif e['type']=='way': ways.append({'id':int(e['id']),'nodes':[int(x) for x in e.get('nodes',[])],'tags':e.get('tags',{})})
    return nodes,ways


def geocode(q: str):
    return get_json(NOMINATIM, {'q':q,'format':'jsonv2','limit':5,'countrycodes':'br'})


def graph_nodes(path: Path):
    vals=set()
    for c in pd.read_csv(path,usecols=['from_node','to_node'],chunksize=500_000):
        vals.update(pd.to_numeric(c['from_node'],errors='coerce').dropna().astype('int64').tolist())
        vals.update(pd.to_numeric(c['to_node'],errors='coerce').dropna().astype('int64').tolist())
    return vals


def nearest_graph_node(nodes: dict, gnodes: set[int], lat: float, lon: float):
    best=None
    for nid,(nlat,nlon,tags) in nodes.items():
        if nid not in gnodes:
            continue
        d=hav(lat,lon,nlat,nlon)
        rec={'node_id':nid,'lat':nlat,'lon':nlon,'distance_m':d,'tags':tags}
        if best is None or d < best['distance_m']:
            best=rec
    return best


def resolve_named_ferry(ways: list[dict], nodes: dict, gnodes: set[int], target_name: str):
    matches=[w for w in ways if w.get('tags',{}).get('name') == target_name]
    if not matches:
        return {'found':False,'target_name':target_name}
    w=matches[0]
    ends=[]
    for label,nid in [('first',w['nodes'][0]),('last',w['nodes'][-1])]:
        coord=nodes.get(nid)
        if coord is None:
            ends.append({'label':label,'osm_node_id':nid,'coordinate_available':False})
            continue
        lat,lon,tags=coord
        nearest=nearest_graph_node(nodes,gnodes,lat,lon)
        ends.append({
            'label':label,
            'osm_node_id':nid,
            'coordinate_available':True,
            'lat':lat,'lon':lon,'tags':tags,
            'endpoint_present_in_frozen_graph':nid in gnodes,
            'nearest_frozen_graph_node':nearest,
        })
    return {'found':True,'target_name':target_name,'way_id':w['id'],'tags':w['tags'],'endpoints':ends}


def main():
    road_path=Path(os.environ.get('ROAD_EDGES','artifacts/road/primary_road_directed_edges.csv.gz'))
    out=Path(os.environ.get('OUT','artifacts/exact_transfer_node_audit'))
    out.mkdir(parents=True,exist_ok=True)
    gnodes=graph_nodes(road_path)

    targets=[
      {'key':'colares_user_ferry','lat':-0.9949506,'lon':-48.1932262,'radius':5000},
      {'key':'santa_cruz_seat_port','lat':-0.66375,'lon':-49.17293,'radius':5000},
      {'key':'belem_hydro_terminal','lat':-1.4525,'lon':-48.503,'radius':5000},
    ]
    result={'frozen_road_node_count':len(gnodes),'targets':{},'geocoding':{}}
    for gq in ['Terminal Hidroviário de Belém, Pará, Brasil','Porto Santa Cruz do Arari, Pará, Brasil','Vila de Jenipapo, Santa Cruz do Arari, Pará, Brasil','Porto da Balsa Penhalonga Colares Pará Brasil']:
        try: result['geocoding'][gq]=geocode(gq)
        except Exception as e: result['geocoding'][gq]={'error':repr(e)}
        time.sleep(1)

    local={}
    for t in targets:
        nodes,ways=nearby_osm_nodes(t['lat'],t['lon'],t['radius'])
        local[t['key']]={'nodes':nodes,'ways':ways}
        frozen=[]
        for nid,(lat,lon,tags) in nodes.items():
            if nid in gnodes:
                frozen.append({'node_id':nid,'lat':lat,'lon':lon,'distance_to_reference_m':hav(t['lat'],t['lon'],lat,lon),'tags':tags})
        frozen=sorted(frozen,key=lambda x:x['distance_to_reference_m'])
        ferry_ways=[w for w in ways if w['tags'].get('route')=='ferry' or w['tags'].get('ferry')]
        highway_ways=[w for w in ways if 'highway' in w['tags']]
        result['targets'][t['key']]={
          'reference':t,
          'nearest_frozen_road_nodes':frozen[:50],
          'ferry_ways':ferry_ways,
          'highway_way_count':len(highway_ways),
          'osm_node_count':len(nodes),
        }

    # Resolve the exact OSM ferry ways already observed in the audit.
    result['resolved_ferry_routes']={
        'colares_penhalonga': resolve_named_ferry(
            local['colares_user_ferry']['ways'], local['colares_user_ferry']['nodes'], gnodes, 'Colares - Penhalonga'
        ),
        'belem_santa_cruz_do_arari': resolve_named_ferry(
            local['santa_cruz_seat_port']['ways'], local['santa_cruz_seat_port']['nodes'], gnodes, 'Belém - Santa Cruz do Arari'
        ),
    }

    col_node=3648185532
    result['colares_known_island_endpoint']={'node_id':col_node,'present_in_frozen_graph':col_node in gnodes}
    try:
        nd=get_json(f'https://api.openstreetmap.org/api/0.6/node/{col_node}.json')
        result['colares_known_island_endpoint']['osm_api']=nd
    except Exception as e:
        result['colares_known_island_endpoint']['osm_api_error']=repr(e)

    (out/'exact_transfer_node_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[]
    for key,v in result['targets'].items():
        for r in v['nearest_frozen_road_nodes']:
            rows.append({'target':key,**{k:r[k] for k in ['node_id','lat','lon','distance_to_reference_m']}})
    pd.DataFrame(rows).to_csv(out/'nearest_frozen_road_node_candidates.csv',index=False)

    ep_rows=[]
    for route_key,r in result['resolved_ferry_routes'].items():
        if not r.get('found'): continue
        for e in r['endpoints']:
            n=e.get('nearest_frozen_graph_node') or {}
            ep_rows.append({
                'route':route_key,'way_id':r['way_id'],'endpoint':e['label'],
                'osm_node_id':e['osm_node_id'],'endpoint_lat':e.get('lat'),'endpoint_lon':e.get('lon'),
                'endpoint_present_in_frozen_graph':e.get('endpoint_present_in_frozen_graph'),
                'nearest_frozen_node_id':n.get('node_id'),'nearest_distance_m':n.get('distance_m'),
            })
    pd.DataFrame(ep_rows).to_csv(out/'resolved_ferry_route_endpoints.csv',index=False)

    print(json.dumps({
      'colares_known_endpoint_present':result['colares_known_island_endpoint']['present_in_frozen_graph'],
      'resolved_ferry_routes':{
          k:{'found':v.get('found'), 'endpoints':v.get('endpoints')} for k,v in result['resolved_ferry_routes'].items()
      },
    },ensure_ascii=False,indent=2))

if __name__=='__main__': main()
