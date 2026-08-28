from pathlib import Path
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
subprocess.run([sys.executable,'-m','src.analysis.publish_integrated_e2sfca_mcdm_som_synthesis'],cwd=ROOT,check=True)
path=ROOT/'results/integrated_synthesis/tables/integrated_synthesis_audit.json'
a=json.loads(path.read_text(encoding='utf-8'))
total=int(a['municipalities_in_som_promethee'])
complete=int(a['municipalities_with_complete_e2sfca_coverage'])
a['municipalities_with_incomplete_e2sfca_coverage']=total-complete
assert total==144
assert 0 <= a['municipalities_with_incomplete_e2sfca_coverage'] <= total
assert complete + a['municipalities_with_incomplete_e2sfca_coverage'] == total
path.write_text(json.dumps(a,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(a,ensure_ascii=False,indent=2))
