#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TURBOFUSION M1-M5
Synchronisation du tableau officiel.

Fonctions :
- Lecture des rapports JSON locaux
- Validation des courses et des moteurs
- Filtrage selon la date de Paris
- Conservation des FIGES historiques
- Generation atomique du dashboard JSON
- Journalisation et controle des erreurs

Aucune prediction n'est inventee.
Aucun FIGE n'est cree par ce script.
"""

import argparse
import json
import logging
import os
import re
import sys
import tempfile

from datetime import datetime, date, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


# ==========================================
# CONFIGURATION
# ==========================================

ROOT = Path(__file__).resolve().parent
PARIS = ZoneInfo("Europe/Paris")

REPORT_DIRS = [
    ROOT / "reports",
    ROOT / "data" / "reports",
    ROOT / "outputs",
    ROOT / "results",
]

DASHBOARD = ROOT / "dashboard.json"
ARCHIVE = ROOT / "data" / "figes_archive.json"

MOTORS = ("M1", "M2", "M3", "M4", "M5")

LOG = logging.getLogger("TURBOFUSION")

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 2000

DATE_KEYS = (
    "date_course",
    "race_date",
    "date",
)

RACE_KEYS = (
    "courses",
    "races",
)

MOTOR_KEYS = (
    "moteurs",
    "motors",
    "analyses",
)

FREEZE_KEYS = (
    "fige",
    "figé",
    "frozen",
    "locked",
)

VALID_STATUSES = {
    "VALIDE",
    "VALIDÉ",
    "VALIDEE",
    "VALIDÉE",
    "FIGE",
    "FIGÉ",
    "NON VALIDE",
    "NON VALIDÉ",
    "EN ATTENTE",
    "INCOMPLET",
}


# ==========================================
# OUTILS
# ==========================================

def now_paris():
    return datetime.now(PARIS)


def today_paris():
    return now_paris().date().isoformat()


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


def first_value(obj, keys, default=None):
    if not isinstance(obj, dict):
        return default

    for key in keys:
        value = obj.get(key)
        if value is not None and value != "":
            return value

    return default


def normalize_date(value):
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.astimezone(PARIS).date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()

    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        pass

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        ).date().isoformat()
    except ValueError:
        pass

    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue

    return None


def clean_number(value):
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        number = int(value)
        return number if number > 0 else None
    except (ValueError, TypeError):
        return None


def normalize_selection(value):
    if isinstance(value, str):
        parts = re.split(r"[\s,;>\-]+", value.strip())
    elif isinstance(value, list):
        parts = value
    else:
        return []

    result = []
    seen = set()

    for item in parts:
        number = clean_number(item)

        if number is not None and number not in seen:
            result.append(number)
            seen.add(number)

    return result


def is_frozen(obj):
    if not isinstance(obj, dict):
        return False

    value = first_value(obj, FREEZE_KEYS, False)

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().upper() in (
            "TRUE", "OUI", "YES", "1", "FIGE", "FIGÉ"
        )

    return value == 1


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=".turbo_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(
                data,
                handle,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)

    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def read_json(path):
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            LOG.warning("Fichier trop volumineux : %s", path)
            return None

        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)

    except (OSError, ValueError, UnicodeError) as exc:
        LOG.warning("Lecture impossible %s : %s", path, exc)
        return None


# ==========================================
# IDENTIFICATION DES COURSES
# ==========================================

def race_identity(race):
    hippodrome = str(
        first_value(
            race,
            ("hippodrome", "track", "lieu"),
            "",
        )
    ).strip().upper()

    reunion = clean_number(
        first_value(race, ("reunion", "réunion", "r"))
    )

    course = clean_number(
        first_value(race, ("course", "numero_course", "c"))
    )

    race_date = normalize_date(
        first_value(race, DATE_KEYS)
    )

    if not race_date or not reunion or not course:
        return None

    return (
        race_date,
        hippodrome,
        reunion,
        course,
    )


def race_id(race):
    identity = race_identity(race)

    if identity is None:
        return None

    race_date, track, reunion, course = identity

    track = re.sub(r"[^A-Z0-9]+", "_", track).strip("_")

    return (
        f"{race_date}_"
        f"{track or 'INCONNU'}_"
        f"R{reunion}C{course}"
    )


# ==========================================
# NORMALISATION DES MOTEURS
# ==========================================

def normalize_motor(name, source):
    if not isinstance(source, dict):
        return None

    selection = normalize_selection(
        first_value(
            source,
            (
                "ordre_arrivee_espere",
                "ordre_arrivée_espéré",
                "selection",
                "pronostic",
                "combinaison",
            ),
            [],
        )
    )

    winner = clean_number(
        first_value(
            source,
            ("gagnant_espere", "gagnant", "winner"),
        )
    )

    placed = clean_number(
        first_value(
            source,
            ("meilleur_place", "place", "placed"),
        )
    )

    if winner is None and selection:
        winner = selection[0]

    if winner is not None and winner not in selection:
        selection.insert(0, winner)

    status = str(
        first_value(
            source,
            ("qualification", "statut", "status"),
            "EN ATTENTE",
        )
    ).strip().upper()

    frozen = is_frozen(source)

    freeze_time = first_value(
        source,
        (
            "heure_fige",
            "heure_figé",
            "fige_at",
            "frozen_at",
        ),
    )

    # Un FIGE doit avoir une heure traçable.
    if frozen and not freeze_time:
        LOG.warning(
            "%s : FIGE sans horodatage, non confirme",
            name,
        )
        frozen = False
        status = "INCOMPLET"

    if frozen:
        status = "FIGÉ"

    if status not in VALID_STATUSES:
        status = "EN ATTENTE"

    return {
        "moteur": name,
        "gagnant_espere": winner,
        "meilleur_place": placed,
        "ordre_arrivee_espere": selection,
        "pari_retenu": first_value(
            source,
            ("pari_retenu", "pari", "bet"),
        ),
        "qualification": status,
        "validation": first_value(
            source,
            ("validation", "validated"),
        ),
        "fige": frozen,
        "heure_fige": freeze_time if frozen else None,
        "score": first_value(
            source,
            ("score", "confidence", "confiance"),
        ),
        "analyse": first_value(
            source,
            ("analyse", "commentaire", "reason"),
        ),
    }


def extract_motors(race):
    raw = first_value(race, MOTOR_KEYS, {})

    result = {}

    for name in MOTORS:
        source = None

        if isinstance(raw, dict):
            source = raw.get(name) or raw.get(name.lower())

        elif isinstance(raw, list):
            for entry in raw:
                if not isinstance(entry, dict):
                    continue

                entry_name = str(
                    first_value(
                        entry,
                        ("moteur", "motor", "name"),
                        "",
                    )
                ).upper()

                if entry_name == name:
                    source = entry
                    break

        if source is None:
            source = race.get(name) or race.get(name.lower())

        result[name] = normalize_motor(name, source)

    return result


# ==========================================
# NORMALISATION DES RAPPORTS
# ==========================================

def normalize_race(source, inherited_date=None):
    if not isinstance(source, dict):
        return None

    race = dict(source)

    if not first_value(race, DATE_KEYS):
        race["date_course"] = inherited_date

    race["date_course"] = normalize_date(
        first_value(race, DATE_KEYS)
    )

    identity = race_identity(race)

    if identity is None:
        LOG.warning("Course ignoree : identifiant incomplet")
        return None

    identifier = race_id(race)

    motors = extract_motors(race)

    participants = first_value(
        race,
        ("partants", "nombre_partants", "participants"),
    )

    if isinstance(participants, list):
        participants = len(participants)
    else:
        participants = clean_number(participants)

    non_runners = normalize_selection(
        first_value(
            race,
            ("non_partants", "np", "non_runners"),
            [],
        )
    )

    return {
        "id": identifier,
        "date_course": race["date_course"],
        "hippodrome": first_value(
            race, ("hippodrome", "track", "lieu")
        ),
        "reunion": identity[2],
        "course": identity[3],
        "heure_depart": first_value(
            race,
            ("heure_depart", "depart", "start_time"),
        ),
        "discipline": first_value(
            race, ("discipline", "specialite")
        ),
        "distance": first_value(
            race, ("distance", "distance_m")
        ),
        "terrain": first_value(
            race, ("terrain", "going")
        ),
        "partants": participants,
        "non_partants": non_runners,
        "moteurs": motors,
        "arrivee_officielle": normalize_selection(
            first_value(
                race,
                ("arrivee_officielle", "official_result"),
                [],
            )
        ),
        "source": first_value(
            race, ("source", "source_url")
        ),
        "source_verifiee": (
            first_value(
                race,
                ("source_verifiee", "source_verified"),
            ) is True
        ),
    }


def extract_races(document):
    if isinstance(document, list):
        return document, None

    if not isinstance(document, dict):
        return [], None

    inherited_date = first_value(document, DATE_KEYS)

    for key in RACE_KEYS:
        value = document.get(key)

        if isinstance(value, list):
            return value, inherited_date

    if any(
        key in document
        for key in ("reunion", "réunion")
    ):
        return [document], inherited_date

    return [], inherited_date


# ==========================================
# PROTECTION DES FIGES
# ==========================================

def merge_races(old, new):
    if old is None:
        return new

    if new is None:
        return old

    merged = dict(old)
    merged.update(new)

    old_motors = old.get("moteurs", {})
    new_motors = new.get("moteurs", {})

    merged_motors = {}

    for name in MOTORS:
        previous = old_motors.get(name)
        current = new_motors.get(name)

        # Un FIGE deja enregistre est immuable.
        if isinstance(previous, dict) and previous.get("fige"):
            merged_motors[name] = previous
        else:
            merged_motors[name] = current or previous

    merged["moteurs"] = merged_motors

    return merged


def load_archive():
    data = read_json(ARCHIVE) if ARCHIVE.exists() else {}

    if not isinstance(data, dict):
        return {}

    return {
        key: value
        for key, value in data.items()
        if isinstance(value, dict)
    }


def update_archive(archive, races):
    for race in races:
        identifier = race["id"]

        frozen_motors = {
            name: motor
            for name, motor in race["moteurs"].items()
            if isinstance(motor, dict)
            and motor.get("fige") is True
        }

        if not frozen_motors:
            continue

        if identifier not in archive:
            archive[identifier] = {
                **race,
                "moteurs": {
                    name: None for name in MOTORS
                },
            }

        previous = archive[identifier]
        previous_motors = previous.setdefault("moteurs", {})

        for name, motor in frozen_motors.items():
            old = previous_motors.get(name)

            if not isinstance(old, dict) or not old.get("fige"):
                previous_motors[name] = motor

    return archive


# ==========================================
# LECTURE DES RAPPORTS
# ==========================================

def discover_files():
    files = set()

    for directory in REPORT_DIRS:
        if not directory.is_dir():
            continue

        for path in directory.rglob("*.json"):
            if path.is_file():
                files.add(path)

    return sorted(files, key=lambda p: str(p))[:MAX_FILES]


def load_reports(target_date):
    races = {}
    files = discover_files()

    LOG.info("Rapports trouves : %d", len(files))

    for path in files:
        document = read_json(path)

        if document is None:
            continue

        entries, inherited_date = extract_races(document)

        for entry in entries:
            race = normalize_race(entry, inherited_date)

            if race is None:
                continue

            if race["date_course"] != target_date:
                continue

            identifier = race["id"]

            races[identifier] = merge_races(
                races.get(identifier),
                race,
            )

    return races, len(files)


# ==========================================
# CONTROLE DES COURSES
# ==========================================

def validate_race(race):
    motors = race.get("moteurs", {})

    available = sum(
        isinstance(motors.get(name), dict)
        for name in MOTORS
    )

    frozen = sum(
        isinstance(motors.get(name), dict)
        and motors[name].get("fige") is True
        for name in MOTORS
    )

    race["nombre_moteurs_disponibles"] = available
    race["nombre_figes"] = frozen

    if frozen:
        race["statut"] = "FIGÉ PARTIEL" if frozen < 5 else "FIGÉ"
    elif available:
        race["statut"] = "ANALYSE DISPONIBLE"
    else:
        race["statut"] = "DONNÉES INSUFFISANTES"

    return race


def sort_key(race):
    time_value = str(race.get("heure_depart") or "99:99")

    match = re.search(r"(\d{1,2}):(\d{2})", time_value)

    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        time_sort = hour * 60 + minute
    else:
        time_sort = 9999

    return (
        time_sort,
        race.get("reunion") or 999,
        race.get("course") or 999,
    )


# ==========================================
# SYNCHRONISATION
# ==========================================

def synchronize(target_date=None):
    target_date = target_date or today_paris()

    LOG.info("Synchronisation du %s", target_date)

    archive = load_archive()
    current, file_count = load_reports(target_date)

    # Restaurer les FIGES archives du jour.
    for identifier, archived in archive.items():
        if archived.get("date_course") != target_date:
            continue

        current[identifier] = merge_races(
            archived,
            current.get(identifier),
        )

    races = [
        validate_race(race)
        for race in current.values()
    ]

    races.sort(key=sort_key)

    frozen_count = sum(
        race["nombre_figes"]
        for race in races
    )

    motor_count = sum(
        race["nombre_moteurs_disponibles"]
        for race in races
    )

    dashboard = {
        "logiciel": "TURBOFUSION M1-M5",
        "sous_titre": "Intelligence hippique specialisee",
        "devise": "La magie du savoir",
        "version_schema": 1,
        "date": target_date,
        "fuseau_horaire": "Europe/Paris",
        "derniere_synchronisation": now_paris().isoformat(),
        "statut": (
            "DONNEES DISPONIBLES"
            if races else "AUCUNE DONNEE VALIDEE"
        ),
        "statistiques": {
            "fichiers_examines": file_count,
            "courses": len(races),
            "analyses_moteurs": motor_count,
            "figes_moteurs": frozen_count,
        },
        "moteurs": list(MOTORS),
        "courses": races,
        "avertissement": (
            "Pronostics issus des rapports disponibles. "
            "Aucune garantie de resultat. "
            "Les donnees absentes ne sont pas inventees."
        ),
    }

    # Archiver avant de publier le tableau.
    archive = update_archive(archive, races)

    atomic_write(ARCHIVE, archive)
    atomic_write(DASHBOARD, dashboard)

    LOG.info(
        "Termine : %d courses, %d analyses, %d FIGES",
        len(races),
        motor_count,
        frozen_count,
    )

    return dashboard


# ==========================================
# EXECUTION
# ==========================================

def main():
    parser = argparse.ArgumentParser(
        description="Synchronisation TURBOFUSION M1-M5"
    )

    parser.add_argument(
        "--date",
        default=None,
        help="Date de course AAAA-MM-JJ",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    target = args.date or today_paris()

    try:
        date.fromisoformat(target)
    except ValueError:
        LOG.error("Date invalide : %s", target)
        return 2

    try:
        result = synchronize(target)

        print(
            json.dumps(
                result["statistiques"],
                ensure_ascii=False,
                indent=2,
            )
        )

        return 0

    except Exception:
        LOG.exception("Echec de synchronisation")
        return 1


if __name__ == "__main__":
    sys.exit(main())

