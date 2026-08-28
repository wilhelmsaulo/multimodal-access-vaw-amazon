from pathlib import Path

import matplotlib.image as mpimg
import matplotlib.pyplot as plt

ROOT = Path('results/stage5')
FIG = ROOT / 'figures'


def main():
    sources = [
        FIG / 'stage5_som_profiles_pará_map.png',
        FIG / 'stage5_som_profile_characteristics_heatmap.png',
        FIG / 'stage5_som_mcdm_profile_association.png',
    ]
    for p in sources:
        if not p.exists():
            raise FileNotFoundError(p)

    fig = plt.figure(figsize=(16, 16))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.25, 1.0])
    axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, :])]
    titles = [
        'A. Spatial distribution of SOM profiles',
        'B. Profile-level association with frozen PROMETHEE II',
        'C. Sociodemographic profile signatures',
    ]
    # Arrange map, association, heatmap for manuscript readability.
    ordered = [sources[0], sources[2], sources[1]]
    for ax, path, title in zip(axes, ordered, titles):
        ax.imshow(mpimg.imread(path))
        ax.set_title(title, fontsize=14, loc='left')
        ax.axis('off')
    fig.suptitle('Stage 5 SOM socioeconomic/demographic profiling — Pará', fontsize=18, y=0.995)
    fig.text(
        0.5, 0.008,
        'Profiles P1–P4 are neutral descriptive groups. PROMETHEE-II comparison is post-hoc and does not feed back into the MCDM ranking.',
        ha='center', fontsize=10,
    )
    fig.tight_layout(rect=[0, 0.02, 1, 0.98])
    fig.savefig(FIG / 'stage5_final_som_interpretation_panel.png', dpi=220, bbox_inches='tight')
    fig.savefig(FIG / 'stage5_final_som_interpretation_panel.pdf', bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    main()
