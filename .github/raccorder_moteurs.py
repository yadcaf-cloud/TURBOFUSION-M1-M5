#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🇸🇳🧠🔥 TURBOFUSION 2+5
Raccordement des deux moteurs principaux à main.py.

Moteur A : M1, M2, M3
Moteur B : M4, M5

- Sauvegarde main.py avant modification.
- Préserve les cinq spécialités.
- Conserve la logique des FIGÉS historiques.
- Ne modifie aucun fichier dans figes_turbofusion/.
- Vérifie la syntaxe Python après raccordement.

Exécution :
    python raccorder_moteurs.py
"""

from pathlib import Path
import ast
import py_compile
import sys

ROOT = Path(__file__).resolve().parent

MAIN = ROOT / "main.py"
BACKUP = ROOT / "main.py.avant_2plus5.py"


def patch(content):
    """
    Prépare le nouveau main.py sans modifier
    directement les fichiers du dépôt.
    """

    # Empêcher un double raccordement.
    if (
        "from moteur_a import analyser as analyser_moteur_a"
        in content
    ):
        return content, False

    tree = ast.parse(content)

    functions = {
        node.name: node
        for node in tree.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        )
    }

    if (
        "analyze" not in functions
        or "engine_rank" not in functions
    ):
        raise RuntimeError(
            "main.py incompatible : fonctions "
            "analyze / engine_rank introuvables"
        )

    # 1. Adapter la fonction historique engine_rank.
    lines = content.splitlines(keepends=True)
    rank = functions["engine_rank"]

    replacement = '''def engine_rank(active, number):
    """Compatibilité avec les cinq spécialités."""
    outputs = (
        analyser_moteur_a(active)
        + analyser_moteur_b(active)
    )

    if not isinstance(number, int) or number not in range(1, 6):
        raise ValueError("Moteur inconnu")

    record = outputs[number - 1]

    return (
        record["ordre_espere"],
        record["qualification"]
    )

'''

    lines[rank.lineno - 1:rank.end_lineno] = [
        replacement
    ]

    content = "".join(lines)

    # 2. Importer les deux moteurs principaux.
    anchor = "from zoneinfo import ZoneInfo\n"

    if content.count(anchor) != 1:
        raise RuntimeError(
            "Import zoneinfo introuvable ou ambigu"
        )

    imports = (
        "\n"
        "from moteur_a import analyser as analyser_moteur_a\n"
        "from moteur_b import analyser as analyser_moteur_b\n"
    )

    content = content.replace(
        anchor,
        anchor + imports,
        1
    )

    # 3. Calculer les cinq spécialités en deux appels.
    old = '''    for number in range(1, 6):
        order, reason = engine_rank(active, number)
        engine = f'M{number}'
'''

    new = '''    evaluations = (
        analyser_moteur_a(active)
        + analyser_moteur_b(active)
    )

    expected = ['M1', 'M2', 'M3', 'M4', 'M5']

    if [
        e.get('moteur') for e in evaluations
    ] != expected:
        raise ValueError(
            'Les cinq spécialités M1-M5 '
            'ne sont pas disponibles '
            'dans l’ordre attendu'
        )

    for evaluation in evaluations:
        engine = evaluation['moteur']
        order = evaluation.get('ordre_espere') or []
        reason = (
            evaluation.get('qualification')
            or 'Non évalué'
        )
'''

    if content.count(old) != 1:
        raise RuntimeError(
            "Boucle des moteurs non reconnue ; "
            "aucun changement effectué"
        )

    content = content.replace(old, new, 1)

    # 4. Préserver le format du tableau officiel.
    old_record = '''        record = {
            'moteur': engine,
            'gagnant_espere': order[0] if valid else None,
            'meilleur_place': order[1] if valid else None,
            'ordre_espere': order if valid else [],
            'pari_retenu': 'Simulation uniquement - aucun pari execute' if valid else 'Aucun',
            'qualification': reason,
            'validation': 'NON FIGÉ',
            'heure_paris': stamp.isoformat(),
        }
'''

    new_record = '''        record = dict(evaluation)

        record.update({
            'gagnant_espere': (
                order[0] if valid else None
            ),
            'meilleur_place': (
                order[1] if valid else None
            ),
            'ordre_espere': (
                order if valid else []
            ),
            'qualification': reason,
            'validation': 'NON FIGÉ',
            'heure_paris': stamp.isoformat(),
            'moteur_principal': (
                'A'
                if engine in ('M1', 'M2', 'M3')
                else 'B'
            ),
        })
'''

    if content.count(old_record) != 1:
        raise RuntimeError(
            "Format des pronostics non reconnu ; "
            "aucun changement effectué"
        )

    content = content.replace(
        old_record,
        new_record,
        1
    )

    # Vérifier la syntaxe avant écriture.
    ast.parse(content)

    return content, True


def main():
    """
    Effectue le raccordement après vérification
    des fichiers indispensables.
    """

    required = (
        "main.py",
        "moteur_a.py",
        "moteur_b.py"
    )

    for name in required:
        if not (ROOT / name).is_file():
            raise RuntimeError(
                f"Fichier manquant : {name}"
            )

    original = MAIN.read_text(
        encoding="utf-8"
    )

    changed, did_change = patch(original)

    if not did_change:
        print(
            "Déjà raccordé : aucune modification."
        )
        return

    if BACKUP.exists():
        raise RuntimeError(
            f"Sauvegarde existante : {BACKUP}. "
            "Aucune modification."
        )

    # Sauvegarder le fichier original.
    BACKUP.write_text(
        original,
        encoding="utf-8"
    )

    # Écrire le nouveau main.py.
    MAIN.write_text(
        changed,
        encoding="utf-8"
    )

    # Vérifier la syntaxe des trois modules.
    for name in required:
        py_compile.compile(
            str(ROOT / name),
            doraise=True
        )

    print("=" * 50)
    print("🇸🇳 TURBOFUSION 2+5")
    print("Raccordement terminé.")
    print("=" * 50)
    print("Moteur A : M1, M2, M3")
    print("Moteur B : M4, M5")
    print("Sauvegarde :", BACKUP.name)
    print("FIGÉS historiques non modifiés.")
    print("Tableau officiel M1–M5 conservé.")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            f"ERREUR : {type(exc).__name__}: {exc}",
            file=sys.stderr
        )
        sys.exit(1)
