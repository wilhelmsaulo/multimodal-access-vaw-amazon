from __future__ import annotations
import argparse,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LogNorm
from src.accessibility.e2sfca import e2sfca,exponential_decay,gaussian_decay

LABELS={'health':'Saúde especializada','creas':'CREAS','specialized_security':'Segurança especializada','specialized_justice':'Justiça especializada'}
CONFIGS={
 'reference_step_120':(120,None,'Referência: limite de 120 min, sem decaimento adicional'),
 'step_240':(240,None,'Sensibilidade: limite de 240 min'),
 'exponential_120_half60':(120,exponential_decay(math.log(2)/60),'Sensibilidade: exponencial, meia-vida de 60 min, limite 120 min'),
 'gaussian_120_sigma60':(120,gaussian_decay(60),'Sensibilidade: gaussiano, sigma 60 min, limite 120 min'),
 'unbounded_no_decay':(None,None,'Diagnóstico: sem limite e sem decaimento'),
}

def weighted_mean(g):
 w=g.female_population.to_numpy(float); x=g.e2sfca_score.to_numpy(float)
 return float(np.average(x,weights=w)) if w.sum()>0 else np.nan

def run_config(travel,origins,services,name,threshold,decay):
 r=e2sfca(travel,origins,services,time_col='total_travel_time_min',threshold_minutes=threshold,decay=decay,supply_mode='unit_presence')
 s=r.sector_scores.merge(origins[['origin_id','municipality_code','municipality_name','female_population']],on='origin_id',validate='many_to_one')
 s['configuration']=name
 m=s.groupby(['service_type','municipality_code','municipality_name'],dropna=False).apply(weighted_mean,include_groups=False).rename('e2sfca_score').reset_index()
 cov=origins.groupby(['municipality_code','municipality_name'],as_index=False).agg(routing_ready_origins=('origin_id','size'),routing_ready_female_population=('female_population','sum'))
 m=m.merge(cov,on=['municipality_code','municipality_name'],how='left'); m['configuration']=name
 return r.service_ratios,s,m

def map_panels(sectors,values,value_key,out,title,municipal=False):
 geo=sectors.to_crs(5880); fig,axs=plt.subplots(2,2,figsize=(14,12)); axs=axs.ravel()
 for ax,(typ,label) in zip(axs,LABELS.items()):
  base=geo.copy(); d=values[values.service_type==typ][[value_key,'e2sfca_score']]
  base=base.merge(d,on=value_key,how='left')
  base.plot(ax=ax,color='#D9D9D9',edgecolor='white' if not municipal else '#888',linewidth=.02 if not municipal else .25)
  pos=base[base.e2sfca_score>0]
  if len(pos): pos.plot(ax=ax,column='e2sfca_score',cmap='viridis',norm=LogNorm(vmin=max(pos.e2sfca_score.min(),1e-12),vmax=pos.e2sfca_score.max()),linewidth=0,legend=True,legend_kwds={'shrink':.65})
  base.dissolve().boundary.plot(ax=ax,color='#444',linewidth=.5); ax.set_title(label); ax.set_axis_off()
 fig.suptitle(title,fontsize=15); fig.text(.01,.01,'Fontes: IBGE Censo 2022; rede OD multimodal corrigida (2026); oferta unitária por local físico roteável. CRS: SIRGAS 2000 / Brazil Polyconic (EPSG:5880).',fontsize=7)
 fig.tight_layout(rect=[0,.025,1,.96]); fig.savefig(out,dpi=300,bbox_inches='tight'); plt.close(fig)

