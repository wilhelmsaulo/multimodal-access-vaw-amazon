from __future__ import annotations

import argparse
from pathlib import Path
import yaml


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('config', type=Path)
    args = p.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding='utf-8'))
    errors = []
    if cfg['policy'].get('synthetic_travel_time_allowed'):
        errors.append('synthetic travel time must remain disabled')
    if cfg['policy'].get('cartographic_distance_to_time_allowed'):
        errors.append('cartographic distance-to-time conversion must remain disabled')

    for m in cfg['municipalities']:
        t = m['transfer']
        if t.get('allowed_in_od'):
            pending_fields = [
                k for k, v in t.items()
                if ('status' in k) and isinstance(v, str) and ('pending' in v)
            ]
            if pending_fields:
                errors.append(
                    f"{m['municipality_name']}: allowed_in_od=true while pending: {pending_fields}"
                )

    if errors:
        raise SystemExit('\n'.join(errors))

    print('Reopened transfer audit gate passed.')
    print('All three municipalities remain blocked from corrected OD until temporal evidence is validated.')


if __name__ == '__main__':
    main()
