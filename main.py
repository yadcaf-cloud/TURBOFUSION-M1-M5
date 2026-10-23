#!/usr/bin/env python3
# TURBOFUSION M1-M5 - V1.2
# Analyse expérimentale, sans pari réel.
# Préservation des rapports et FIGÉS historiques.

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Paris")
OUT = Path("rapports_turbofusion")
BASES = [
    "https://offline.turfinfo.api.pmu.fr/rest/client/7/",
    "https://online.turfinfo.api.pmu.fr/rest/client/1/",
]


def now():
    return dt.datetime.now(TZ)


def fetch(path):
    errors = []
    for base in BASES:
        url = base + path.lstrip("/")
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 TURBOFUSION/1.2"
            }
        )
        try:
            with urllib.request.urlopen(
                req, timeout=20
            ) as response:
                data = json.load(response)
                return data, url
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError(" | ".join(errors))


def meetings_from(data):
    if not isinstance(data, dict):
        raise ValueError("Programme PMU non conforme")

    programme = data.get("programme", data)
    if isinstance(programme, dict):
        meetings = programme.get("reunions", [])
    else:
        meetings = []

    if not isinstance(meetings, list):
        raise ValueError("Liste des réunions invalide")
    return meetings


def country_of(meeting):
    value = meeting.get("pays")
    if isinstance(value, dict):
        value = (
            value.get("code")
            or value.get("codePays")
            or value.get("libelle")
        )
    if not value:
        value = meeting.get("codePays")
    return str(value or "").strip().upper()


def french_meeting(meeting):
    country = country_of(meeting)
    return country in {
        "FR", "FRA", "FRANCE", "FRANÇAIS",
        "FRANCAIS"
    }


