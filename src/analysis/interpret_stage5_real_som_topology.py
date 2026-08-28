from pathlib import Path
import json
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
T = ROOT / 'results' / 'stage5' / 'tables'
F = ROOT / 'results' / 'stage5' / 'figures'
F.mkdir(parents=True, exist_ok=True)

CODEBOOK = T / 'stage5_som_selected_codebook.csv'
NODES = T / 'stage5_som_node_profiles.csv'

FEATURE_LABELS = {
    'criterion__rural_female_share': 'Rural female share',
    'socio__female_literacy_rate_15plus': 'Female literacy 15+',
    'socio__household_per_capita_income_mean_brl': 'Household per-capita income',
    'profile__female_age_ilr_1': 'Age ILR1',
    'profile__female_age_ilr_2': 'Age ILR2',
    'profile__female_age_ilr_3': 'Age ILR3',
    'profile__female_race_ilr_1': 'Race/color ILR1',
    'profile__female_race_ilr_2': 'Race/color ILR2',
    'profile__female_race_ilr_3': 'Race/color ILR3',
    'profile__female_race_ilr_4': 'Race/color ILR4',
}


def profile_pair(a, b):
    a, b = int(a), int(b)
    return (a, b) if a < b else (b, a)


def main():
    cb = pd.read_csv(CODEBOOK)
    nd = pd.read_csv(NODES)
    df = cb.merge(nd, on=['som_row', 'som_col'], validate='one_to_one')
    feature_cols = [c for c in cb.columns if c not in ['som_row', 'som_col']]
    assert len(df) == 25
    assert len(feature_cols) == 10
    assert int(df['municipality_count'].sum()) == 144

    # Moore-neighborhood edges, each undirected pair once.
    by_coord = {(int(r.som_row), int(r.som_col)): r for r in df.itertuples(index=False)}
    edges = []
    for (r, c), row in by_coord.items():
        va = np.array([getattr(row, f) for f in feature_cols], dtype=float)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                rr, cc = r + dr, c + dc
                if (rr, cc) not in by_coord or (rr, cc) <= (r, c):
                    continue
                nbr = by_coord[(rr, cc)]
                vb = np.array([getattr(nbr, f) for f in feature_cols], dtype=float)
                diff = vb - va
                dist = float(np.linalg.norm(diff))
                rec = {
                    'row_a': r, 'col_a': c, 'profile_a': int(row.som_profile),
                    'row_b': rr, 'col_b': cc, 'profile_b': int(nbr.som_profile),
                    'euclidean_codebook_distance': dist,
                    'cross_profile': int(row.som_profile) != int(nbr.som_profile),
                }
                p1, p2 = profile_pair(row.som_profile, nbr.som_profile)
                rec['profile_pair'] = f'P{p1}-P{p2}' if p1 != p2 else f'P{p1}-P{p1}'
                for f, d in zip(feature_cols, diff):
                    rec[f'delta__{f}'] = float(d)
                    rec[f'abs_delta__{f}'] = float(abs(d))
                edges.append(rec)

    edge_df = pd.DataFrame(edges)
    cross = edge_df[edge_df['cross_profile']].copy()
    edge_df.to_csv(T / 'stage5_som_real_topology_edges.csv', index=False)

    # Cross-profile boundary strength.
    summary_rows = []
    contrib_rows = []
    for pair, g in cross.groupby('profile_pair', sort=True):
        d = g['euclidean_codebook_distance']
        summary_rows.append({
            'profile_pair': pair,
            'boundary_edge_count': int(len(g)),
            'mean_boundary_distance': float(d.mean()),
            'median_boundary_distance': float(d.median()),
            'min_boundary_distance': float(d.min()),
            'max_boundary_distance': float(d.max()),
        })
        mean_abs = {f: float(g[f'abs_delta__{f}'].mean()) for f in feature_cols}
        denom = sum(mean_abs.values())
        ranked = sorted(mean_abs.items(), key=lambda kv: kv[1], reverse=True)
        for rank, (f, val) in enumerate(ranked, 1):
            contrib_rows.append({
                'profile_pair': pair,
                'rank': rank,
                'feature': f,
                'feature_label': FEATURE_LABELS[f],
                'mean_absolute_standardized_difference': val,
                'share_of_l1_boundary_difference': float(val / denom) if denom else np.nan,
            })

    summary = pd.DataFrame(summary_rows).sort_values('mean_boundary_distance', ascending=False)
    contrib = pd.DataFrame(contrib_rows)
    summary.to_csv(T / 'stage5_som_real_profile_transition_summary.csv', index=False)
    contrib.to_csv(T / 'stage5_som_real_transition_feature_contributions.csv', index=False)

    # Municipality-count-weighted profile codebook centroids (descriptive only).
    centroids = []
    for p, g in df.groupby('som_profile', sort=True):
        w = g['municipality_count'].to_numpy(float)
        rec = {'som_profile': int(p), 'municipalities': int(w.sum()), 'neurons': int(len(g))}
        for f in feature_cols:
            rec[f] = float(np.average(g[f].to_numpy(float), weights=w))
        centroids.append(rec)
    pd.DataFrame(centroids).to_csv(T / 'stage5_som_real_profile_codebook_centroids.csv', index=False)

    # Matrix of observed boundary strength among directly adjacent profiles.
    profiles = [1, 2, 3, 4]
    mat = np.full((4, 4), np.nan)
    np.fill_diagonal(mat, 0.0)
    for r in summary.itertuples(index=False):
        a, b = [int(x[1:]) for x in r.profile_pair.split('-')]
        mat[a-1, b-1] = mat[b-1, a-1] = r.mean_boundary_distance

    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    masked = np.ma.masked_invalid(mat)
    im = ax.imshow(masked)
    ax.set_xticks(range(4), [f'P{i}' for i in profiles])
    ax.set_yticks(range(4), [f'P{i}' for i in profiles])
    ax.set_title('SOM macroprofile boundary strength\n(mean codebook distance across adjacent neurons)')
    for i in range(4):
        for j in range(4):
            if i == j:
                ax.text(j, i, '—', ha='center', va='center')
            elif np.isfinite(mat[i, j]):
                ax.text(j, i, f'{mat[i,j]:.2f}', ha='center', va='center')
            else:
                ax.text(j, i, 'not adjacent', ha='center', va='center', fontsize=8)
    fig.colorbar(im, ax=ax, label='Mean Euclidean codebook distance')
    fig.tight_layout()
    fig.savefig(F / 'stage5_som_real_profile_transition_matrix.png', dpi=300)
    fig.savefig(F / 'stage5_som_real_profile_transition_matrix.pdf')
    plt.close(fig)

    # Top three feature contrasts at each observed boundary.
    pairs = summary['profile_pair'].tolist()
    top = contrib[contrib['rank'] <= 3].copy()
    fig, axes = plt.subplots(len(pairs), 1, figsize=(8.2, max(3.2, 2.35 * len(pairs))), squeeze=False)
    for ax, pair in zip(axes[:, 0], pairs):
        g = top[top['profile_pair'] == pair].sort_values('mean_absolute_standardized_difference')
        ax.barh(g['feature_label'], g['mean_absolute_standardized_difference'])
        ax.set_title(f'{pair}: strongest component-plane contrasts along the shared SOM boundary')
        ax.set_xlabel('Mean absolute standardized codebook difference')
    fig.tight_layout()
    fig.savefig(F / 'stage5_som_real_transition_feature_contributions.png', dpi=300)
    fig.savefig(F / 'stage5_som_real_transition_feature_contributions.pdf')
    plt.close(fig)

    audit = {
        'stage': 'Stage 5 real SOM topology interpretation',
        'source_model_retrained': False,
        'profile_reclassification_performed': False,
        'mcdm_feedback': False,
        'neighbor_definition': 'Moore neighborhood on frozen 5x5 rectangular SOM; undirected adjacent neuron pairs counted once',
        'cross_profile_boundary_definition': 'an adjacent neuron pair whose frozen macroprofile IDs differ',
        'boundary_strength': 'Euclidean distance between standardized frozen SOM codebook vectors',
        'feature_contribution': 'mean absolute standardized codebook difference across all boundary edges for a profile pair; descriptive decomposition only',
        'weighted_profile_codebook_centroids': 'codebook prototypes weighted by frozen municipality hits; descriptive only',
        'municipalities': 144,
        'neurons': 25,
        'features': 10,
        'total_neighbor_edges': int(len(edge_df)),
        'cross_profile_edges': int(len(cross)),
        'observed_adjacent_profile_pairs': summary['profile_pair'].tolist(),
        'nonadjacent_profile_pairs_are_not_assigned_artificial_distances': True,
        'outputs': [
            'results/stage5/tables/stage5_som_real_topology_edges.csv',
            'results/stage5/tables/stage5_som_real_profile_transition_summary.csv',
            'results/stage5/tables/stage5_som_real_transition_feature_contributions.csv',
            'results/stage5/tables/stage5_som_real_profile_codebook_centroids.csv',
            'results/stage5/figures/stage5_som_real_profile_transition_matrix.png',
            'results/stage5/figures/stage5_som_real_profile_transition_matrix.pdf',
            'results/stage5/figures/stage5_som_real_transition_feature_contributions.png',
            'results/stage5/figures/stage5_som_real_transition_feature_contributions.pdf',
        ],
    }
    (T / 'stage5_som_real_topology_interpretation_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')

    print(summary.to_string(index=False))
    print('\nTop boundary features:')
    print(top.sort_values(['profile_pair','rank']).to_string(index=False))


if __name__ == '__main__':
    main()
