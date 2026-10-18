#!/usr/bin/env python3
"""TURBOFUSION V1 — analyse expérimentale, aucun pari réel."""
import argparse, datetime as dt, hashlib, json, os, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Europe/Paris')
BASES = [
    'https://offline.turfinfo.api.pmu.fr/rest/client/7/',
    'https://online.turfinfo.api.pmu.fr/rest/client/1/'
]
DATA = Path(os.getenv('TURBO_DATA', 'data'))

def now():
    return dt.datetime.now(TZ)

def fetch(path):
    errors = []
    for base in BASES:
        try:
            req = urllib.request.Request(
                base + path,
                headers={
                    'User-Agent': 'TURBOFUSION-M1-M5/1.0',
                    'Accept': 'application/json'
                }
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                return json.load(response)
        except Exception as exc:
            errors.append(f'{base}: {type(exc).__name__}: {exc}')
    raise RuntimeError('Sources indisponibles: ' + ' | '.join(errors))

def collect(day):
    raw = fetch('programme/' + day.strftime('%d%m%Y'))
    DATA.mkdir(parents=True, exist_ok=True)
    target = DATA / f'programme_{day.isoformat()}.json'
    target.write_text(json.dumps({
        'collecte': now().isoformat(),
        'source': 'PMU endpoint candidat',
        'donnees': raw
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    return target, raw

def extract_races(raw):
    meetings = raw.get('programme', {}).get('reunions', []) if isinstance(raw, dict) else []
    for meeting in meetings:
        country = str(meeting.get('pays', meeting.get('paysCode', ''))).upper()
        if country not in ('FRA', 'FR', 'FRANCE'):
            continue
        for race in meeting.get('courses', []):
            yield {
                'reunion': meeting.get('numOfficiel'),
                'course': race.get('numOrdre'),
                'hippodrome': meeting.get('hippodrome', {}).get('libelleCourt')
                if isinstance(meeting.get('hippodrome'), dict) else None,
                'depart_ms': race.get('heureDepart'),
                'partants': race.get('nombrePartants')
            }

def analyze(raw, day):
    """Audit de programme uniquement: aucun score sans partants détaillés vérifiés."""
    result = {
        'version': '1.0',
        'date': day.isoformat(),
        'cree_a': now().isoformat(),
        'courses': []
    }
    for race in extract_races(raw):
        race.update({
            'moteurs': {
                f'M{i}': {
                    'statut': 'DONNEES_INSUFFISANTES',
                    'selection': None
                } for i in range(1, 6)
            },
            'fige': False
        })
        result['courses'].append(race)

    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / f'audit_{day.isoformat()}.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return path, result

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--date', default=now().date().isoformat())
    p.add_argument('--diagnostic', action='store_true')
    args = p.parse_args()
    day = dt.date.fromisoformat(args.date)
    try:
        path, raw = collect(day)
        audit, result = analyze(raw, day)
        print(json.dumps({
            'etat': 'collecte_ok',
            'programme': str(path),
            'audit': str(audit),
            'courses_francaises': len(result['courses']),
            'pronostics': 'non actives tant que donnees partants non verifiees'
        }, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({
            'etat': 'erreur_connexion',
            'detail': str(exc)
        }, ensure_ascii=False))
        raise SystemExit(1)

if __name__ == '__main__':
    main()
