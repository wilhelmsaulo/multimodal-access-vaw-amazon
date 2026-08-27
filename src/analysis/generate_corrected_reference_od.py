from __future__ import annotations

import csv
import gzip
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

BB=Path('artifacts/corrected_backbone')
EP=Path('artifacts/endpoints')
OUT=Path('artifacts/corrected_reference_od')
OUT.mkdir(parents=True,exist_ok=True)
road_path=BB/'final_road_directed_edges.csv.gz'
hydro_path=BB/'final_hydro_directed_edges.csv.gz'
origins_path=EP/'origin_routing_endpoints.csv.gz'
services_path=EP/'service_routing_endpoints.csv.gz'
for p in (road_path,hydro_path,origins_path,services_path):
    if not p.exists(): raise FileNotFoundError(p)

origins=pd.read_csv(origins_path,dtype={'origin_id':str,'routing_node_id':str})
services=pd.read_csv(services_path,dtype={'service_id':str,'routing_node_id':str})
if len(origins)!=12673 or len(services)!=225:
    raise RuntimeError(f'Unexpected endpoint counts: origins={len(origins)} services={len(services)}')

numeric_parts=[]; special_nodes=set(); usecols=['from_node','to_node','travel_time_min']
for c in pd.read_csv(road_path,usecols=usecols,dtype={'from_node':str,'to_node':str},chunksize=750_000):
    for col in ('from_node','to_node'):
        s=c[col].astype(str); n=pd.to_numeric(s,errors='coerce'); ok=n.notna()
        numeric_parts.append(n.loc[ok].astype('int64').to_numpy())
        special_nodes.update(s.loc[~ok].tolist())
numeric_nodes=np.unique(np.concatenate(numeric_parts)); del numeric_parts
n_numeric=len(numeric_nodes); special_map={x:n_numeric+i for i,x in enumerate(sorted(special_nodes))}

def encode_road(s: pd.Series)->np.ndarray:
    ss=s.astype(str); n=pd.to_numeric(ss,errors='coerce'); out=np.empty(len(ss),dtype=np.int64); ok=n.notna().to_numpy()
    if ok.any():
        vals=n.loc[ok].astype('int64').to_numpy(); pos=np.searchsorted(numeric_nodes,vals)
        if np.any(pos>=n_numeric) or np.any(numeric_nodes[pos]!=vals): raise RuntimeError('Numeric road node missing')
        out[ok]=pos
    if (~ok).any(): out[~ok]=np.fromiter((special_map[x] for x in ss.loc[~ok]),dtype=np.int64,count=(~ok).sum())
    return out

rev_rows=[]; rev_cols=[]; weights=[]; road_edges=0
for c in pd.read_csv(road_path,usecols=usecols,dtype={'from_node':str,'to_node':str},chunksize=750_000):
    t=pd.to_numeric(c['travel_time_min'],errors='raise').to_numpy(float)
    if not np.all(t>0): raise RuntimeError('Road/transfer graph contains non-positive time')
    u=encode_road(c['from_node']); v=encode_road(c['to_node'])
    rev_rows.append(v); rev_cols.append(u); weights.append(t); road_edges+=len(c)

hydro=pd.read_csv(hydro_path,dtype={'from_node':str,'to_node':str})
ht=pd.to_numeric(hydro['travel_time_min'],errors='raise').to_numpy(float)
if not np.all(ht>0): raise RuntimeError('Hydro graph contains non-positive time')
next_id=n_numeric+len(special_map); hydro_map={}
for x in pd.concat([hydro['from_node'],hydro['to_node']],ignore_index=True).astype(str).unique():
    if x in special_map: continue
    # If an existing hydro node is also a numeric frozen road node, preserve graph identity.
    try:
        v=int(float(x)); pos=int(np.searchsorted(numeric_nodes,v))
        if pos<n_numeric and int(numeric_nodes[pos])==v: continue
    except Exception: pass
    hydro_map[x]=next_id; next_id+=1

def enc_h(s: pd.Series)->np.ndarray:
    out=[]
    for x in s.astype(str):
        if x in special_map: out.append(special_map[x]); continue
        try:
            v=int(float(x)); pos=int(np.searchsorted(numeric_nodes,v))
            if pos<n_numeric and int(numeric_nodes[pos])==v: out.append(pos); continue
        except Exception: pass
        out.append(hydro_map[x])
    return np.asarray(out,dtype=np.int64)

