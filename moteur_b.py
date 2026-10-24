#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TURBOFUSION 2+5 — Moteur B : spécialités M4 et M5.

M4 : proxy de classe / stratégie fondé sur forme et gains connus.
M5 : risque de dispersion des places récentes et régularité.
Aucun accès réseau, aucun pari exécuté, aucun FIGÉ modifié.
"""
from __future__ import annotations

import json
import math
from typing import Any, Mapping, Sequence

from moteur_a import _active, _float, _number, _positions, _record


def analyser_m4(horses: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Classe relative expérimentale, PAS une simulation tactique du parcours."""
    active = _active(horses)
    scored = []
    for horse in active:
        positions = _positions(horse.get('musique'))
        gains = _float(horse.get('gains'))
        if len(positions) < 3 or gains is None or gains < 0:
            continue
        form = sum(10 - p for p in positions) / len(positions)
        score = form + math.log1p(gains) / 12.0
        scored.append((score, _number(horse)))
    return _record('M4', scored, len(active),
                   'Proxy forme/gains expérimental ; stratégie de course non modélisée',
                   'musique exploitable et gains connus')


def analyser_m5(horses: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Régularité et dispersion ; n'évalue pas les risques non observés."""
    active = _active(horses)
    scored = []
    for horse in active:
        positions = _positions(horse.get('musique'))
        if len(positions) < 3:
            continue
        mean = sum(positions) / len(positions)
        variance = sum((p - mean) ** 2 for p in positions) / len(positions)
        score = 10 - mean - variance / 5.0
        scored.append((score, _number(horse)))
    return _record('M5', scored, len(active),
                   'Heuristique de dispersion expérimentale, non validée',
                   'musique récente exploitable (au moins 3 places)')


def analyser(horses: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Retourne exactement M4 puis M5."""
    return [analyser_m4(horses), analyser_m5(horses)]


if __name__ == '__main__':
    import argparse
    import sys
    parser = argparse.ArgumentParser(description='TURBOFUSION — Moteur B')
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
        print(f'ERREUR moteur B : {exc}', file=sys.stderr)
        sys.exit(1)