def get_number(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def horse(raw):
    return {
        "numero": get_number(
            raw.get("numPmu", raw.get("numero"))
        ),
        "nom": raw.get("nom", "Inconnu"),
        "musique": raw.get("musique", ""),
        "age": raw.get("age"),
        "jockey": raw.get("jockey") or raw.get("driver"),
        "entraineur": raw.get("entraineur"),
        "non_partant": bool(raw.get("nonPartant", False))
    }


def form_score(musique):
    # Heuristique limitée : ne remplace pas
    # une véritable analyse des performances.
    digits = [
        int(x) for x in
        re.findall(r"[1-9]", str(musique)[:18])
    ][:5]
    if not digits:
        return None
    return round(
        sum(11 - x for x in digits) / len(digits), 2
    )


def departure(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            # Heure PMU souvent exprimée en ms.
            seconds = value / 1000 if value > 1e11 else value
            return dt.datetime.fromtimestamp(
                seconds, TZ
            )
        parsed = dt.datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(TZ)
    except (ValueError, OverflowError, OSError):
        return None


def analyse(day, reunion, course, meeting, race):
    path = (
        f"programme/{day:%d%m%Y}/"
        f"R{reunion}/C{course}/participants"
    )
    data, source = fetch(path)

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("participants", [])
    else:
        raise ValueError("Participants non conformes")

    if not isinstance(items, list):
        raise ValueError("Participants invalides")

    horses = [
        horse(x) for x in items
        if isinstance(x, dict)
    ]
    active = [
        h for h in horses
        if not h["non_partant"]
        and h["numero"] is not None
    ]
    known = [
        h for h in active
        if form_score(h["musique"]) is not None
    ]

    track = meeting.get("hippodrome", {})
    if isinstance(track, dict):
        track = (
            track.get("libelleCourt")
            or track.get("libelleLong")
            or "Inconnu"
        )

    dep = departure(race.get("heureDepart"))
    timestamp = now()
    before_start = (
        dep is not None
        and timestamp < dep - dt.timedelta(minutes=5)
    )

    # Le score de forme n'autorise qu'une
    # pré-analyse M1. M2-M5 restent non évalués
    # faute de données spécifiques vérifiées.
    ranking = sorted(
        known,
        key=lambda h: (
            -form_score(h["musique"]),
            h["numero"]
        )
    )
    enough = (
        len(active) >= 5
        and len(known) >= max(
            3, int(len(active) * 0.7)
        )
    )

    engines = []
    for number in range(1, 6):
        usable = number == 1 and enough
        order = (
            [h["numero"] for h in ranking[:5]]
            if usable else []
        )
        engines.append({
            "moteur": f"M{number}",
            "gagnant_espere": order[0] if order else None,
            "meilleur_place": (
                order[1] if len(order) > 1 else None
            ),
            "ordre_espere": order,
            "pari_retenu": (
                "Simulation de forme uniquement"
                if usable else "Aucun"
            ),
            "qualification": (
                "Pré-analyse partielle"
                if usable else "Non évalué"
            ),
            "validation": "NON FIGÉ",
            "heure_paris": timestamp.isoformat()
        })

    return {
        "reunion": f"R{reunion}",
        "course": f"C{course}",
        "hippodrome": str(track),
        "depart": race.get("heureDepart"),
        "source": source,
        "analyse_avant_depart": before_start,
        "partants": horses,
        "moteurs": engines,
        "fige": False,
        "limites": [
            "M1 : heuristique de forme uniquement.",
            "M2-M5 : données spécialisées insuffisantes.",
            "Aucun FIGÉ automatique autorisé.",
            "Aucun pari réel exécuté."
        ]
    }


def save_report(payload):
    OUT.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(
        payload, ensure_ascii=False, indent=2
    )
    digest = hashlib.sha256(
        blob.encode("utf-8")
    ).hexdigest()[:12]

    stamp = now().strftime("%Y%m%d_%H%M%S_%f")
    path = OUT / f"turbofusion_{stamp}_{digest}.json"

    # Mode exclusif : aucun rapport écrasé.
    with path.open("x", encoding="utf-8") as file:
        file.write(blob)

    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--reunion")
    parser.add_argument(
        "--diagnostic", action="store_true"
    )
    args = parser.parse_args()

    day = (
        dt.date.fromisoformat(args.date)
        if args.date else now().date()
    )

    program, source = fetch(
        f"programme/{day:%d%m%Y}"
    )
    meetings = meetings_from(program)

    print("Source PMU :", source)
    print("Réunions reçues :", len(meetings))

    countries = {}
    for m in meetings:
        country = country_of(m)
        countries[country] = countries.get(country, 0) + 1

    print("Pays détectés :", countries)

    selected = [
        m for m in meetings
        if french_meeting(m)
    ]

    print("Réunions françaises :", len(selected))

    if args.diagnostic:
        for m in meetings:
            print(
                "Réunion", m.get("numOfficiel"),
                "Pays", country_of(m),
                "Hippodrome", m.get("hippodrome")
            )
        return 0

    reports = []
    errors = []

    for meeting in selected:
        r = get_number(meeting.get("numOfficiel"))
        if r is None:
            continue
        if args.reunion and (
            args.reunion.upper() != f"R{r}"
        ):
            continue

        races = meeting.get("courses", [])
        if not isinstance(races, list):
            errors.append(f"R{r}: courses invalides")
            continue

        for race in races:
            c = get_number(race.get("numOrdre"))
            if c is None:
                continue
            try:
                result = analyse(
                    day, r, c, meeting, race
                )
                reports.append(result)
                print(f"R{r}C{c}: analyse enregistrée")
            except Exception as exc:
                msg = f"R{r}C{c}: {exc}"
                errors.append(msg)
                print("ERREUR :", msg)

    payload = {
        "logiciel": "TURBOFUSION M1-M5",
        "version": "1.2",
        "date_courses": day.isoformat(),
        "cree_a_paris": now().isoformat(),
        "source_programme": source,
        "reunions_recues": len(meetings),
        "reunions_francaises": len(selected),
        "pays_detectes": countries,
        "courses": reports,
        "erreurs": errors,
        "figes_crees": 0,
        "mode": "Diagnostic / lecture seule",
        "historique": (
            "Les anciens rapports et FIGÉS "
            "ne sont jamais modifiés."
        )
    }

    path = save_report(payload)
    print("Rapport :", path)
    print("Courses analysées :", len(reports))
    print("Erreurs :", len(errors))

    if not selected:
        print(
            "ALERTE : aucune réunion française reconnue. "
            "Vérifier le champ pays et la réponse PMU."
        )
        return 2

    if not reports:
        print(
            "ALERTE : aucune course analysée. "
            "Consulter les erreurs du rapport."
        )
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
          