def main():
 p=argparse.ArgumentParser(); p.add_argument('--od',type=Path,required=True); p.add_argument('--origins',type=Path,required=True); p.add_argument('--services',type=Path,required=True); p.add_argument('--census-gpkg',type=Path,required=True); p.add_argument('--out',type=Path,default=Path('results/e2sfca'))
 a=p.parse_args(); out=a.out; figs=out/'figures'; tabs=out/'tables'; figs.mkdir(parents=True,exist_ok=True); tabs.mkdir(parents=True,exist_ok=True)
 travel=pd.read_csv(a.od,usecols=['scenario','origin_id','service_id','total_travel_time_min'],dtype={'origin_id':str,'service_id':str},low_memory=False)
 origins=pd.read_csv(a.origins,dtype={'origin_id':str,'municipality_code':str}); services=pd.read_csv(a.services,dtype={'service_id':str})
 origins.municipality_code=origins.municipality_code.str.zfill(7); origins.female_population=pd.to_numeric(origins.female_population,errors='raise')
 if len(travel)!=2851425 or len(origins)!=12673 or len(services)!=225: raise RuntimeError('Unexpected authoritative input dimensions')
 all_m=[]; ref_s=ref_r=None
 for name,(threshold,decay,_) in CONFIGS.items():
  ratios,scores,mun=run_config(travel,origins,services,name,threshold,decay); all_m.append(mun)
  if name=='reference_step_120': ref_r,ref_s=ratios,scores
 municipal=pd.concat(all_m,ignore_index=True); municipal.to_csv(tabs/'configuration_municipal_scores.csv',index=False)
 ref_s.to_csv(tabs/'reference_sector_scores.csv.gz',index=False,compression='gzip'); ref_r.to_csv(tabs/'reference_service_ratios.csv',index=False)
 municipal[municipal.configuration=='reference_step_120'].to_csv(tabs/'reference_municipal_scores.csv',index=False)
 rows=[]
 for typ in LABELS:
  w=municipal[municipal.service_type==typ].pivot(index='municipality_code',columns='configuration',values='e2sfca_score')
  c=w.corr(method='spearman')
  for x in c.index:
   for y in c.columns: rows.append({'service_type':typ,'configuration_a':x,'configuration_b':y,'spearman':c.loc[x,y]})
 pd.DataFrame(rows).to_csv(tabs/'configuration_agreement.csv',index=False)
 # score distributions
 fig,axs=plt.subplots(2,2,figsize=(12,9));
 for ax,(typ,label) in zip(axs.ravel(),LABELS.items()):
  x=ref_s[(ref_s.service_type==typ)&(ref_s.e2sfca_score>0)].e2sfca_score
  ax.hist(np.log10(x),bins=35,color='#0072B2',alpha=.85); ax.set_title(label); ax.set_xlabel('log10(score E2SFCA), scores positivos'); ax.set_ylabel('Setores')
 fig.suptitle('E2SFCA de referência — distribuição dos scores setoriais'); fig.tight_layout(rect=[0,0,1,.96]); fig.savefig(figs/'reference_score_distributions.png',dpi=300,bbox_inches='tight'); plt.close(fig)
 # configuration comparison
 fig,axs=plt.subplots(2,2,figsize=(13,10)); order=list(CONFIGS)
 for ax,(typ,label) in zip(axs.ravel(),LABELS.items()):
  d=pd.DataFrame(rows); z=d[(d.service_type==typ)].pivot(index='configuration_a',columns='configuration_b',values='spearman').reindex(index=order,columns=order)
  im=ax.imshow(z,vmin=0,vmax=1,cmap='viridis'); ax.set_xticks(range(len(order)),order,rotation=45,ha='right',fontsize=7); ax.set_yticks(range(len(order)),order,fontsize=7); ax.set_title(label)
 fig.colorbar(im,ax=axs.ravel().tolist(),label='Spearman'); fig.suptitle('Concordância municipal entre configurações E2SFCA'); fig.subplots_adjust(left=.2,bottom=.22,top=.92,right=.9,wspace=.35,hspace=.5); fig.savefig(figs/'configuration_agreement.png',dpi=300,bbox_inches='tight'); plt.close(fig)
 sectors=gpd.read_file(a.census_gpkg); sectors['sector_id']=sectors.CD_SETOR.astype(str); sectors['origin_id']=sectors['sector_id']; sectors['municipality_code']=sectors.CD_MUN.astype(str).str.zfill(7)
 map_panels(sectors,ref_s,'origin_id',figs/'reference_sector_maps.png','E2SFCA de referência — scores por setor censitário')
 mun_geo=sectors[['municipality_code','geometry']].dissolve(by='municipality_code').reset_index()
 ref_m=municipal[municipal.configuration=='reference_step_120']
 map_panels(mun_geo,ref_m,'municipality_code',figs/'reference_municipal_maps.png','E2SFCA de referência — agregação municipal ponderada pela população feminina',True)
 (out/'README.md').write_text('\n'.join(['# Item 4 — pacote visual e analítico do E2SFCA','', 'A configuração de referência usa oferta unitária, cálculo separado por tipo de serviço, limite de 120 minutos e nenhuma função adicional de decaimento. Ela minimiza novas suposições e mantém o limite já registrado no estudo. Quatro configurações adicionais são publicadas como sensibilidade.','', 'Afuá e outros setores sem origem primária pronta permanecem como cobertura não avaliada; não recebem score zero sintético.','', '## Figuras','', '![Distribuições](figures/reference_score_distributions.png)','', '![Mapas setoriais](figures/reference_sector_maps.png)','', '![Mapas municipais](figures/reference_municipal_maps.png)','', '![Configurações](figures/configuration_agreement.png)','', '## Tabelas','', '- [Scores setoriais de referência](tables/reference_sector_scores.csv.gz)','- [Scores municipais de referência](tables/reference_municipal_scores.csv)','- [Todas as configurações](tables/configuration_municipal_scores.csv)','- [Concordância](tables/configuration_agreement.csv)','- [Razões oferta-demanda](tables/reference_service_ratios.csv)','']),encoding='utf-8')
 meta={'status':'authoritative_published_complementary_analysis','reference':'reference_step_120','supply_mode':'unit_presence','service_types_separate':True,'municipal_aggregation':'female_population_weighted_mean_among_routing_ready_origins','coverage_limited_origins_not_zero_imputed':True,'configurations':{k:v[2] for k,v in CONFIGS.items()},'od_run':33089335405}
 (out/'publication_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__': main()
