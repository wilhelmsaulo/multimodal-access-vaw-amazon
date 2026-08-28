from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'results' / 'integrated_synthesis'
TAB = OUT / 'tables'
FIG = OUT / 'figures'
OUT.mkdir(parents=True, exist_ok=True)
TAB.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

E2 = ROOT / 'results' / 'e2sfca' / 'tables' / 'reference_municipal_scores.csv'
SOMM = ROOT / 'results' / 'stage5' / 'tables' / 'stage5_som_profiles_with_promethee.csv'
PROF = ROOT / 'results' / 'stage5' / 'tables' / 'stage5_som_profile_characteristics.csv'

# Frozen inputs only. This script does not retrain, rerank, or alter any upstream model.
e2 = pd.read_csv(E2)
sp = pd.read_csv(SOMM)
prof = pd.read_csv(PROF)

for d in (e2, sp):
    d['municipality_code'] = pd.to_numeric(d['municipality_code'], errors='coerce').astype('Int64')

service_types = sorted(e2['service_type'].dropna().astype(str).unique())
expected_services = len(service_types)

# E2SFCA within-service percentile: higher E2SFCA score = greater potential accessibility.
# Missing coverage is preserved. No synthetic zero is created.
e2['e2sfca_within_service_percentile'] = e2.groupby('service_type')['e2sfca_score'].rank(method='average', pct=True)
score_w = e2.pivot(index=['municipality_code','municipality_name'], columns='service_type', values='e2sfca_score')
pct_w = e2.pivot(index=['municipality_code','municipality_name'], columns='service_type', values='e2sfca_within_service_percentile')
score_w.columns = [f'e2sfca_score__{c}' for c in score_w.columns]
pct_w.columns = [f'e2sfca_percentile__{c}' for c in pct_w.columns]
e2w = pd.concat([score_w, pct_w], axis=1).reset_index()

pct_cols = [f'e2sfca_percentile__{s}' for s in service_types]
e2w['e2sfca_services_observed'] = e2w[pct_cols].notna().sum(axis=1)
e2w['e2sfca_complete_service_coverage'] = e2w['e2sfca_services_observed'].eq(expected_services)
e2w['e2sfca_mean_within_service_percentile_complete_only'] = e2w[pct_cols].mean(axis=1).where(e2w['e2sfca_complete_service_coverage'])

base = sp.merge(e2w, on='municipality_code', how='left', suffixes=('','_e2sfca'))
if 'municipality_name_e2sfca' in base.columns:
    base.drop(columns=['municipality_name_e2sfca'], inplace=True)
base['e2sfca_services_observed'] = base['e2sfca_services_observed'].fillna(0).astype(int)
base['e2sfca_complete_service_coverage'] = base['e2sfca_complete_service_coverage'].fillna(False)

# Descriptive concordance typology. It is NOT a new priority class or score.
complete = base['e2sfca_complete_service_coverage'] & base['e2sfca_mean_within_service_percentile_complete_only'].notna()
low_access_cut = base.loc[complete, 'e2sfca_mean_within_service_percentile_complete_only'].quantile(0.25)
high_access_cut = base.loc[complete, 'e2sfca_mean_within_service_percentile_complete_only'].quantile(0.75)
base['integrated_descriptive_pattern'] = 'E2SFCA coverage incomplete'
base.loc[complete, 'integrated_descriptive_pattern'] = 'Intermediate E2SFCA accessibility'
base.loc[complete & (base['e2sfca_mean_within_service_percentile_complete_only'] <= low_access_cut), 'integrated_descriptive_pattern'] = 'Lower E2SFCA accessibility quartile'
base.loc[complete & (base['e2sfca_mean_within_service_percentile_complete_only'] >= high_access_cut), 'integrated_descriptive_pattern'] = 'Higher E2SFCA accessibility quartile'
base['promethee_top_quartile_and_lower_e2sfca'] = (
    base['top_quartile'].astype(bool) & complete &
    (base['e2sfca_mean_within_service_percentile_complete_only'] <= low_access_cut)
)

base.sort_values(['promethee_rank','municipality_name']).to_csv(TAB/'integrated_municipal_e2sfca_mcdm_som.csv', index=False)

