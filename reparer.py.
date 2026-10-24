#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🇸🇳🧠🔥 TURBOFUSION M1–M5
RÉPARATION CONSOLIDÉE — VERSION 1

Protection des données et FIGÉS historiques.
Correction de l'interface sans modifier les pronostics.
"""

from pathlib import Path
from datetime import datetime, timezone
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
DASHBOARD = ROOT / "dashboard.json"
BACKUPS = ROOT / "sauvegardes_reparation"

def journal(message):
    print(f"[TURBOFUSION] {message}")

def verifier_dashboard():
    if not DASHBOARD.exists():
        journal("ATTENTION : dashboard.json absent.")
        return False

    try:
        with DASHBOARD.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("Objet JSON attendu")

        journal(
            f"Dashboard valide : "
            f"{len(data.get('courses', []))} courses."
        )
        return True

    except (OSError, ValueError) as exc:
        journal(f"ERREUR dashboard : {exc}")
        return False

def sauvegarder_index():
    BACKUPS.mkdir(exist_ok=True)

    date = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    destination = BACKUPS / f"index_{date}.html"
    shutil.copy2(INDEX, destination)

    journal(f"Sauvegarde : {destination.name}")

def reparer_interface():
    if not INDEX.exists():
        journal("ERREUR : index.html introuvable.")
        return False

    original = INDEX.read_text(encoding="utf-8")
    contenu = original

    corrections = [
        (
            "e(val(c,'heure','heure_depart','depart'))",
            "e(val(c,'heure','heure_depart','depart_paris','depart'))"
        ),
        (
            "e(val(c,'partants','nombre_partants','nb_partants'))",
            "e(val(c,'nombre_partants','nb_partants'))"
        )
    ]

    for ancien, nouveau in corrections:
        if ancien in contenu:
            contenu = contenu.replace(ancien, nouveau)
            journal("Correction appliquée.")
        elif nouveau in contenu:
            journal("Correction déjà présente.")
        else:
            journal("Structure différente : correction ignorée.")

    if contenu == original:
        journal("Aucune modification nécessaire.")
        return True

    sauvegarder_index()

    temporaire = ROOT / "index.html.tmp"
    temporaire.write_text(contenu, encoding="utf-8")
    temporaire.replace(INDEX)

    journal("Interface réparée.")
    return True

def main():
    journal("Démarrage de la réparation sécurisée.")

    if not verifier_dashboard():
        journal("Arrêt : données absentes ou invalides.")
        return 1

    if not reparer_interface():
        return 1

    journal("Réparation terminée.")
    journal("dashboard.json NON MODIFIÉ.")
    journal("FIGÉS historiques NON MODIFIÉS.")
    journal("Audits historiques NON MODIFIÉS.")
    journal("Vérifiez index.html avant publication.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
