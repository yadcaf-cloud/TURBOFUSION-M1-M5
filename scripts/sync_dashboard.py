#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🇸🇳🧠🔥 TURBOFUSION M1-M5
Intelligence hippique spécialisée — La magie du savoir

Synchronisation sécurisée du tableau officiel.

- Sélection du dernier rapport valide
- Préservation des FIGÉS historiques
- Conservation des audits existants
- Contrôle des cinq moteurs
- Écriture atomique de dashboard.json
- Aucun pronostic fabriqué
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]

REPORTS = ROOT / "rapports_turbofusion"
FIGES = ROOT / "figes_turbofusion"
DASHBOARD = ROOT / "dashboard.json"

PARIS = ZoneInfo("Europe/Paris")

MOTEURS = ("M1", "M2", "M3", "M4", "M5")


def journal(message):
    heure = datetime.now(PARIS).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    print(f"[{heure} Paris] {message}", flush=True)


def charger_json(path):
    with path.open("r", encoding="utf-8") as fichier:
        return json.load(fichier)


def date_rapport(data):
    valeur = data.get("cree_a_paris")

    if not isinstance(valeur, str):
        return None

    try:
        instant = datetime.fromisoformat(
            valeur.replace("Z", "+00:00")
        )

        if instant.tzinfo is None:
            return None

        return instant
    except ValueError:
        return None


def trouver_dernier_rapport():
    if not REPORTS.exists():
        raise RuntimeError(
            "Dossier rapports_turbofusion absent"
        )

    candidats = []

    for path in REPORTS.glob("turbofusion_*.json"):
        try:
            data = charger_json(path)

            if not isinstance(data, dict):
                continue

            if not isinstance(data.get("courses"), list):
                continue

            instant = date_rapport(data)

            if instant is None:
                journal(
                    f"Rapport sans horodatage valide : {path.name}"
                )
                continue

            candidats.append((instant.timestamp(), path, data))

        except (OSError, ValueError, TypeError) as exc:
            journal(
                f"Rapport ignoré : {path.name} : {exc}"
            )

    if not candidats:
        raise RuntimeError(
            "Aucun rapport valide disponible"
        )

    candidats.sort(key=lambda x: (x[0], x[1].name))

    _, path, data = candidats[-1]

    journal(f"Rapport sélectionné : {path.name}")

    return path, data


def charger_dashboard_existant():
    if not DASHBOARD.exists():
        return {}

    data = charger_json(DASHBOARD)

    if not isinstance(data, dict):
        raise RuntimeError(
            "Dashboard existant invalide : objet attendu"
        )

    return data


def charger_figes():
    archives = []
    erreurs = []

    if not FIGES.exists():
        journal("Dossier FIGÉS absent")
        return archives, erreurs

    for path in sorted(FIGES.glob("*.json")):
        try:
            data = charger_json(path)

            if not isinstance(data, dict):
                raise ValueError("Objet JSON attendu")

            pronostic = data.get("pronostic")

            if not isinstance(pronostic, dict):
                raise ValueError("Pronostic absent")

            moteur = pronostic.get("moteur")

            if moteur not in MOTEURS:
                raise ValueError("Moteur inconnu")

            ordre = pronostic.get("ordre_espere", [])

            if not isinstance(ordre, list):
                raise ValueError("Ordre invalide")

            if not data.get("fige_a_paris"):
                raise ValueError("Horodatage FIGÉ absent")

            archives.append({
                "course": data.get("course"),
                "date_course": data.get("date_course"),
                "hippodrome": data.get("hippodrome"),
                "depart_paris": data.get("depart_paris"),
                "fige_a_paris": data.get("fige_a_paris"),
                "moteur": moteur,
                "gagnant_espere": pronostic.get(
                    "gagnant_espere"
                ),
                "meilleur_place": pronostic.get(
                    "meilleur_place"
                ),
                "ordre_espere": ordre,
                "pari_retenu": pronostic.get(
                    "pari_retenu"
                ),
                "qualification": pronostic.get(
                    "qualification"
                ),
                "validation": "FIGÉ",
                "fichier": str(path.relative_to(ROOT))
            })

        except (OSError, ValueError, TypeError) as exc:
            message = (
                f"FIGÉ illisible conservé : "
                f"{path.name} : {exc}"
            )
            journal(message)
            erreurs.append(message)

    return archives, erreurs


def verifier_courses(courses):
    erreurs = []

    for course in courses:
        if not isinstance(course, dict):
            erreurs.append("Course invalide")
            continue

        moteurs = course.get("moteurs", [])

        if not isinstance(moteurs, list):
            erreurs.append(
                f"Moteurs invalides : {course.get('course')}"
            )
            continue

        presents = {
            m.get("moteur")
            for m in moteurs
            if isinstance(m, dict)
        }

        manquants = set(MOTEURS) - presents

        if manquants:
            erreurs.append(
                f"{course.get('reunion')} "
                f"{course.get('course')} : "
                f"moteurs manquants : "
                f"{', '.join(sorted(manquants))}"
            )

    return erreurs


def ecriture_atomique(destination, donnees):
    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temporaire = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=".dashboard_",
            suffix=".tmp",
            delete=False
        ) as fichier:

            temporaire = Path(fichier.name)

            json.dump(
                donnees,
                fichier,
                ensure_ascii=False,
                indent=2
            )

            fichier.flush()
            os.fsync(fichier.fileno())

        os.replace(temporaire, destination)

    finally:
        if temporaire is not None:
            temporaire.unlink(missing_ok=True)


def main():
    journal("🇸🇳🧠🔥 TURBOFUSION M1-M5")
    journal("Synchronisation officielle démarrée")

    rapport_path, rapport = trouver_dernier_rapport()

    ancien = charger_dashboard_existant()

    audits = ancien.get("audits", [])

    if not isinstance(audits, list):
        raise RuntimeError(
            "Audits existants invalides : publication annulée"
        )

    archives, erreurs_figes = charger_figes()

    courses = rapport["courses"]

    erreurs_moteurs = verifier_courses(courses)

    erreurs = list(rapport.get("erreurs", []))

    erreurs.extend(erreurs_figes)
    erreurs.extend(erreurs_moteurs)

    payload = {
        "logiciel": "TURBOFUSION M1-M5",
        "version_dashboard": "2.1",
        "date_courses": rapport.get("date_courses"),
        "cree_a_paris": rapport.get("cree_a_paris"),
        "synchronise_a_paris": datetime.now(
            PARIS
        ).isoformat(),
        "courses": courses,
        "figes": archives,
        "audits": audits,
        "erreurs": erreurs,
        "source_rapport": str(
            rapport_path.relative_to(ROOT)
        ),
        "nombre_courses": len(courses),
        "nombre_figes": len(archives),
        "nombre_audits": len(audits),
        "note": (
            "Analyses expérimentales. "
            "Aucun pari réel exécuté. "
            "FIGÉS historiques non modifiés."
        )
    }

    ecriture_atomique(DASHBOARD, payload)

    journal("TABLEAU DE BORD SYNCHRONISÉ")
    journal(f"Courses : {len(courses)}")
    journal(f"FIGÉS : {len(archives)}")
    journal(f"Audits conservés : {len(audits)}")
    journal(f"Anomalies : {len(erreurs)}")
    journal("Archives FIGÉES non modifiées")
    journal("Synchronisation terminée")


if __name__ == "__main__":
    try:
        main()
    except Exception as erreur:
        journal(
            f"ERREUR DE SYNCHRONISATION : {erreur}"
        )
        raise SystemExit(1)
