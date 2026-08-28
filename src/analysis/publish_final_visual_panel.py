from __future__ import annotations
import argparse,json
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

PANELS=[
 ('A','Equipamentos e serviços','results/stage1_services/figures/all_service_sites.png'),
 ('B','Rede multimodal corrigida','results/stage2_network/figures/statewide_multimodal_network.png'),
 ('C','Situação setorial na rede de referência','results/stage1_sector_origins/figures/sector_reference_network_access.png'),
 ('D','E2SFCA — agregação municipal por tipo','results/e2sfca/figures/reference_municipal_maps.png'),
 ('E','PROMETHEE II — priorização municipal','results/stage4/figures/promethee_ii_rank_map.png'),
 ('F','TOPSIS — ranking de contraste','results/stage4/figures/topsis_rank_map.png'),
]
def main():
 p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,default=Path('.')); p.add_argument('--out',type=Path,default=Path('results/final_visual_panel')); a=p.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
 fig,axs=plt.subplots(2,3,figsize=(22,14),facecolor='white')
 for ax,(letter,title,rel) in zip(axs.ravel(),PANELS):
  q=a.root/rel
  if not q.exists(): raise FileNotFoundError(q)
  ax.imshow(mpimg.imread(q)); ax.set_axis_off(); ax.set_title(f'{letter}  {title}',loc='left',fontsize=14,fontweight='bold',pad=8)
 fig.suptitle('Acesso multimodal e priorização da resposta à violência contra as mulheres no Pará',fontsize=20,fontweight='bold',y=.985)
 fig.text(.01,.008,'Fontes: IBGE Censo 2022; CNES; MDS/SAGI; PCPA/SEGUP; TJPA; rede multimodal corrigida e resultados analíticos do projeto (2026). Cada mapa individual preserva sua legenda, fonte e referência cartográfica.',fontsize=8)
 fig.subplots_adjust(left=.015,right=.99,top=.945,bottom=.03,wspace=.025,hspace=.08)
 fig.savefig(a.out/'final_multimethod_panel.png',dpi=300,bbox_inches='tight',facecolor='white')
 fig.savefig(a.out/'final_multimethod_panel.pdf',bbox_inches='tight',facecolor='white'); plt.close(fig)
 (a.out/'README.md').write_text('# Item 5 — painel visual final\n\n![Painel final](final_multimethod_panel.png)\n\nO painel reúne: (A) serviços, (B) rede multimodal, (C) situação dos setores, (D) E2SFCA municipal, (E) PROMETHEE II e (F) TOPSIS. Uma versão PDF em alta resolução acompanha a figura.\n',encoding='utf-8')
 (a.out/'publication_metadata.json').write_text(json.dumps({'item':5,'status':'published','panels':[{'label':x[0],'title':x[1],'source':x[2]} for x in PANELS],'formats':['png','pdf']},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__': main()
