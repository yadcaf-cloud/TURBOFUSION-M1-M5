
#!/usr/bin/env python3
"""Publie un tableau de bord issu du dernier rapport, sans modifier les FIGES."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'rapports_turbofusion'
FIGES = ROOT / 'figes_turbofusion'

def load(path):
    with path.open(encoding='utf-8') as f:
        return json.load(f)

def main():
    reports = sorted(REPORTS.glob('turbofusion_*.json'))
    if not reports:
        raise SystemExit('Aucun rapport disponible : dashboard non remplace')

    latest = max(reports, key=lambda p: (p.stat().st_mtime_ns, p.name))
    data = load(latest)

    if not isinstance(data.get('courses'), list):
        raise SystemExit('Rapport invalide : courses absentes')

    figes = []
    for p in sorted(FIGES.glob('*.json')):
        try:
            f = load(p)
            if isinstance(f, dict) and isinstance(f.get('pronostic'), dict):
                figes.append({
                    'course': f.get('course'),
                    'date_course': f.get('date_course'),
                    'hippodrome': f.get('hippodrome'),
                    'depart_paris': f.get('depart_paris'),
                    'fige_a_paris': f.get('fige_a_paris'),
                    'moteur': f['pronostic'].get('moteur'),
                    'ordre_espere': f['pronostic'].get('ordre_espere', []),
                    'validation': 'FIGÉ',
                })
        except (OSError, ValueError, TypeError) as exc:
            print(f'AVERTISSEMENT : FIGÉ illisible {p}: {exc}')

    payload = {
        'logiciel': data.get('logiciel', 'TURBOFUSION M1-M5'),
        'date_courses': data.get('date_courses'),
        'cree_a_paris': data.get('cree_a_paris'),
        'courses': data['courses'],
        'figes': figes,
        'audits': [],
        'erreurs': data.get('erreurs', []),
        'source_rapport': str(latest.relative_to(ROOT)),
        'note': 'Pronostics experimentaux; aucun pari reel execute',
    }

    target = ROOT / 'dashboard.json'
    tmp = target.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(target)

    print(f'Dashboard synchronise : {len(data["courses"])} courses, {len(figes)} FIGES')

if __name__ == '__main__':
    main()
  
