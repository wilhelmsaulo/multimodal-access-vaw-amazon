from pathlib import Path
import json
import math
import itertools
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parents[2]
INP = ROOT / 'results' / 'integrated_synthesis' / 'tables' / 'integrated_municipal_e2sfca_mcdm_som.csv'
OUT = ROOT / 'results' / 'posthoc_statistics'
TAB = OUT / 'tables'
FIG = OUT / 'figures'
OUT.mkdir(parents=True, exist_ok=True)
TAB.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(INP)
df['som_profile'] = pd.to_numeric(df['som_profile'], errors='coerce').astype('Int64')
profiles = [1,2,3,4]
alpha = 0.05

# Outcomes external to SOM construction. The E2SFCA percentiles are used only because
# they preserve the within-service order while putting the four services on a common 0-1 scale.
outcomes = {
    'e2sfca_creas': ('e2sfca_percentile__creas', 'E2SFCA CREAS percentile'),
    'e2sfca_health': ('e2sfca_percentile__health', 'E2SFCA health percentile'),
    'e2sfca_specialized_justice': ('e2sfca_percentile__specialized_justice', 'E2SFCA specialized justice percentile'),
    'e2sfca_specialized_security': ('e2sfca_percentile__specialized_security', 'E2SFCA specialized security percentile'),
    'promethee_net_flow': ('promethee_net_flow', 'PROMETHEE-II net flow'),
    'promethee_rank': ('promethee_rank', 'PROMETHEE-II rank'),
    'robustness_top_quartile_probability': ('robustness_top_quartile_probability', 'Robust top-quartile probability'),
}

def epsilon_squared_kw(H, n, k):
    if n <= k:
        return np.nan
    return max(0.0, (H - k + 1) / (n - k))

def epsilon_label(e):
    # Common descriptive thresholds for rank-based epsilon-squared.
    if pd.isna(e): return 'NA'
    if e < 0.01: return 'negligible'
    if e < 0.06: return 'small'
    if e < 0.14: return 'moderate'
    return 'large'

def welch_anova(groups):
    # Welch one-way ANOVA from group means/variances/sample sizes.
    vals = [np.asarray(g, dtype=float) for g in groups if len(g) >= 2]
    k = len(vals)
    if k < 2: return (np.nan, np.nan, np.nan, np.nan)
    n = np.array([len(g) for g in vals], dtype=float)
    means = np.array([g.mean() for g in vals])
    vars_ = np.array([g.var(ddof=1) for g in vals])
    # Constant group protection.
    vars_ = np.where(vars_ <= 0, np.finfo(float).eps, vars_)
    w = n / vars_
    wsum = w.sum()
    ybar = (w * means).sum() / wsum
    numerator = (w * (means - ybar)**2).sum() / (k - 1)
    term = np.sum(((1 - w/wsum)**2) / (n - 1))
    denominator = 1 + (2 * (k - 2) / (k**2 - 1)) * term
    F = numerator / denominator
    df1 = k - 1
    df2 = (k**2 - 1) / (3 * term) if term > 0 else np.inf
    p = stats.f.sf(F, df1, df2)
    return F, df1, df2, p

def dunn_pairwise(data, value_col, group_col='som_profile'):
    d = data[[group_col, value_col]].dropna().copy()
    d['rank_all'] = stats.rankdata(d[value_col].to_numpy(), method='average')
    N = len(d)
    if N < 2: return pd.DataFrame()
    # Tie correction following Dunn's variance formulation.
    _, counts = np.unique(d[value_col].to_numpy(), return_counts=True)
    tie_sum = np.sum(counts**3 - counts)
    var_rank = (N * (N + 1) / 12.0) - (tie_sum / (12.0 * (N - 1))) if N > 1 else np.nan
    ranks = d.groupby(group_col)['rank_all'].mean()
    ns = d.groupby(group_col).size()
    rows=[]
    for a,b in itertools.combinations(sorted(ranks.index),2):
        se = math.sqrt(var_rank * (1/ns.loc[a] + 1/ns.loc[b]))
        z = (ranks.loc[a] - ranks.loc[b]) / se if se > 0 else np.nan
        p = 2*stats.norm.sf(abs(z)) if pd.notna(z) else np.nan
        rows.append({'profile_a':int(a),'profile_b':int(b),'z':z,'p_raw':p})
    out=pd.DataFrame(rows)
    if len(out):
        mask=out['p_raw'].notna()
        out.loc[mask,'p_holm']=multipletests(out.loc[mask,'p_raw'], alpha=alpha, method='holm')[1]
        out['significant_holm_0_05']=out['p_holm'] < alpha
    return out

global_rows=[]
posthoc_rows=[]
desc_rows=[]

