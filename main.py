#!/usr/bin/env python3
"""TURBOFUSION V1.1 — analyse hippique expérimentale, lecture seule.

Usage:
  python main.py --date 2026-10-18
  python main.py --date 2026-10-18 --reunion R1
  python main.py --diagnostic

Aucun pari réel. Les sélections sont indicatives et fondées sur les seules
informations effectivement disponibles. Les analyses sont horodatées.
"""
import argparse
import datetime as dt
import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Paris")
BASES = (
    "https://offline.turfinfo.api.pmu.fr/rest/client/7/",
    "https://online.turfinfo.api.pmu.fr/rest/client/1/",
)
OUT = Path("rapports_turbofusion")


def fetch(path):
    errors = []
    for base in BASES:
        url = base + path.lstrip("/")
        req = urllib.request.Request(url, headers={
            "User-Agent": "TURBOFUSION/1.1 (read-only)",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                return json.load(response), url
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError("Sources indisponibles : " + " | ".join(errors))


def get_program(day):
    return fetch(f"programme/{day:%d%m%Y}")


def get_participants(day, reunion, course):
    return fetch(f"programme/{day:%d%m%Y}/R{reunion}/C{course}/participants")


def normalize_horse(raw):
    return {
        "numero": raw.get("numPmu") or raw.get("numero"),
        "nom": raw.get("nom", "Inconnu"),
        "musique": raw.get("musique", ""),
        "age": raw.get("age"),
        "jockey": raw.get("jockey") or raw.get("driver"),
        "entraineur": raw.get("entraineur"),
        "non_partant": bool(raw.get("nonPartant", False)),
    }


def form_score(musique):
    """Indice heuristique très limité : ne déduit pas la valeur sportive réelle."""
    digits = [int(c) for c in str(musique)[:18] if c in "123456789"][:5]
    if not digits:
        return None
    return round(sum(11 - n for n in digits) / len(digits), 2)


def engine_ranking(horses, engine):
    eligible = [h for h in horses if not h["non_partant"] and h["numero"] is not None]
    def key(h):
        score = form_score(h["musique"])
        number = int(h["numero"]) if str(h["numero"]).isdigit() else 999
        if engine == 1:
            return (score is None, -(score or 0), number)
        if engine == 2:
            return (score is None, -(score or 0), -number)
        if engine == 3:
            return (score is None, -(score or 0), abs(number - 8), number)
        if engine == 4:
            return (score is None, -(score or 0), number % 3, number)
        return (score is None, -(score or 0), -abs(number - 8), number)
    return sorted(eligible, key=key)


def analyse_course(day, reunion, course, meta):
    raw, source = get_participants(day, reunion, course)
    if isinstance(raw, dict):
        items = raw.get("participants", [])
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    horses = [normalize_horse(h) for h in items if isinstance(h, dict)]
    known = sum(form_score(h["musique"]) is not None for h in horses if not h["non_partant"])
    active = sum(not h["non_partant"] for h in horses)
    result = {
        "reunion": f"R{reunion}", "course": f"C{course}",
        "hippodrome": meta.get("hippodrome", "Non renseigné"),
        "depart": meta.get("heureDepart"), "source": source,
        "partants": horses, "moteurs": [],
        "limites": ["Terrain, météo, aptitude, entourage et cote non évalués automatiquement."],
    }
    for m in range(1, 6):
        ranking = engine_ranking(horses, m)
        nums = [h["numero"] for h in ranking[:5]]
        sufficient = active >= 5 and known >= max(3, int(active * .7))
        result["moteurs"].append({
            "moteur": f"M{m}", "gagnant_espere": nums[0] if sufficient and nums else None,
            "meilleur_place": nums[1] if sufficient and len(nums) > 1 else None,
            "ordre_espere": nums if sufficient else [],
            "pari_retenu": "Simulation uniquement" if sufficient else "Aucune sélection",
            "qualification": "🟢 ⭐⭐⭐⭐ (données partielles)" if sufficient else "Données insuffisantes",
            "validation": "PV — non figé" if sufficient else "Non évalué",
        })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=dt.datetime.now(TZ).date().isoformat())
    parser.add_argument("--reunion", help="Exemple : R1")
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args()
    day = dt.date.fromisoformat(args.date)
    timestamp = dt.datetime.now(TZ)
    program, url = get_program(day)
    print("Source PMU :", url)
    if args.diagnostic:
        print("Connexion OK ; date :", day.isoformat())
        return
    meetings = program.get("programme", {}).get("reunions", [])
    reports = []
    for meeting in meetings:
        r = meeting.get("numOfficiel")
        if not isinstance(r, int) or (args.reunion and args.reunion.upper() != f"R{r}"):
            continue
        # Filtre géographique prudent : seules les réunions explicitement FR.
        country = str(meeting.get("pays", "")).upper()
        if country not in ("FR", "FRA", "FRANCE"):
            continue
        track = meeting.get("hippodrome", {})
        track_name = track.get("libelleCourt", "Inconnu") if isinstance(track, dict) else str(track)
        for race in meeting.get("courses", []):
            c = race.get("numOrdre")
            if not isinstance(c, int):
                continue
            try:
                reports.append(analyse_course(day, r, c, {
                    "hippodrome": track_name, "heureDepart": race.get("heureDepart")
                }))
                print(f"R{r}C{c} : analyse réalisée")
            except (RuntimeError, ValueError) as exc:
                print(f"R{r}C{c} : indisponible ({exc})")
    payload = {"logiciel": "TURBOFUSION", "version": "1.1",
               "date_courses": day.isoformat(), "cree_a_paris": timestamp.isoformat(),
               "mode": "lecture seule / expérimental / aucun pari réel",
               "source_programme": url, "courses": reports}
    OUT.mkdir(exist_ok=True)
    blob = json.dumps(payload, ensure_ascii=False, indent=2)
    suffix = hashlib.sha256(blob.encode()).hexdigest()[:10]
    path = OUT / f"turbofusion_{day.isoformat()}_{timestamp:%H%M%S}_{suffix}.json"
    path.write_text(blob, encoding="utf-8")
    print(f"Rapport : {path} | {len(reports)} course(s)")


if __name__ == "__main__":
    main()
