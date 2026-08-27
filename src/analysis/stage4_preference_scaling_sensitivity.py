from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from stage4_mcdm import (
    ACCESS_BENEFIT,
    ACCESS_TIME,
    BINARY_DEFICIT,
    CRITERIA,
    STATUS_COVERAGE_LIMIT,
    TERRITORIAL,
    promethee_flows,
    ranks_desc,
)


def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument('matrix',type=Path)
    p.add_argument('--out',type=Path,required=True)
    return p.parse_args()


def minmax(s: pd.Series) -> pd.Series:
    lo=s.min(skipna=True); hi=s.max(skipna=True)
    if pd.isna(lo) or pd.isna(hi) or np.isclose(lo,hi): return pd.Series(0.0,index=s.index,dtype=float)
    return (s-lo)/(hi-lo)


def winsor_minmax(s: pd.Series, q=.05) -> pd.Series:
    obs=s.dropna()
    if obs.empty: return pd.Series(np.nan,index=s.index,dtype=float)
    lo=float(obs.quantile(q)); hi=float(obs.quantile(1-q))
    clipped=s.clip(lower=lo,upper=hi)
    if np.isclose(lo,hi): return pd.Series(0.0,index=s.index,dtype=float)
    return (clipped-lo)/(hi-lo)


def percentile_scale(s: pd.Series) -> pd.Series:
    out=pd.Series(np.nan,index=s.index,dtype=float)
    ok=s.notna()
    n=int(ok.sum())
    if n<=1:
        out.loc[ok]=0.0
    else:
        out.loc[ok]=(s.loc[ok].rank(method='average')-1)/(n-1)
    return out


def build_scores(frame: pd.DataFrame, scale_mode: str) -> pd.DataFrame:
    x=pd.DataFrame(index=frame.index)
    for c in ACCESS_BENEFIT:
        x[c]=1-pd.to_numeric(frame[c],errors='coerce')
    for c in ACCESS_TIME:
        raw=pd.to_numeric(frame[c],errors='coerce')
        if scale_mode=='minmax': scaled=minmax(raw)
        elif scale_mode=='winsor_05_95': scaled=winsor_minmax(raw,.05)
        elif scale_mode=='percentile': scaled=percentile_scale(raw)
        else: raise ValueError(scale_mode)
        scaled.loc[frame['accessibility_coverage_status'].eq(STATUS_COVERAGE_LIMIT)]=np.nan
        x[c]=scaled
    for c in BINARY_DEFICIT:
        x[c]=pd.to_numeric(frame[c],errors='coerce')
    for c in TERRITORIAL:
        raw=pd.to_numeric(frame[c],errors='coerce')
        if scale_mode=='percentile': x[c]=percentile_scale(raw)
        elif scale_mode=='winsor_05_95': x[c]=winsor_minmax(raw,.05)
        else: x[c]=raw
    return x[CRITERIA].clip(0,1)


def preference_tensor(scores: np.ndarray, pref_mode: str):
    n,k=scores.shape
    pref=np.zeros((k,n,n),dtype=np.float32)
    avail=np.zeros((k,n,n),dtype=np.float32)
    if pref_mode=='linear_p1': p=1.0
    elif pref_mode=='linear_p05': p=.5
    elif pref_mode=='linear_p025': p=.25
    elif pref_mode=='usual': p=None
    else: raise ValueError(pref_mode)
    for j in range(k):
        z=scores[:,j]; valid=np.isfinite(z); joint=valid[:,None]&valid[None,:]
        d=np.maximum(z[:,None]-z[None,:],0.0)
        if p is None: pp=(d>0).astype(float)
        else: pp=np.minimum(d/p,1.0)
        pref[j]=np.where(joint,pp,0.0).astype(np.float32)
        avail[j]=joint.astype(np.float32)
    return pref,avail


def corr(a,b):
    return float(np.corrcoef(np.asarray(a,float),np.asarray(b,float))[0,1])