hu=enc_h(hydro['from_node']); hv=enc_h(hydro['to_node'])
rev_rows.append(hv); rev_cols.append(hu); weights.append(ht); hydro_edges=len(hydro)
rows=np.concatenate(rev_rows); cols=np.concatenate(rev_cols); w=np.concatenate(weights)
del rev_rows,rev_cols,weights,hydro
n_nodes=next_id
key=rows.astype(np.int64)*np.int64(n_nodes)+cols.astype(np.int64); order=np.argsort(key,kind='mergesort')
key=key[order]; rows=rows[order]; cols=cols[order]; w=w[order]
starts=np.r_[0,np.flatnonzero(key[1:]!=key[:-1])+1]; minw=np.minimum.reduceat(w,starts)
rows_u=rows[starts]; cols_u=cols[starts]; duplicate_edges_removed=int(len(w)-len(minw))
graph=csr_matrix((minw,(rows_u,cols_u)),shape=(n_nodes,n_nodes))

def encode_endpoint(x:str)->int:
    s=str(x)
    try:
        v=int(float(s)); pos=int(np.searchsorted(numeric_nodes,v))
        if pos<n_numeric and int(numeric_nodes[pos])==v: return pos
    except Exception: pass
    if s in special_map:return special_map[s]
    if s in hydro_map:return hydro_map[s]
    raise KeyError(f'Endpoint node absent: {s}')

origin_idx=np.array([encode_endpoint(x) for x in origins['routing_node_id']],dtype=np.int64)
service_idx=np.array([encode_endpoint(x) for x in services['routing_node_id']],dtype=np.int64)
origin_access=pd.to_numeric(origins['access_time_min'],errors='raise').to_numpy(float)
service_access=pd.to_numeric(services['access_time_min'],errors='raise').to_numpy(float)

out_path=OUT/'od_reference_network.csv.gz'; reachable_total=0; network_time_min=math.inf; network_time_max=0.0
total_pairs=len(origins)*len(services)
with gzip.open(out_path,'wt',newline='',encoding='utf-8') as fh:
    wr=csv.writer(fh); wr.writerow(['scenario','origin_id','service_id','network_time_min','origin_access_time_min','service_access_time_min','total_travel_time_min','reachable'])
    for j,(svc,src) in enumerate(zip(services.itertuples(index=False),service_idx)):
        dist=dijkstra(graph,directed=True,indices=int(src),return_predecessors=False); vals=dist[origin_idx]; reachable=np.isfinite(vals)
        reachable_total+=int(reachable.sum())
        if reachable.any(): network_time_min=min(network_time_min,float(vals[reachable].min())); network_time_max=max(network_time_max,float(vals[reachable].max()))
        total=vals+origin_access+float(service_access[j])
        for i,o in enumerate(origins.itertuples(index=False)):
            if reachable[i]: wr.writerow(['reference_network',o.origin_id,svc.service_id,f'{vals[i]:.10g}',f'{origin_access[i]:.10g}',f'{service_access[j]:.10g}',f'{total[i]:.10g}',True])
            else: wr.writerow(['reference_network',o.origin_id,svc.service_id,'',f'{origin_access[i]:.10g}',f'{service_access[j]:.10g}','',False])
        if (j+1)%25==0 or j+1==len(services): print(f'completed_services={j+1}/{len(services)} reachable_pairs={reachable_total}')

audit={
 'scenario':'reference_network','origin_count':len(origins),'service_count':len(services),'total_od_pairs':total_pairs,
 'reachable_od_pairs':reachable_total,'unreachable_od_pairs':total_pairs-reachable_total,'reachable_fraction':reachable_total/total_pairs,
 'road_directed_edges_input':road_edges,'hydro_directed_edges_input':hydro_edges,'graph_nodes_compact':n_nodes,
 'parallel_directed_edges_reduced_by_minimum':duplicate_edges_removed,
 'network_time_min_reachable':None if not math.isfinite(network_time_min) else network_time_min,'network_time_max_reachable':network_time_max,
 'origin_access_time_included':True,'service_access_time_included':True,'waiting_time_included':False,'air_temporal_routing_included':False,
 'bounded_transfer_patch_applied':True,'afua_synthetic_edge_added':False,'ready_for_accessibility_analysis':True,
 'scientific_policy':'Shortest-path OD on the frozen backbone plus only the bounded evidence-backed Colares and Santa Cruz do Arari transfer corrections. Waiting and ordinary-air routing remain excluded; Afuá receives no synthetic connection.'
}
(OUT/'od_reference_network_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(audit,ensure_ascii=False,indent=2))