# Per-profile E2SFCA summary, by service, retaining coverage explicitly.
rows=[]
for p, gp in base.groupby('som_profile'):
    for s in service_types:
        sc=f'e2sfca_score__{s}'; pc=f'e2sfca_percentile__{s}'
        vals=gp[pc]
        rows.append({
            'som_profile':int(p), 'service_type':s, 'municipality_count_profile':len(gp),
            'municipalities_with_e2sfca':int(vals.notna().sum()),
            'coverage_share':float(vals.notna().mean()),
            'median_e2sfca_score':float(gp[sc].median()) if gp[sc].notna().any() else np.nan,
            'median_within_service_percentile':float(vals.median()) if vals.notna().any() else np.nan,
            'mean_within_service_percentile':float(vals.mean()) if vals.notna().any() else np.nan,
        })
pes = pd.DataFrame(rows)
pes.to_csv(TAB/'som_profile_e2sfca_service_summary.csv', index=False)

# E2SFCA vs frozen PROMETHEE associations by service.
corr=[]
for s in service_types:
    pc=f'e2sfca_percentile__{s}'
    d=base[['promethee_rank','promethee_net_flow',pc]].dropna()
    corr.append({
        'service_type':s, 'n_complete':len(d),
        'spearman_e2sfca_percentile_vs_promethee_rank': d[pc].corr(d['promethee_rank'], method='spearman'),
        'spearman_e2sfca_percentile_vs_promethee_net_flow': d[pc].corr(d['promethee_net_flow'], method='spearman'),
    })
corr=pd.DataFrame(corr)
corr.to_csv(TAB/'e2sfca_promethee_associations.csv', index=False)

# Cross-method descriptive counts by SOM profile.
summary = base.groupby('som_profile').agg(
    municipalities=('municipality_code','size'),
    promethee_median_rank=('promethee_rank','median'),
    promethee_top_quartile_count=('top_quartile','sum'),
    promethee_top_quartile_share=('top_quartile','mean'),
    complete_e2sfca_count=('e2sfca_complete_service_coverage','sum'),
    mean_e2sfca_percentile_median=('e2sfca_mean_within_service_percentile_complete_only','median'),
    concordant_top_priority_lower_access_count=('promethee_top_quartile_and_lower_e2sfca','sum'),
).reset_index()
summary['promethee_top_quartile_count']=summary['promethee_top_quartile_count'].astype(int)
summary['complete_e2sfca_count']=summary['complete_e2sfca_count'].astype(int)
summary['concordant_top_priority_lower_access_count']=summary['concordant_top_priority_lower_access_count'].astype(int)
summary.to_csv(TAB/'integrated_profile_summary.csv', index=False)

# Focus table: top PROMETHEE municipalities plus E2SFCA and SOM context.
focus_cols=['municipality_code','municipality_name','som_profile','promethee_rank','promethee_net_flow','top_10','top_quartile','robustness_top_quartile_probability','e2sfca_services_observed','e2sfca_complete_service_coverage','e2sfca_mean_within_service_percentile_complete_only','integrated_descriptive_pattern'] + pct_cols
base.sort_values('promethee_rank').head(20)[focus_cols].to_csv(TAB/'integrated_top20_promethee_context.csv', index=False)

# Figure 1: profile x service E2SFCA percentile heatmap.
heat = pes.pivot(index='som_profile', columns='service_type', values='median_within_service_percentile').reindex(sorted(base.som_profile.unique()))
fig, ax = plt.subplots(figsize=(max(7,1.45*len(service_types)),4.8))
im=ax.imshow(heat.values, vmin=0, vmax=1, aspect='auto')
ax.set_xticks(range(len(heat.columns)), [str(x) for x in heat.columns], rotation=35, ha='right')
ax.set_yticks(range(len(heat.index)), [f'P{int(x)}' for x in heat.index])
ax.set_title('Median within-service E2SFCA percentile by SOM profile')
ax.set_xlabel('Service type'); ax.set_ylabel('SOM macroprofile')
for i in range(heat.shape[0]):
    for j in range(heat.shape[1]):
        v=heat.iloc[i,j]
        if pd.notna(v): ax.text(j,i,f'{v:.2f}',ha='center',va='center',fontsize=9)
fig.colorbar(im,ax=ax,label='E2SFCA percentile (higher = greater potential accessibility)')
fig.tight_layout(); fig.savefig(FIG/'integrated_som_e2sfca_profile_heatmap.png',dpi=300); fig.savefig(FIG/'integrated_som_e2sfca_profile_heatmap.pdf'); plt.close(fig)

