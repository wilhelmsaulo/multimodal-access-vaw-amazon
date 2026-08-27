from __future__ import annotations

import argparse
from pathlib import Path
import yaml


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('screen_config', type=Path)
    p.add_argument('transfer_config', type=Path)
    args = p.parse_args()

    screen = yaml.safe_load(args.screen_config.read_text(encoding='utf-8'))
    transfer = yaml.safe_load(args.transfer_config.read_text(encoding='utf-8'))

    errors = []
    if screen['screening_rule'].get('synthetic_edge_allowed'):
        errors.append('synthetic hydro/ferry edges must remain disabled')
    if screen['screening_rule'].get('synthetic_time_allowed'):
        errors.append('synthetic hydro/ferry times must remain disabled')

    critical = {x['municipality'] for x in screen['critical_cases']}
    expected = {'Afua', 'Colares', 'Santa Cruz do Arari'}
    if critical != expected:
        errors.append(f'critical case set mismatch: {critical!r}')

    additional = screen.get('additional_statewide_cases_reopened', [])
    if additional:
        errors.append('bounded statewide screen must not silently reopen additional cases')

    t_by_name = {m['municipality_name']: m for m in transfer['municipalities']}
    for name in expected:
        if name not in t_by_name:
            errors.append(f'missing transfer policy for {name}')

    afua = t_by_name.get('Afua', {})
    afua_policy = afua.get('final_policy', {})
    if afua_policy.get('status') != 'coverage_scope_limited':
        errors.append('Afua final status must be coverage_scope_limited')
    if afua_policy.get('reopen_route_search') is not False:
        errors.append('Afua route search must be closed')
    if afua.get('transfer', {}).get('allowed_in_od'):
        errors.append('Afua must not receive an unvalidated OD edge')

    if errors:
        raise SystemExit('\n'.join(errors))

    print('STATEWIDE HYDRO ANOMALY SCREEN: PASS')
    print('Critical cases: Afua, Colares, Santa Cruz do Arari')
    print('Additional cases reopened: 0')
    print('Afua: final coverage/scope-limited hydro-first case; no synthetic edge.')
    print('Statewide open-ended terminal search: CLOSED under declared anomaly rule.')
    print('Next technical work: correct evidence-backed Colares and Santa Cruz transfers, then rebuild routing outputs.')


if __name__ == '__main__':
    main()
