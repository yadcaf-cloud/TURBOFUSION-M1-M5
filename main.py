#!/usr/bin/env python3
"""TURBOFUSION 3.0 — M1 à M5, analyses traçables et FIGÉS immuables."""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
PARIS = ZoneInfo("Europe/Paris")
SPECIALITES = {
    "M1": ("Forme et régularité", ("forme", "regularite")),
    "M2": ("Aptitudes et conditions", ("aptitude", "conditions")),
    "M3": ("Origines et entourage", ("origines", "entourage")),
    "M4": ("Classe et stratégie", ("classe", "strategie")),
    "M5": ("Risques et fiabilité", ("fiabilite", "regularite")),
}


def lire(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def ecrire(path, objet):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporaire = path.with_name(path.name + ".tmp")
    try:
        with temporaire.open("w", encoding="utf-8") as f:
            json.dump(objet, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
        os.replace(temporaire, path)
    finally:
        temporaire.unlink(missing_ok=True)


def date_depart(valeur):
    instant = dt.datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Date de départ sans fuseau horaire")
    return instant.astimezone(PARIS)


def notes_musique(cheval):
    """Heuristique limitée aux places lisibles; aucune validation statistique."""
    musique = cheval.get("musique")
    if not isinstance(musique, str):
        return {}
    # Supprimer les années, qui ne sont pas des résultats.
    musique = re.sub(r"\([^)]*\)", "", musique.lower())
    sequence = re.findall(r"([1-9])([apmh])", musique)[:6]
    if len(sequence) < 3:
        return {}
    places = [int(place) for place, _ in sequence]
    valeurs = [(10 - p) / 9 for p in places]
    return {
        "forme": round(sum(valeurs[:3]) / 3, 4),
        "regularite": round(sum(valeurs) / len(valeurs), 4),
        "fiabilite": round(sum(p <= 5 for p in places) / len(places), 4),
    }


def note(cheval, critere):
    valeur = cheval.get(critere)
    if valeur is None and critere in ("forme", "regularite", "fiabilite"):
        valeur = notes_musique(cheval).get(critere)
    if type(valeur) not in (int, float) or not math.isfinite(valeur):
        return None
    return float(valeur) if 0 <= valeur <= 1 else None


def analyser_moteur(nom, chevaux, avant_depart):
    specialite, criteres = SPECIALITES[nom]
    lignes = []
    for cheval in chevaux:
        if cheval.get("non_partant") is True:
            continue
        numero, nom_cheval = cheval.get("numero"), cheval.get("nom")
        if type(numero) is not int or numero <= 0 or not isinstance(nom_cheval, str) or not nom_cheval.strip():
            continue
        valeurs = [note(cheval, c) for c in criteres]
        complet = all(v is not None for v in valeurs)
        lignes.append({
            "numero": numero,
            "nom": nom_cheval.strip(),
            "score": round(sum(valeurs) / len(valeurs), 4) if complet else None,
            "couverture": round(sum(v is not None for v in valeurs) / len(valeurs), 2),
        })

    couverture_complete = len(lignes) >= 2 and all(ligne["score"] is not None for ligne in lignes)
    if couverture_complete:
        lignes.sort(key=lambda ligne: (-ligne["score"], ligne["numero"]))
    discriminant = couverture_complete and lignes[0]["score"] > lignes[1]["score"]
    admissible = bool(discriminant and avant_depart)
    ordre = [ligne["numero"] for ligne in lignes[:5]] if admissible else []
    motif = (
        "Classement heuristique calculé sur les critères du moteur" if admissible
        else "Départ trop proche ou passé" if not avant_depart
        else "Données incomplètes ou scores de tête non discriminants"
    )
    return {
        "moteur": nom,
        "specialite": specialite,
        "criteres": list(criteres),
        "qualification": "candidate" if admissible else "abstention",
        "motif": motif,
        "classement": lignes[:5] if couverture_complete else [],
        "ordre_arrivee_espere": ordre,
        "gagnant_espere": ordre[0] if ordre else None,
        "place_espere": ordre[1] if len(ordre) > 1 else None,
        "pari": f"Simple Gagnant {ordre[0]}" if ordre else "Aucun pari proposé",
    }


def identifiant_course(course):
    identifiant = str(course.get("id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifiant):
        raise ValueError(f"Identifiant de course invalide : {identifiant!r}")
    return identifiant


def charger_fige(chemin):
    """Relire le FIGÉ original plutôt que recalculer son pronostic."""
    return lire(chemin)


def traiter(figer=False, marge_minutes=5):
    source = DATA / "courses.json"
    if not source.is_file():
        raise FileNotFoundError("data/courses.json absent : lancer collecte_pmu.py")
    entree = lire(source)
    if not isinstance(entree, dict) or not isinstance(entree.get("courses"), list):
        raise ValueError("Format attendu : objet JSON contenant une liste 'courses'")
    maintenant = dt.datetime.now(PARIS)
    sorties, erreurs = [], []
    nouveaux_figes = 0
    ids_vus = set()

    for index, course in enumerate(entree["courses"], 1):
        try:
            if not isinstance(course, dict):
                raise ValueError("Course non représentée par un objet")
            identifiant = identifiant_course(course)
            if identifiant in ids_vus:
                raise ValueError("Identifiant de course dupliqué")
            ids_vus.add(identifiant)
            depart = date_depart(course["depart"])
            chevaux = course.get("partants")
            if not isinstance(chevaux, list) or not chevaux or not all(isinstance(c, dict) for c in chevaux):
                raise ValueError("Liste des partants absente ou invalide")
            numeros = [c.get("numero") for c in chevaux]
            numeros_valides = all(type(n) is int and n > 0 for n in numeros)
            if not numeros_valides or len(set(numeros)) != len(numeros):
                raise ValueError("Numéros de chevaux invalides ou dupliqués")
            if not all(isinstance(c.get("nom"), str) and c["nom"].strip() for c in chevaux):
                raise ValueError("Nom de cheval absent")
            if not all(type(c.get("non_partant", False)) is bool for c in chevaux):
                raise ValueError("Indicateur non_partant invalide")

            collecte_ok = course.get("collecte_participants") == "ok"
            avant_depart = maintenant < depart - dt.timedelta(minutes=marge_minutes)
            moteurs = {
                nom: analyser_moteur(nom, chevaux, avant_depart and collecte_ok)
                for nom in SPECIALITES
            }
            eligibles = [nom for nom, m in moteurs.items() if m["qualification"] == "candidate"]
            chemin_fige = DATA / "figes" / f"{identifiant}.json"
            statut = "analyse_provisoire"
            figes_officiels = {}
            instantane = None

            if chemin_fige.exists():
                instantane = charger_fige(chemin_fige)
                statut = "fige_existant"
            elif figer and eligibles and collecte_ok and avant_depart:
                instantane = {
                    "course_id": identifiant,
                    "depart": course["depart"],
                    "fige_a": maintenant.isoformat(),
                    "moteurs": moteurs,
                    "source": course.get("source"),
                }
                chemin_fige.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with chemin_fige.open("x", encoding="utf-8") as f:
                        json.dump(instantane, f, ensure_ascii=False, indent=2, allow_nan=False)
                        f.write("\n")
                    statut = "fige"
                    nouveaux_figes += 1
                except FileExistsError:
                    instantane = charger_fige(chemin_fige)
                    statut = "fige_existant"

            if instantane is not None:
                figes_officiels = {
                    nom: m for nom, m in instantane.get("moteurs", {}).items()
                    if isinstance(m, dict) and m.get("qualification") == "candidate"
                }

            ligne = {
                "id": identifiant,
                "hippodrome": course.get("hippodrome"),
                "reunion": course.get("reunion"),
                "course": course.get("course"),
                "depart": course["depart"],
                "partants": sum(not c.get("non_partant", False) for c in chevaux),
                "non_partants": sum(c.get("non_partant", False) for c in chevaux),
                "moteurs": moteurs,
                "moteurs_qualifies": eligibles,
                "moteurs_figes": figes_officiels,
                "statut": statut,
                "analyse_a": maintenant.isoformat(),
                "source": course.get("source"),
            }
            if instantane is not None:
                ligne["fige_a"] = instantane.get("fige_a")
                ligne["fichier_fige"] = chemin_fige.relative_to(ROOT).as_posix()
                ligne["sha256"] = hashlib.sha256(chemin_fige.read_bytes()).hexdigest()
            sorties.append(ligne)
        except (KeyError, ValueError, TypeError, json.JSONDecodeError, OSError) as exc:
            erreurs.append({"index": index, "id": str(course.get("id", "")) if isinstance(course, dict) else None,
                            "erreur": str(exc)})

    sorties.sort(key=lambda c: date_depart(c["depart"]))
    resultat = {
        "logiciel": "TURBOFUSION 3.0",
        "date": maintenant.date().isoformat(),
        "genere_a": maintenant.isoformat(),
        "statut_collecte": entree.get("statut_collecte", "inconnu"),
        "moteurs": list(SPECIALITES),
        "courses": sorties,
        "erreurs": erreurs,
        "avertissements": [
            "Scores heuristiques non validés statistiquement.",
            "Pronostics FIGÉS conservés séparément des analyses actualisées.",
            "Aucun pari réel exécuté automatiquement; aucun gain garanti.",
        ],
    }
    ecrire(DATA / "audit_latest.json", resultat)
    ecrire(DATA / "publication_latest.json", resultat)
    print(f"{len(sorties)} courses analysées ; {nouveaux_figes} nouveaux FIGÉS ; {len(erreurs)} erreurs")
    return resultat


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyse hippique TURBOFUSION M1–M5")
    parser.add_argument("--figer", action="store_true", help="Créer les FIGÉS admissibles avant départ")
    parser.add_argument("--safety-minutes", type=int, default=5, help="Marge minimale avant départ")
    args = parser.parse_args()
    if args.safety_minutes < 0:
        parser.error("La marge de sécurité ne peut pas être négative")
    traiter(figer=args.figer, marge_minutes=args.safety_minutes)