# Figure 2: PROMETHEE association by SOM profile.
fig,ax=plt.subplots(figsize=(6.5,4.8))
x=np.arange(len(summary)); vals=summary['promethee_top_quartile_share'].values
ax.bar(x, vals)
ax.set_xticks(x,[f'P{int(p)}' for p in summary.som_profile])
ax.set_ylim(0,max(.6,vals.max()+.08)); ax.set_ylabel('Share in PROMETHEE top quartile'); ax.set_xlabel('SOM macroprofile')
ax.set_title('Post-hoc PROMETHEE top-quartile membership by SOM profile')
for i,v in enumerate(vals): ax.text(i,v+.015,f'{v:.1%}',ha='center')
fig.tight_layout(); fig.savefig(FIG/'integrated_som_promethee_top_quartile.png',dpi=300); fig.savefig(FIG/'integrated_som_promethee_top_quartile.pdf'); plt.close(fig)

# Figure 3: integrated scatter for municipalities with complete E2SFCA coverage.
fig,ax=plt.subplots(figsize=(7.2,5.5))
d=base.loc[complete].copy()
markers=['o','s','^','D']
for k,p in enumerate(sorted(d.som_profile.unique())):
    g=d[d.som_profile==p]
    ax.scatter(g['e2sfca_mean_within_service_percentile_complete_only'],g['promethee_net_flow'],label=f'P{int(p)}',marker=markers[k%len(markers)],alpha=.75)
ax.axvline(low_access_cut,linestyle='--',linewidth=1)
ax.axhline(0,linestyle=':',linewidth=1)
ax.set_xlabel('Mean within-service E2SFCA percentile (complete coverage only)')
ax.set_ylabel('Frozen PROMETHEE-II net flow')
ax.set_title('Integrated E2SFCA × PROMETHEE view, stratified by SOM profile')
ax.legend(title='SOM profile')
fig.tight_layout(); fig.savefig(FIG/'integrated_e2sfca_promethee_som_scatter.png',dpi=300); fig.savefig(FIG/'integrated_e2sfca_promethee_som_scatter.pdf'); plt.close(fig)

# Compact publication panel.
fig,axs=plt.subplots(1,3,figsize=(15,4.8))
# A heatmap
ax=axs[0]; im=ax.imshow(heat.values,vmin=0,vmax=1,aspect='auto'); ax.set_xticks(range(len(heat.columns)),heat.columns,rotation=45,ha='right',fontsize=8); ax.set_yticks(range(len(heat.index)),[f'P{int(x)}' for x in heat.index]); ax.set_title('A. E2SFCA by SOM profile'); ax.set_ylabel('SOM profile'); fig.colorbar(im,ax=ax,fraction=.046,pad=.04)
# B bars
ax=axs[1]; ax.bar(np.arange(len(summary)),summary.promethee_top_quartile_share); ax.set_xticks(np.arange(len(summary)),[f'P{int(x)}' for x in summary.som_profile]); ax.set_title('B. PROMETHEE top quartile'); ax.set_ylabel('Share'); ax.set_ylim(0,max(.6,summary.promethee_top_quartile_share.max()+.08))
# C scatter
ax=axs[2]
for k,p in enumerate(sorted(d.som_profile.unique())):
    g=d[d.som_profile==p]; ax.scatter(g.e2sfca_mean_within_service_percentile_complete_only,g.promethee_net_flow,label=f'P{int(p)}',marker=markers[k%4],alpha=.75)
ax.axvline(low_access_cut,ls='--',lw=1); ax.axhline(0,ls=':',lw=1); ax.set_title('C. Municipality-level integration'); ax.set_xlabel('Mean E2SFCA percentile'); ax.set_ylabel('PROMETHEE net flow'); ax.legend(fontsize=8)
fig.suptitle('Integrated frozen results: E2SFCA, PROMETHEE II and SOM',y=1.02)
fig.tight_layout(); fig.savefig(FIG/'integrated_e2sfca_mcdm_som_panel.png',dpi=300,bbox_inches='tight'); fig.savefig(FIG/'integrated_e2sfca_mcdm_som_panel.pdf',bbox_inches='tight'); plt.close(fig)

