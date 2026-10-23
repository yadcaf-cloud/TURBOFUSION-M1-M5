#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TURBOFUSION M1-M5 v2.0 - Analyse expérimentale PMU.
Aucun pari réel. FIGES append-only, jamais recalcules apres leur creation.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo('Europe/Paris')
OUT = Path('rapports_turbofusion')
FIGES = Path('figes_turbofusion')
BASES = [
    'https://offline.turfinfo.api.pmu.fr/rest/client/7/',
    'https://online.turfinfo.api.pmu.fr/rest/client/1/',
]
USER_AGENT = 'Mozilla/5.0 (compatible; TURBOFUSION/2.0; diagnostic PMU)'


def now():
    return dt.datetime.now(PARIS)


def as_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def as_float(value):
    try:
        number = float(str(value).replace(',', '.'))
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def pick(obj, *keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        value = obj.get(key)
        if value is not None and value != '':
            return value
    return None


def label(value):
    if isinstance(value, dict):
        return str(pick(value, 'libelleCourt', 'libelleLong', 'libelle', 'nom', 'code', 'codePays') or '')
    return str(value or '')


def fetch(path):
    errors = []
    for base in BASES:
        url = base + path.lstrip('/')
        for attempt in range(2):
            request = urllib.request.Request(url, headers={
                'Accept': 'application/json', 'User-Agent': USER_AGENT
            })
            try:
                with urllib.request.urlopen(request, timeout=18) as response:
                    raw = response.read(8_000_001)
                    if len(raw) > 8_000_000:
                        raise ValueError('reponse trop volumineuse')
                    return json.loads(raw.decode('utf-8-sig')), url
            except (urllib.error.URLError, TimeoutError, ValueError,
                    UnicodeError, json.JSONDecodeError) as exc:
                errors.append(f'{url} essai {attempt + 1}: {type(exc).__name__}: {exc}')
                if attempt == 0:
                    time.sleep(1)
    raise RuntimeError(' | '.join(errors))


def meetings_from(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        raise ValueError('programme PMU non conforme')
    for node in (data.get('programme'), data):
        if isinstance(node, dict):
            for key in ('reunions', 'réunions'):
                value = node.get(key)
                if isinstance(value, list):
                    return value
    raise ValueError('aucune liste reunions dans la reponse; cles=' + ','.join(data.keys()))


def country_of(meeting):
    value = pick(meeting, 'pays', 'codePays', 'paysCode', 'country')
    if isinstance(value, dict):
        value = pick(value, 'code', 'codePays', 'libelle', 'nom')
    return str(value or '').strip().upper()


def french_meeting(meeting):
    country = country_of(meeting)
    # Si le pays est absent, ne pas inventer une localisation.
    return country in {'FR', 'FRA', 'FRANCE', 'FRANÇAIS', 'FRANCAIS'}


def departure(value):
    if value is None:
        return None
    try:
        if isinstance(value, (float, int)) or str(value).isdigit():
            number = float(value)
            if number > 1e11:
                number /= 1000
            return dt.datetime.fromtimestamp(number, PARIS)
        parsed = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.astimezone(PARIS) if parsed.tzinfo else None
    except (ValueError, OverflowError, OSError):
        return None


def participants_from(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ('participants', 'partants'):
            if isinstance(data.get(key), list):
                return data[key]
    raise ValueError('liste participants absente ou invalide')


def horse(item):
    music = str(pick(item, 'musique', 'musiqueCheval') or '')
    return {
        'numero': as_int(pick(item, 'numPmu', 'numero', 'numOrdre')),
        'nom': str(pick(item, 'nom', 'nomCheval') or 'Inconnu'),
        'musique': music,
        'age': as_int(item.get('age')),
        'jockey': label(pick(item, 'jockey', 'driver')),
        'entraineur': label(item.get('entraineur')),
        'poids': as_float(pick(item, 'handicapPoids', 'poidsConditionMonte')),
        'gains': as_float(pick(item, 'gainsParticipant', 'gainsCarriere')),
        'non_partant': str(item.get('nonPartant', False)).lower() in ('true', '1'),
    }


def form_score(music):
    # Indicateur simplifie : resultats 1 a 9, non probabiliste.
    digits = [int(x) for x in re.findall(r'[1-9]', music)[:5]]
    return sum(10 - x for x in digits) / len(digits) if len(digits) >= 3 else None


def engine_rank(active, number):
    """Classement distinct, uniquement si les champs utiles existent.
    M2 et M3 ne sont pas evalues sans donnees d'aptitude/origines fiables.
    """
    if number in (2, 3):
        return [], 'Données spécialisées insuffisantes'
    scored = []
    for h in active:
        form = form_score(h['musique'])
        if form is None:
            continue
        if number == 1:
            score = form
        elif number == 4:
            # M4 : forme et gains de carriere (proxy imparfait de classe).
            if h['gains'] is None or h['gains'] < 0:
                continue
            score = form + math.log1p(h['gains']) / 12
        else:
            # M5 : penalisation de la dispersion des places recentes.
            positions = [int(x) for x in re.findall(r'[1-9]', h['musique'])[:5]]
            avg = sum(positions) / len(positions)
            variance = sum((x - avg) ** 2 for x in positions) / len(positions)
            score = form - variance / 5
        scored.append((score, h['numero']))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    if len(scored) < max(5, math.ceil(len(active) * 0.7)):
        return [], 'Couverture des donnees insuffisante'
    return [n for _, n in scored[:5]], 'Heuristique expérimentale, non validée statistiquement'


def atomic_new_json(path, payload):
    """Creation exclusive : ne remplace jamais un historique existant."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode('utf-8')
    try:
        with path.open('xb') as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        return True
    except FileExistsError:
        return False


def unique_report(payload):
    stamp = now().strftime('%Y%m%d_%H%M%S_%f')
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    path = OUT / f'turbofusion_{stamp}_{digest}.json'
    atomic_new_json(path, payload)
    return path


def analyze(day, meeting, race, freeze_minutes, allow_freeze):
    r = as_int(pick(meeting, 'numOfficiel', 'numReunion'))
    c = as_int(pick(race, 'numOrdre', 'numCourse'))
    if r is None or c is None:
        raise ValueError('numero de reunion/course absent')
    raw, source = fetch(f'programme/{day:%d%m%Y}/R{r}/C{c}/participants')
    horses = [horse(item) for item in participants_from(raw) if isinstance(item, dict)]
    active = [h for h in horses if not h['non_partant'] and h['numero'] is not None]
    if len({h['numero'] for h in active}) != len(active):
        raise ValueError('numeros de partants dupliques')
    dep = departure(pick(race, 'heureDepart', 'heureDepartCourse'))
    stamp = now()
    # Aucune modification d'un fige apres son creation; limite de 5 minutes.
    before_limit = dep is not None and stamp < dep - dt.timedelta(minutes=freeze_minutes)
    is_today = day == stamp.date()
    eligible = bool(allow_freeze and is_today and before_limit and len(active) >= 5)
    race_key = f'{day:%Y%m%d}_R{r}_C{c}'
    track = label(meeting.get('hippodrome')) or 'Inconnu'
    engines = []
    new_freezes = []
    for number in range(1, 6):
        order, reason = engine_rank(active, number)
        engine = f'M{number}'
        freeze_path = FIGES / f'{race_key}_{engine}.json'
        existing = freeze_path.exists()
        valid = len(order) >= 5
        record = {
            'moteur': engine,
            'gagnant_espere': order[0] if valid else None,
            'meilleur_place': order[1] if valid else None,
            'ordre_espere': order if valid else [],
            'pari_retenu': 'Simulation uniquement - aucun pari execute' if valid else 'Aucun',
            'qualification': reason,
            'validation': 'NON FIGÉ',
            'heure_paris': stamp.isoformat(),
        }
        if existing:
            # Afficher la trace existante sans la recalculer ni la modifier.
            try:
                old = json.loads(freeze_path.read_text(encoding='utf-8'))
                record = old['pronostic']
                record = dict(record)
                record['validation'] = 'FIGÉ HISTORIQUE (IMMUTABLE)'
            except (OSError, ValueError, KeyError, TypeError):
                record = {'moteur': engine, 'validation': 'FIGÉ EXISTANT ILLISIBLE - CONSERVÉ',
                          'fichier': str(freeze_path)}
        elif eligible and valid:
            record['validation'] = 'FIGÉ'
            freeze = {
                'schema': 2, 'date_course': day.isoformat(), 'course': f'R{r}C{c}',
                'hippodrome': track, 'depart_paris': dep.isoformat(),
                'fige_a_paris': stamp.isoformat(), 'source': source,
                'partants': horses, 'pronostic': record,
                'avertissement': 'Pronostic experimental; aucune garantie de gain.'
            }
            if atomic_new_json(freeze_path, freeze):
                new_freezes.append(str(freeze_path))
            else:
                record['validation'] = 'FIGÉ EXISTANT (NON MODIFIÉ)'
        engines.append(record)
    return {
        'reunion': f'R{r}', 'course': f'C{c}', 'hippodrome': track,
        'depart_paris': dep.isoformat() if dep else None,
        'source': source, 'nombre_partants': len(active),
        'non_partants': [h['numero'] for h in horses if h['non_partant']],
        'partants': horses, 'moteurs': engines, 'nouveaux_figes': new_freezes,
        'fige': bool(new_freezes) or any(e.get('validation', '').startswith('FIGÉ') for e in engines),
    }


def main():
    parser = argparse.ArgumentParser(description='TURBOFUSION M1-M5')
    parser.add_argument('--date', help='AAAA-MM-JJ (par defaut aujourd hui Paris)')
    parser.add_argument('--reunion', help='exemple R1')
    parser.add_argument('--diagnostic', action='store_true')
    parser.add_argument('--no-freeze', action='store_true')
    parser.add_argument('--freeze-minutes', type=int, default=5)
    args = parser.parse_args()
    if args.freeze_minutes < 1:
        parser.error('--freeze-minutes doit etre >= 1')
    day = dt.date.fromisoformat(args.date) if args.date else now().date()
    program, source = fetch(f'programme/{day:%d%m%Y}')
    meetings = meetings_from(program)
    print('Source PMU :', source, flush=True)
    print('Réunions reçues :', len(meetings), flush=True)
    countries = {}
    for m in meetings:
        if isinstance(m, dict):
            country = country_of(m) or '(absent)'
            countries[country] = countries.get(country, 0) + 1
            print('Réunion', pick(m, 'numOfficiel', 'numReunion'),
                  '| pays:', country, '| hippodrome:', label(m.get('hippodrome')),
                  '| courses:', len(m.get('courses', [])) if isinstance(m.get('courses'), list) else 'absentes')
    selected = [m for m in meetings if isinstance(m, dict) and french_meeting(m)]
    print('Pays détectés :', countries)
    print('Réunions françaises :', len(selected))
    errors, reports = [], []
    if not selected:
        errors.append('Aucune réunion française reconnue. Vérifier les champs pays/codePays de la réponse.')
    if not args.diagnostic:
        for meeting in selected:
            r = as_int(pick(meeting, 'numOfficiel', 'numReunion'))
            if r is None:
                errors.append('Réunion sans numéro officiel')
                continue
            if args.reunion and args.reunion.upper() != f'R{r}':
                continue
            races = meeting.get('courses')
            if not isinstance(races, list):
                errors.append(f'R{r}: liste courses absente ou invalide')
                continue
            for race in races:
                if not isinstance(race, dict):
                    continue
                try:
                    report = analyze(day, meeting, race, args.freeze_minutes, not args.no_freeze)
                    reports.append(report)
                    print(f"{report['reunion']}{report['course']}: {report['nombre_partants']} partants; "
                          f"{len(report['nouveaux_figes'])} nouveaux FIGÉS", flush=True)
                except Exception as exc:
                    message = f"R{r}C{pick(race, 'numOrdre', 'numCourse')}: {type(exc).__name__}: {exc}"
                    errors.append(message)
                    print('ERREUR :', message, flush=True)
    payload = {
        'logiciel': 'TURBOFUSION M1-M5', 'version': '2.0',
        'date_courses': day.isoformat(), 'cree_a_paris': now().isoformat(),
        'source_programme': source, 'reunions_recues': len(meetings),
        'reunions_francaises': len(selected), 'pays_detectes': countries,
        'courses': reports, 'erreurs': errors,
        'figes_crees': sum(len(r['nouveaux_figes']) for r in reports),
        'historique': 'Fichiers historiques jamais ecrases ni modifies.',
        'mode': 'Diagnostic' if args.diagnostic else 'Analyse expérimentale',
    }
    path = unique_report(payload)
    print('Rapport :', path)
    print('Courses analysées :', len(reports))
    print('FIGÉS créés :', payload['figes_crees'])
    print('Erreurs :', len(errors))
    # Signaler les anomalies via le statut GitHub Actions.
    if args.diagnostic:
        return 0 if meetings else 2
    return 0 if reports else 3


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'ERREUR FATALE : {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