def main():
    a=parse_args(); a.out.mkdir(parents=True,exist_ok=True)
    frame=pd.read_csv(a.matrix,dtype={'municipality_code':'string'})
    if len(frame)!=144: raise RuntimeError('Expected 144 municipalities')
    weights=np.full(len(CRITERIA),1/len(CRITERIA))
    scenarios=[]; rankings=[]
    scales=['minmax','winsor_05_95','percentile']
    prefs=['linear_p1','linear_p05','linear_p025','usual']
    ref_rank=None
    qn=int(np.ceil(len(frame)/4))
    for scale in scales:
        scores=build_scores(frame,scale).to_numpy(float)
        for pm in prefs:
            pref,avail=preference_tensor(scores,pm)
            _,_,net,_=promethee_flows(pref,avail,weights)
            rank=ranks_desc(net)
            sid=f'{scale}__{pm}'
            if sid=='minmax__linear_p1': ref_rank=rank.copy()
            rankings.append(pd.DataFrame({
                'scenario':sid,
                'municipality_code':frame['municipality_code'],
                'municipality_name':frame['municipality_name'],
                'rank':rank,
                'net_flow':net,
                'coverage_limited':frame['accessibility_coverage_status'].eq(STATUS_COVERAGE_LIMIT),
            }))
    if ref_rank is None: raise RuntimeError('Reference scenario missing')
    ref_top10=set(frame.loc[ref_rank<=10,'municipality_code'].astype(str)); ref_q=set(frame.loc[ref_rank<=qn,'municipality_code'].astype(str))
    allr=pd.concat(rankings,ignore_index=True)
    for sid,g in allr.groupby('scenario',sort=False):
        rr=g['rank'].to_numpy()
        # group order is original frame order because every scenario was appended in that order
        t10=set(g.loc[g['rank']<=10,'municipality_code'].astype(str)); tq=set(g.loc[g['rank']<=qn,'municipality_code'].astype(str))
        scenarios.append({
            'scenario':sid,
            'spearman_vs_reference':corr(rr,ref_rank),
            'top10_overlap_count':len(t10&ref_top10),
            'top10_jaccard':len(t10&ref_top10)/len(t10|ref_top10),
            'top_quartile_overlap_count':len(tq&ref_q),
            'top_quartile_jaccard':len(tq&ref_q)/len(tq|ref_q),
            'max_abs_rank_shift':int(np.max(np.abs(rr-ref_rank))),
            'mean_abs_rank_shift':float(np.mean(np.abs(rr-ref_rank))),
        })
    scen=pd.DataFrame(scenarios).sort_values('scenario')
    scen.to_csv(a.out/'preference_scaling_scenario_summary.csv',index=False)
    allr.to_csv(a.out/'preference_scaling_all_rankings.csv',index=False)

    pivot=allr.pivot(index=['municipality_code','municipality_name'],columns='scenario',values='rank').reset_index()
    scenario_cols=[c for c in pivot.columns if c not in ['municipality_code','municipality_name']]
    pivot['best_rank']=pivot[scenario_cols].min(axis=1)
    pivot['worst_rank']=pivot[scenario_cols].max(axis=1)
    pivot['rank_range']=pivot['worst_rank']-pivot['best_rank']
    pivot['top10_scenario_fraction']=(pivot[scenario_cols]<=10).mean(axis=1)
    pivot['top_quartile_scenario_fraction']=(pivot[scenario_cols]<=qn).mean(axis=1)
    pivot.sort_values(['rank_range','best_rank'],ascending=[False,True]).to_csv(a.out/'municipality_preference_scaling_stability.csv',index=False)

    summary={
        'stage':'Stage 4 preference-function and scaling sensitivity',
        'reference_scenario':'minmax__linear_p1',
        'scenario_count':len(scen),
        'scale_modes':scales,
        'preference_modes':prefs,
        'reference_weights':'equal 1/9 criterion weights',
        'coverage_limited_policy':'Afuá remains missing-aware/pairwise comparable; no imputation',
        'spearman_min':float(scen['spearman_vs_reference'].min()),
        'spearman_median':float(scen['spearman_vs_reference'].median()),
        'top10_overlap_min':int(scen['top10_overlap_count'].min()),
        'top_quartile_overlap_min':int(scen['top_quartile_overlap_count'].min()),
        'max_rank_shift_across_scenarios':int(scen['max_abs_rank_shift'].max()),
        'scientific_note':'Sensitivity scenarios alter only scaling/preference mapping, not criteria, transport graph, services, weights or missingness policy. The usual preference is intentionally discontinuous and serves as a stress test rather than the preferred specification.'
    }
    (a.out/'preference_scaling_sensitivity_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print(scen.to_string(index=False))

if __name__=='__main__': main()
