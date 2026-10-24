#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TURBOFUSION M1-M5
Synchronisation du tableau officiel v3.0

- Lecture des rapports de main.py
- Compatibilite avec les chemins du depot
- Conservation des FIGES historiques
- Controle des moteurs M1 a M5
- Publication atomique de dashboard.json
- Aucune prediction inventee
"""

import argparse
import json
import logging
import os
import re
import sys
import tempfile

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
PARIS = ZoneInfo("Europe/Paris")

REPORT_DIR = ROOT / "rapports_turbofusion"
FREEZE_DIR = ROOT / "figes_turbofusion"
DASHBOARD = ROOT / "dashboard.json"

MOTORS = ("M1", "M2", "M3", "M4", "M5")
MAX_BYTES = 10_000_000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
LOG = logging.getLogger("TURBOFUSION")


def now():
    return datetime.now(PARIS)


def read_json(path):
    try:
        if path.stat().st_size > MAX_BYTES:
            LOG.warning("Fichier trop volumineux : %s", path)
            return None

        with path.open("r", encoding="utf-8-sig") as f:
            return json.load(f)

    except (OSError, ValueError, UnicodeError) as exc:
        LOG.warning("Lecture impossible %s : %s", path, exc)
        return None


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".turbofusion_",
            suffix=".tmp",
            delete=False
        ) as f:
            temporary = Path(f.name)
            json.dump(
                data, f,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

        os.replace(temporary, path)

    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def number(value):
    if isinstance(value, bool):
        return None

    match = re.fullmatch(
        r"[RC]?(\d+)",
        str(value or "").strip(),
        re.IGNORECASE
    )

    if not match:
        return None

    n = int(match.group(1))
    return n if n > 0 else None


def selection(value):
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = re.split(r"[\s,;>\-]+", value)
    else:
        return []

    result = []
    for item in items:
        n = number(item)
        if n and n not in result:
            result.append(n)

    return result


def normalize_date(value):
    if not value:
        return None

    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def normalize_motor(raw, name):
    if not isinstance(raw, dict):
        raw = {}

    order = selection(
        raw.get("ordre_espere")
        or raw.get("ordre_arrivee_espere")
        or raw.get("selection")
        or []
    )

    winner = number(raw.get("gagnant_espere"))
    placed = number(raw.get("meilleur_place"))

    if not winner and order:
        winner = order[0]

    if not placed and len(order) > 1:
        placed = order[1]

    validation = str(
        raw.get("validation") or "NON FIGÉ"
    )

    frozen = (
        validation.upper().startswith("FIGÉ")
        or raw.get("fige") is True
    )

    return {
        "moteur": name,
        "gagnant_espere": winner,
        "meilleur_place": placed,
        "ordre_espere": order,
        "pari_retenu": raw.get("pari_retenu", "Aucun"),
        "qualification": raw.get(
            "qualification", "Non évalué"
        ),
        "validation": validation,
        "heure_paris": raw.get("heure_paris"),
        "fige": frozen
    }


def motors_from(raw):
    result = {}

    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict):
                name = str(
                    entry.get("moteur", "")
                ).upper()

                if name in MOTORS:
                    result[name] = normalize_motor(
                        entry, name
                    )

    elif isinstance(raw, dict):
        for name in MOTORS:
            entry = raw.get(name) or raw.get(name.lower())
            if entry:
                result[name] = normalize_motor(entry, name)

    for name in MOTORS:
        result.setdefault(
            name, normalize_motor({}, name)
        )

    return result


def race_key(day, reunion, course):
    return f"{day}_R{reunion}_C{course}"


def normalize_race(raw, day):
    if not isinstance(raw, dict):
        return None

    reunion = number(raw.get("reunion"))
    course = number(raw.get("course"))

    if not reunion or not course:
        return None

    motors = motors_from(raw.get("moteurs", []))

    horses = raw.get("partants", [])
    if not isinstance(horses, list):
        horses = []

    active = [
        h for h in horses
        if isinstance(h, dict)
        and not h.get("non_partant", False)
    ]

    return {
        "id": race_key(day, reunion, course),
        "date_course": day,
        "reunion": f"R{reunion}",
        "course": f"C{course}",
        "hippodrome": raw.get(
            "hippodrome", "Non renseigné"
        ),
        "depart_paris": raw.get("depart_paris"),
        "nombre_partants": raw.get(
            "nombre_partants", len(active)
        ),
        "non_partants": raw.get(
            "non_partants", []
        ),
        "partants": horses,
        "moteurs": motors,
        "source": raw.get("source"),
        "nouveaux_figes": raw.get(
            "nouveaux_figes", []
        )
    }


def report_entries(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    if isinstance(data.get("courses"), list):
        return data["courses"]

    if "reunion" in data and "course" in data:
        return [data]

    return []


def load_reports(day):
    races = {}
    count = 0

    if not REPORT_DIR.exists():
        LOG.warning("Dossier des rapports absent")
        return races, count

    paths = sorted(
        REPORT_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime
    )

    for path in paths[-2000:]:
        data = read_json(path)
        if data is None:
            continue

        count += 1

        report_day = None
        if isinstance(data, dict):
            report_day = normalize_date(
                data.get("date_course")
                or data.get("date")
            )

        for raw in report_entries(data):
            if not isinstance(raw, dict):
                continue

            current_day = normalize_date(
                raw.get("date_course")
            ) or report_day

            if not current_day:
                departure = raw.get("depart_paris")
                current_day = normalize_date(departure)

            if current_day != day:
                continue

            race = normalize_race(raw, day)
            if race is None:
                continue

            previous = races.get(race["id"])

            if previous:
                for name in MOTORS:
                    old = previous["moteurs"][name]
                    if old["fige"]:
                        race["moteurs"][name] = old

            races[race["id"]] = race

    return races, count


def restore_freezes(races, day):
    if not FREEZE_DIR.exists():
        return 0

    restored = 0

    for path in sorted(FREEZE_DIR.glob("*.json")):
        data = read_json(path)

        if not isinstance(data, dict):
            continue

        if normalize_date(
            data.get("date_course")
        ) != day:
            continue

        reunion = None
        course = None

        match = re.fullmatch(
            r"R(\d+)C(\d+)",
            str(data.get("course", "")),
            re.IGNORECASE
        )

        if match:
            reunion = int(match.group(1))
            course = int(match.group(2))

        if not reunion or not course:
            continue

        key = race_key(day, reunion, course)

        if key not in races:
            races[key] = normalize_race({
                "reunion": reunion,
                "course": course,
                "hippodrome": data.get("hippodrome"),
                "depart_paris": data.get("depart_paris"),
                "partants": data.get("partants", []),
                "source": data.get("source")
            }, day)

        race = races[key]
        raw_motor = data.get("pronostic", {})

        if not isinstance(raw_motor, dict):
            continue

        name = str(
            raw_motor.get("moteur", "")
        ).upper()

        if name not in MOTORS:
            continue

        motor = normalize_motor(raw_motor, name)

        # L'archive est la reference historique.
        motor["validation"] = "FIGÉ HISTORIQUE (IMMUTABLE)"
        motor["fige"] = True
        motor["heure_paris"] = (
            data.get("fige_a_paris")
            or motor["heure_paris"]
        )

        race["moteurs"][name] = motor
        restored += 1

    return restored


def sort_race(race):
    departure = race.get("depart_paris") or ""
    return (
        departure,
        race.get("reunion", ""),
        race.get("course", "")
    )


def synchronize(day):
    races, count = load_reports(day)
    restored = restore_freezes(races, day)

    ordered = sorted(
        races.values(), key=sort_race
    )

    frozen_count = 0

    for race in ordered:
        motors = race["moteurs"]

        frozen = sum(
            bool(motors[name]["fige"])
            for name in MOTORS
        )

        frozen_count += frozen
        race["nombre_figes"] = frozen

        if frozen == 5:
            race["statut"] = "FIGÉ COMPLET"
        elif frozen:
            race["statut"] = "FIGÉ PARTIEL"
        else:
            race["statut"] = "NON FIGÉ"

        race["fige"] = frozen > 0

        # Compatibilite avec le dashboard existant.
        race["moteurs"] = [
            motors[name] for name in MOTORS
        ]

    timestamp = now().isoformat()

    dashboard = {
        "logiciel": "TURBOFUSION M1-M5",
        "version_dashboard": "3.0",
        "sous_titre": (
            "Intelligence hippique spécialisée"
        ),
        "devise": "La magie du savoir",
        "date_courses": day,
        "synchronise_a_paris": timestamp,
        "fuseau_horaire": "Europe/Paris",
        "statut": (
            "DONNÉES DISPONIBLES"
            if ordered else "AUCUNE DONNÉE"
        ),
        "statistiques": {
            "rapports_lus": count,
            "courses": len(ordered),
            "figes_moteurs": frozen_count,
            "archives_figees_lues": restored
        },
        "courses": ordered,
        "avertissement": (
            "Analyses expérimentales. "
            "Aucune garantie de résultat. "
            "Aucun pari réel exécuté."
        )
    }

    atomic_json(DASHBOARD, dashboard)

    LOG.info(
        "Synchronisation terminée : "
        "%s courses, %s FIGÉS",
        len(ordered), frozen_count
    )

    return dashboard


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        help="Date AAAA-MM-JJ"
    )
    args = parser.parse_args()

    day = args.date or now().date().isoformat()

    try:
        date.fromisoformat(day)
    except ValueError:
        LOG.error("Date invalide : %s", day)
        return 2

    try:
        dashboard = synchronize(day)
        print(json.dumps(
            dashboard["statistiques"],
            indent=2,
            ensure_ascii=False
        ))
        return 0

    except Exception:
        LOG.exception("Erreur de synchronisation")
        return 1


if __name__ == "__main__":
    sys.exit(main())
