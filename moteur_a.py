#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TURBOFUSION 2+5 — Moteur A : spécialités M1, M2, M3.

Analyse expérimentale, sans garantie prédictive. Aucun accès réseau,
aucune écriture de FIGÉ et aucune fabrication de données manquantes.
Entrée : liste de chevaux normalisés (voir main.py).
Sortie : trois enregistrements compatibles avec le tableau officiel.
"""
from __future__ import annotations

import math
import re
from typing import Any, Mapping, Sequence

MIN_COVERAGE = 0.70
MIN_HORSES = 5


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(str(value).replace(',', '.'))
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def _number(horse: Mapping[str, Any]) -> int | None:
    try:
        value = horse.get('numero')
        if isinstance(value, bool) or value is None:
            return None
        number = int(value)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def _positions(music: Any) -> list[int]:
    """Proxy prudent pour musiques PMU : n'interprète pas les 0, lettres et incidents."""
    if not isinstance(music, str):
        return []
    return [int(digit) for digit in re.findall(r'[1-9]', music)[:5]]


def _active(horses: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    result = []
    seen = set()
    for horse in horses:
        if not isinstance(horse, Mapping):
            continue
        n = _number(horse)
        if n is None or horse.get('non_partant') is True or n in seen:
            continue
        seen.add(n)
        result.append(horse)
    return result


def _record(name: str, scores: list[tuple[float, int]], total: int,
            qualification: str, required_fields: str) -> dict[str, Any]:
    scores.sort(key=lambda x: (-x[0], x[1]))
    coverage = len(scores) / total if total else 0.0
    valid = total >= MIN_HORSES and len(scores) >= MIN_HORSES and coverage >= MIN_COVERAGE
    order = [n for _, n in scores[:5]] if valid else []
    reason = qualification if valid else (
        f'Données insuffisantes ({len(scores)}/{total} chevaux évaluables). '
        f'Champs requis : {required_fields}'
    )
    return {
        'moteur': name,
        'gagnant_espere': order[0] if order else None,
        'meilleur_place': order[1] if len(order) > 1 else None,
        'ordre_espere': order,
        'pari_retenu': 'Aucun pari déterminé — simulation uniquement',
        'qualification': reason,
        'validation': 'NON FIGÉ',
        'heure_paris': None,
        'couverture': round(coverage, 3),
        'specialite_disponible': valid,
    }


def analyser_m1(horses: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Forme récente et régularité, proxy à partir de la musique."""
    active = _active(horses)
    scored = []
    for horse in active:
        positions = _positions(horse.get('musique'))
        if len(positions) < 3:
            continue
        avg = sum(positions) / len(positions)
        variance = sum((p - avg) ** 2 for p in positions) / len(positions)
        score = 10.0 - avg - 0.15 * variance
        scored.append((score, _number(horse)))
    return _record('M1', scored, len(active),
                   'Heuristique forme/régularité expérimentale, non validée',
                   'musique récente exploitable (au moins 3 places)')


def analyser_m2(horses: Sequence[Mapping[str, Any]],
                conditions: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Aptitude distance/surface/terrain : uniquement si mesures comparables fournies.

    Le champ optionnel aptitude_conditions_score doit être un score numérique
    provenant d'une analyse externe vérifiée pour la course et ses conditions.
    Sans ce champ, M2 est indisponible. Aucun score n'est inféré du nom ou du poids.
    """
    active = _active(horses)
    scored = []
    for horse in active:
        score = _float(horse.get('aptitude_conditions_score'))
        if score is not None and horse.get('aptitude_source'):
            scored.append((score, _number(horse)))
    return _record('M2', scored, len(active),
                   'Scores d’aptitude fournis par une source identifiée ; méthode à auditer',
                   'aptitude_conditions_score et aptitude_source')


def analyser_m3(horses: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Origines/entourage/équipement : données évaluées par source externe vérifiée.

    Le score n'est jamais fabriqué à partir de la présence d'un jockey ou
    entraîneur : il faut une mesure documentée pour chaque cheval.
    """
    active = _active(horses)
    scored = []
    for horse in active:
        score = _float(horse.get('entourage_origines_score'))
        if score is not None and horse.get('entourage_origines_source'):
            scored.append((score, _number(horse)))
    return _record('M3', scored, len(active),
                   'Scores entourage/origines fournis par une source identifiée ; méthode à auditer',
                   'entourage_origines_score et entourage_origines_source')


def analyser(horses: Sequence[Mapping[str, Any]],
             conditions: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Retourne exactement les sorties M1, M2, M3 dans cet ordre."""
    return [analyser_m1(horses), analyser_m2(horses, conditions), analyser_m3(horses)]


if __name__ == '__main__':
    import argparse
    import json
    import sys
    parser = argparse.ArgumentParser(description='TURBOFUSION — Moteur A')
    parser.add_argument('fichier', help='JSON avec partants (liste ou objet)')
    args = parser.parse_args()
    try:
        with open(args.fichier, encoding='utf-8') as stream:
            data = json.load(stream)
        horses = data.get('partants', []) if isinstance(data, dict) else data
        if not isinstance(horses, list):
            raise ValueError('partants doit être une liste')
        print(json.dumps(analyser(horses), ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError) as exc:
        print(f'ERREUR moteur A : {exc}', file=sys.stderr)
        sys.exit(1)