# Manuscript-ready synthesis draft, automatically grounded in computed summaries.
strong_corr = corr.loc[corr['spearman_e2sfca_percentile_vs_promethee_net_flow'].abs().idxmax()] if len(corr) else None
text = []
text.append('# Integrated results synthesis — E2SFCA, MCDM and SOM\n')
text.append('This synthesis joins already frozen outputs. It does not retrain the SOM, change PROMETHEE-II rankings, or redefine E2SFCA. The integration is descriptive and intended for manuscript interpretation.\n')
text.append('## Cross-method interpretation\n')
text.append(f'The reference E2SFCA block contains {expected_services} service types: ' + ', '.join(service_types) + '. Within each service, municipal scores are converted to percentiles only to permit a common descriptive scale in the integrated figures. Raw E2SFCA scores are retained in the municipal table. Missing E2SFCA coverage is preserved and never replaced by zero.\n')
text.append('The SOM profiles remain neutral socioeconomic-demographic descriptors. PROMETHEE-II remains the frozen multicriteria prioritization result. Consequently, differences in PROMETHEE membership or E2SFCA accessibility across P1–P4 are associations, not causal effects of demographic composition.\n')
text.append('## Profile-level integrated pattern\n')
for _,r in summary.iterrows():
    ep = 'NA' if pd.isna(r.mean_e2sfca_percentile_median) else f'{r.mean_e2sfca_percentile_median:.3f}'
    text.append(f"- P{int(r.som_profile)} (n={int(r.municipalities)}): PROMETHEE median rank {r.promethee_median_rank:.1f}; top-quartile share {r.promethee_top_quartile_share:.1%}; municipalities with complete E2SFCA service coverage {int(r.complete_e2sfca_count)}; median cross-service E2SFCA percentile among complete cases {ep}; concordant PROMETHEE-top-quartile/lower-E2SFCA count {int(r.concordant_top_priority_lower_access_count)}.\n")
if strong_corr is not None:
    text.append(f"\nAcross individual municipalities, the largest absolute service-specific Spearman association between E2SFCA percentile and PROMETHEE net flow occurs for `{strong_corr.service_type}` (rho={strong_corr.spearman_e2sfca_percentile_vs_promethee_net_flow:.3f}, n={int(strong_corr.n_complete)}). This is descriptive because accessibility-related information is conceptually related to the MCDM construction.\n")
text.append('\n## Interpretation constraints\n')
text.append('- Do not interpret P1–P4 as ordinal vulnerability or violence-risk levels.\n- Do not interpret E2SFCA missingness as zero accessibility.\n- Do not use the mean E2SFCA percentile as a new MCDM criterion or new ranking. It is only a visualization/synthesis aid for municipalities with complete service coverage.\n- The rural female share overlaps between SOM and MCDM and must be acknowledged when discussing cross-method associations.\n- The integrated result supports triangulation: E2SFCA describes potential service accessibility, PROMETHEE prioritizes municipalities under the frozen multicriteria model, and SOM describes the socioeconomic-demographic contexts in which these patterns occur.\n')
(OUT/'integrated_results_synthesis.md').write_text(''.join(text),encoding='utf-8')

audit={
    'stage':'Integrated frozen-results synthesis',
    'municipalities_in_som_promethee':int(len(sp)),
    'e2sfca_service_types':service_types,
    'expected_e2sfca_service_type_count':expected_services,
    'municipalities_with_complete_e2sfca_coverage':int(base.e2sfca_complete_service_coverage.sum()),
    'municipalities_with_incomplete_e2sfca_coverage':int((~base.e2sfca_complete_service_coverage).sum()),
    'lower_accessibility_quartile_cutoff_on_mean_percentile':float(low_access_cut),
    'higher_accessibility_quartile_cutoff_on_mean_percentile':float(high_access_cut),
    'no_synthetic_zero_for_missing_e2sfca':True,
    'e2sfca_raw_scores_preserved':True,
    'cross_service_mean_percentile_is_descriptive_only':True,
    'som_retrained':False,
    'promethee_reranked':False,
    'mcdm_weights_changed':False,
    'new_integrated_ranking_created':False,
    'outputs':[
        'results/integrated_synthesis/tables/integrated_municipal_e2sfca_mcdm_som.csv',
        'results/integrated_synthesis/tables/som_profile_e2sfca_service_summary.csv',
        'results/integrated_synthesis/tables/e2sfca_promethee_associations.csv',
        'results/integrated_synthesis/tables/integrated_profile_summary.csv',
        'results/integrated_synthesis/tables/integrated_top20_promethee_context.csv',
        'results/integrated_synthesis/figures/integrated_e2sfca_mcdm_som_panel.png',
        'results/integrated_synthesis/integrated_results_synthesis.md'
    ]
}
(TAB/'integrated_synthesis_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(audit,ensure_ascii=False,indent=2))