for key,(col,label) in outcomes.items():
    d=df[['som_profile',col]].dropna()
    groups=[]
    for p in profiles:
        vals=d.loc[d.som_profile==p,col].astype(float).to_numpy()
        groups.append(vals)
        desc_rows.append({
            'outcome':key,'outcome_label':label,'som_profile':p,'n':len(vals),
            'mean':float(np.mean(vals)) if len(vals) else np.nan,
            'sd':float(np.std(vals,ddof=1)) if len(vals)>1 else np.nan,
            'median':float(np.median(vals)) if len(vals) else np.nan,
            'q1':float(np.quantile(vals,.25)) if len(vals) else np.nan,
            'q3':float(np.quantile(vals,.75)) if len(vals) else np.nan,
        })
    nonempty=[g for g in groups if len(g)>0]
    H,p_kw=stats.kruskal(*nonempty)
    n=sum(len(g) for g in nonempty); k=len(nonempty)
    eps=epsilon_squared_kw(H,n,k)
    F,df1,df2,p_w=welch_anova(nonempty)
    lev_stat,lev_p=stats.levene(*nonempty, center='median')
    global_rows.append({
        'outcome':key,'outcome_label':label,'n_complete':n,'groups':k,
        'kruskal_H':H,'kruskal_df':k-1,'kruskal_p':p_kw,
        'epsilon_squared':eps,'epsilon_squared_magnitude':epsilon_label(eps),
        'welch_F':F,'welch_df1':df1,'welch_df2':df2,'welch_p_sensitivity':p_w,
        'brown_forsythe_levene_stat':lev_stat,'brown_forsythe_levene_p':lev_p,
        'primary_global_significant_0_05':bool(p_kw<alpha),
    })
    if p_kw < alpha:
        po=dunn_pairwise(df, col)
        if len(po):
            po.insert(0,'outcome_label',label)
            po.insert(0,'outcome',key)
            posthoc_rows.extend(po.to_dict('records'))

global_df=pd.DataFrame(global_rows)
desc_df=pd.DataFrame(desc_rows)
posthoc_df=pd.DataFrame(posthoc_rows)
global_df.to_csv(TAB/'posthoc_global_tests.csv',index=False)
desc_df.to_csv(TAB/'posthoc_group_descriptives.csv',index=False)
posthoc_df.to_csv(TAB/'posthoc_dunn_holm.csv',index=False)

# Categorical association: SOM profile x PROMETHEE top-quartile membership.
ct=pd.crosstab(df['som_profile'], df['top_quartile'].astype(bool)).reindex(profiles, fill_value=0)
chi2,p_chi,dof,expected=stats.chi2_contingency(ct)
n=ct.to_numpy().sum(); r,c=ct.shape
cramers_v=math.sqrt(chi2/(n*min(r-1,c-1))) if min(r-1,c-1)>0 else np.nan
chi=pd.DataFrame([{
    'test':'SOM profile x PROMETHEE top-quartile membership',
    'n':int(n),'chi_square':chi2,'df':dof,'p_value':p_chi,'cramers_v':cramers_v,
    'significant_0_05':bool(p_chi<alpha)
}])
chi.to_csv(TAB/'posthoc_chi_square_top_quartile.csv',index=False)
ct_out=ct.copy(); ct_out.columns=['not_top_quartile','top_quartile'] if len(ct_out.columns)==2 else [str(x) for x in ct_out.columns]
ct_out.reset_index().to_csv(TAB/'posthoc_top_quartile_contingency.csv',index=False)

# Holm correction across the family of primary global Kruskal-Wallis tests.
global_df['kruskal_p_holm_across_outcomes']=multipletests(global_df['kruskal_p'], alpha=alpha, method='holm')[1]
global_df['global_significant_holm_across_outcomes_0_05']=global_df['kruskal_p_holm_across_outcomes']<alpha
global_df.to_csv(TAB/'posthoc_global_tests.csv',index=False)

# Publication-ready summary table.
pub=global_df[['outcome_label','n_complete','kruskal_H','kruskal_df','kruskal_p','kruskal_p_holm_across_outcomes','epsilon_squared','epsilon_squared_magnitude','welch_F','welch_df1','welch_df2','welch_p_sensitivity']].copy()
pub.to_csv(TAB/'posthoc_publication_summary.csv',index=False)

# Compact figure: -log10 p and epsilon-squared for primary global tests.
fig,ax=plt.subplots(figsize=(9,5.2))
y=np.arange(len(global_df))
vals=-np.log10(np.clip(global_df['kruskal_p_holm_across_outcomes'].to_numpy(float),1e-300,1))
ax.barh(y, vals)
ax.axvline(-np.log10(alpha),ls='--',lw=1)
ax.set_yticks(y,global_df['outcome_label'])
ax.set_xlabel('-log10 Holm-adjusted Kruskal–Wallis p-value')
ax.set_title('Post-hoc differences across neutral SOM profiles')
ax.invert_yaxis()
for i,(v,e) in enumerate(zip(vals,global_df['epsilon_squared'])):
    ax.text(v+0.05,i,f'ε²={e:.3f}',va='center',fontsize=8)
fig.tight_layout(); fig.savefig(FIG/'posthoc_global_tests_effects.png',dpi=300,bbox_inches='tight'); fig.savefig(FIG/'posthoc_global_tests_effects.pdf',bbox_inches='tight'); plt.close(fig)

