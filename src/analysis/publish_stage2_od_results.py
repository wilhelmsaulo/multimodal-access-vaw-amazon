from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument('--od-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('results/stage2_od'))
    args=p.parse_args()
    out=args.out; tables=out/'tables'; figs=out/'figures'
    tables.mkdir(parents=True,exist_ok=True); figs.mkdir(parents=True,exist_ok=True)

    od_path=args.od_dir/'od_reference_network.csv.gz'
    audit_path=args.od_dir/'od_reference_network_audit.json'
    audit=json.loads(audit_path.read_text(encoding='utf-8'))
    shutil.copy2(audit_path,tables/'od_reference_network_audit.json')

    use=['origin_id','service_id','total_travel_time_min','reachable']
    chunks=[]
    for c in pd.read_csv(od_path,usecols=use,dtype={'origin_id':str,'service_id':str},chunksize=400000):
        c['reachable']=c['reachable'].astype(str).str.lower().eq('true')
        c['total_travel_time_min']=pd.to_numeric(c['total_travel_time_min'],errors='coerce')
        chunks.append(c)
    df=pd.concat(chunks,ignore_index=True); del chunks
    if len(df)!=2851425 or df['origin_id'].nunique()!=12673 or df['service_id'].nunique()!=225:
        raise RuntimeError('Corrected OD cardinalities do not match authoritative run')

    origin=df.groupby('origin_id',sort=False).agg(
        reachable_services=('reachable','sum'),service_count=('service_id','size'),
        nearest_time_min=('total_travel_time_min','min'),median_time_min=('total_travel_time_min','median')
    ).reset_index()
    origin['reachable_fraction']=origin['reachable_services']/origin['service_count']
    origin.to_csv(tables/'origin_reachability_summary.csv.gz',index=False,compression='gzip')

    service=df.groupby('service_id',sort=False).agg(
        reachable_origins=('reachable','sum'),origin_count=('origin_id','size')
    ).reset_index()
    service['reachable_fraction']=service['reachable_origins']/service['origin_count']
    service.to_csv(tables/'service_reachability_summary.csv.gz',index=False,compression='gzip')

    r=df.loc[df['reachable'] & df['total_travel_time_min'].notna(),'total_travel_time_min']
    probs=[0.01,0.05,0.10,0.25,0.50,0.75,0.90,0.95,0.99]
    q=pd.DataFrame({'quantile':probs,'total_travel_time_min':[float(r.quantile(x)) for x in probs]})
    q.to_csv(tables/'reachable_travel_time_quantiles.csv',index=False)

    # Deterministic compact matrix for visual inspection only; the full 2.85M-pair OD remains the authoritative artifact.
    origins=sorted(df['origin_id'].unique())[:40]
    services=sorted(df['service_id'].unique())[:40]
    sub=df[df['origin_id'].isin(origins)&df['service_id'].isin(services)].copy()
    mat=sub.pivot(index='origin_id',columns='service_id',values='total_travel_time_min').reindex(index=origins,columns=services)
    mat.to_csv(tables/'representative_od_time_matrix_40x40.csv')

    fig,ax=plt.subplots(figsize=(10,8))
    im=ax.imshow(mat.to_numpy(float),aspect='auto',cmap='viridis')
    ax.set_title('OD corrigida — matriz temporal ilustrativa 40 × 40')
    ax.set_xlabel('Serviços (subconjunto determinístico)'); ax.set_ylabel('Origens (subconjunto determinístico)')
    fig.colorbar(im,ax=ax,label='Tempo total de viagem (min)')
    fig.text(0.01,0.01,'Fonte: OD de referência corrigida, run 33089335405 (2026). Células sem rota permanecem ausentes.',fontsize=7)
    fig.tight_layout(rect=[0,0.03,1,1]); fig.savefig(figs/'representative_od_time_matrix.png',dpi=300,bbox_inches='tight'); plt.close(fig)

    fig,ax=plt.subplots(figsize=(9,5.5)); ax.hist(origin['reachable_fraction'],bins=30)
    ax.set_title('OD corrigida — distribuição da fração de serviços alcançáveis por origem')
    ax.set_xlabel('Fração de serviços alcançáveis'); ax.set_ylabel('Número de origens')
    fig.text(0.01,0.01,'Fonte: OD de referência corrigida, run 33089335405 (2026).',fontsize=7)
    fig.tight_layout(rect=[0,0.03,1,1]); fig.savefig(figs/'origin_reachable_fraction_distribution.png',dpi=300,bbox_inches='tight'); plt.close(fig)

    fig,ax=plt.subplots(figsize=(9,5.5)); ax.hist(r,bins=60)
    ax.set_title('OD corrigida — distribuição dos tempos de viagem alcançáveis')
    ax.set_xlabel('Tempo total de viagem (min)'); ax.set_ylabel('Pares origem–serviço')
    fig.text(0.01,0.01,'Fonte: OD de referência corrigida, run 33089335405 (2026).',fontsize=7)
    fig.tight_layout(rect=[0,0.03,1,1]); fig.savefig(figs/'reachable_travel_time_distribution.png',dpi=300,bbox_inches='tight'); plt.close(fig)

    readme=[
        '# Stage 2 — corrected origin–destination matrix','',
        'This directory documents the authoritative corrected origin–service OD matrix without duplicating the full 2.85-million-row file inside Git history.','',
        '## Authoritative provenance','',
        '- Corrected OD run: `33089335405`','- Artifact: `pa-corrected-reference-od`','- Origins: 12,673','- Services: 225','- OD pairs: 2,851,425',
        f"- Reachable pairs: {int(audit['reachable_od_pairs']):,}",f"- Unreachable pairs: {int(audit['unreachable_od_pairs']):,}",'',
        'The full compressed OD matrix remains the authoritative workflow artifact. The files here are permanent audit/documentation derivatives.','',
        '## Permanent tables','',
        '- [OD audit metadata](tables/od_reference_network_audit.json)','- [Origin reachability summary](tables/origin_reachability_summary.csv.gz)','- [Service reachability summary](tables/service_reachability_summary.csv.gz)','- [Reachable travel-time quantiles](tables/reachable_travel_time_quantiles.csv)','- [Illustrative 40 × 40 OD time matrix](tables/representative_od_time_matrix_40x40.csv)','',
        '## Figures','',
        '![OD matrix](figures/representative_od_time_matrix.png)','',
        '![Origin reachability](figures/origin_reachable_fraction_distribution.png)','',
        '![Travel time](figures/reachable_travel_time_distribution.png)','',
        'The 40 × 40 matrix is explicitly illustrative and deterministic; it is not a substitute for the full OD artifact. Unreachable cells are not assigned synthetic travel times.',''
    ]
    (out/'README.md').write_text('\n'.join(readme),encoding='utf-8')
    (out/'publication_metadata.json').write_text(json.dumps({
        'corrected_od_run':33089335405,'source_artifact':'pa-corrected-reference-od','od_pairs':2851425,
        'origins':12673,'services':225,'full_od_committed_to_git':False,'full_od_preserved_as_authoritative_workflow_artifact':True,
        'illustrative_matrix_shape':[40,40]
    },ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    main()
