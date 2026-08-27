from __future__ import annotations

import argparse
from pathlib import Path
import yaml

PENDING_MARKERS = ('pending', 'not_validated')


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('config', type=Path)
    args = p.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding='utf-8'))
    errors = []

    policy = cfg['policy']
    if policy.get('synthetic_travel_time_allowed'):
        errors.append('synthetic travel time must remain disabled')
    if policy.get('cartographic_distance_to_time_allowed'):
        errors.append('cartographic distance-to-time conversion must remain disabled')
    if policy.get('unvalidated_waiting_time_allowed'):
        errors.append('unvalidated waiting time must remain disabled')

    warning = cfg.get('backbone_structural_warning', {})
    if warning.get('frozen_materialized_road_hydro_terminal_identities') != 3:
        errors.append('expected frozen structural warning to record exactly 3 materialized road-hydro terminal identities')

    for m in cfg['municipalities']:
        t = m['transfer']
        if t.get('allowed_in_od'):
            unresolved = []
            for k, v in t.items():
                if 'status' not in k or not isinstance(v, str):
                    continue
                if any(marker in v for marker in PENDING_MARKERS):
                    unresolved.append(k)
            if unresolved:
                errors.append(
                    f"{m['municipality_name']}: allowed_in_od=true while unresolved: {unresolved}"
                )

    if errors:
        raise SystemExit('\n'.join(errors))

    print('Reopened transfer audit gate passed.')
    print('MCDM ranking remains blocked until corrected network evidence is complete.')
    for m in cfg['municipalities']:
        print(f"- {m['municipality_name']}: allowed_in_od={m['transfer'].get('allowed_in_od')}; diagnosis={m['revised_diagnosis']}")


if __name__ == '__main__':
    main()