# Pairwise significance matrix count by profile pair across outcomes.
if len(posthoc_df):
    sig=posthoc_df[posthoc_df['significant_holm_0_05']].copy()
    pairs=[(1,2),(1,3),(1,4),(2,3),(2,4),(3,4)]
    pair_counts=[]
    for a,b in pairs:
        pair_counts.append({'profile_pair':f'P{a}-P{b}','significant_outcome_count':int(((sig.profile_a==a)&(sig.profile_b==b)).sum())})
    pd.DataFrame(pair_counts).to_csv(TAB/'posthoc_pairwise_significant_counts.csv',index=False)

# Manuscript-ready report.
lines=['# Post-hoc statistical assessment of SOM profile associations\n']
lines.append('The tests in this section are applied to outcomes that were not used to construct the SOM profiles: E2SFCA service-specific accessibility, frozen PROMETHEE-II outputs, and the robustness-derived probability of top-quartile membership. They do not provide an independent inferential validation of the socioeconomic/demographic variables used to train the SOM.\n')
lines.append('Kruskal–Wallis is the primary global test because the groups are unequal in size and several outcomes are bounded, ranked, zero-inflated, or asymmetric. Dunn pairwise comparisons are performed only after a significant global result and are Holm-adjusted. Epsilon-squared (ε²) is reported as the rank-based effect size. Welch one-way ANOVA is retained only as a sensitivity analysis.\n')
lines.append('## Global tests\n')
for _,r in global_df.iterrows():
    lines.append(f"- **{r.outcome_label}:** H({int(r.kruskal_df)})={r.kruskal_H:.3f}, p={r.kruskal_p:.4g}, Holm(global)={r.kruskal_p_holm_across_outcomes:.4g}, ε²={r.epsilon_squared:.3f} ({r.epsilon_squared_magnitude}); Welch sensitivity p={r.welch_p_sensitivity:.4g}.\n")
lines.append(f"\nFor SOM profile × PROMETHEE top-quartile membership, χ²({int(dof)})={chi2:.3f}, p={p_chi:.4g}, Cramér's V={cramers_v:.3f}.\n")
if len(posthoc_df):
    lines.append('\n## Pairwise Dunn–Holm results\n')
    for outcome,gg in posthoc_df.groupby('outcome_label'):
        s=gg[gg.significant_holm_0_05]
        if len(s):
            pairs_txt=', '.join([f"P{int(x.profile_a)}–P{int(x.profile_b)} (pHolm={x.p_holm:.4g})" for _,x in s.iterrows()])
            lines.append(f'- **{outcome}:** {pairs_txt}.\n')
        else:
            lines.append(f'- **{outcome}:** no pair remained significant after Holm correction.\n')
lines.append('\n## Interpretation guardrails\n- Statistical differences between P1–P4 do not make the profile IDs ordinal risk levels.\n- P-values are interpreted together with ε² or Cramér\'s V.\n- The rural female share is shared conceptually between SOM and MCDM, so PROMETHEE associations are not treated as fully independent of every SOM input.\n- E2SFCA missingness is preserved; Afuá is excluded only from tests requiring an observed E2SFCA value and never receives a synthetic zero.\n- These analyses are post-hoc association tests and do not alter SOM training, MCDM weights/ranking, or E2SFCA outputs.\n')
(OUT/'posthoc_statistical_results.md').write_text(''.join(lines),encoding='utf-8')

audit={
    'stage':'Post-hoc statistical assessment of SOM profile associations',
    'input':'results/integrated_synthesis/tables/integrated_municipal_e2sfca_mcdm_som.csv',
    'municipalities':int(len(df)),
    'profiles':profiles,
    'primary_test':'Kruskal-Wallis',
    'primary_global_multiple_testing':'Holm correction across seven outcome-level Kruskal-Wallis tests',
    'pairwise_test':'Dunn test after significant global Kruskal-Wallis, Holm correction within each outcome',
    'effect_size_continuous':'epsilon-squared',
    'categorical_test':'Pearson chi-square for SOM profile x PROMETHEE top-quartile membership',
    'categorical_effect_size':'Cramer V',
    'sensitivity_test':'Welch one-way ANOVA',
    'variance_diagnostic':'Brown-Forsythe/Levene test centered at median',
    'som_training_variables_tested_as_independent_validation':False,
    'som_retrained':False,
    'promethee_reranked':False,
    'e2sfca_recomputed':False,
    'outputs':[
        'results/posthoc_statistics/tables/posthoc_global_tests.csv',
        'results/posthoc_statistics/tables/posthoc_dunn_holm.csv',
        'results/posthoc_statistics/tables/posthoc_chi_square_top_quartile.csv',
        'results/posthoc_statistics/tables/posthoc_group_descriptives.csv',
        'results/posthoc_statistics/tables/posthoc_publication_summary.csv',
        'results/posthoc_statistics/figures/posthoc_global_tests_effects.png',
        'results/posthoc_statistics/posthoc_statistical_results.md'
    ]
}
(TAB/'posthoc_statistics_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(audit,ensure_ascii=False,indent=2))
