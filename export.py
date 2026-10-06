"""Export CSV d'une collection (shiny enrichis par `to_view` + `attach_phases`)."""
import csv
import io
import re

from duration import clock
from filters import generation, phase_status
from pokemon import BALLS, FAMILIES, GAMES, GENDERS, POKEDEX, display_name

PHASE_LABELS = {"cible": "phase finale", "phase": "phase", "seul": ""}

# (en-tête, valeur) — l'ordre des colonnes du fichier
COLUMNS = [
    ("n_pokedex", lambda s: s["species_id"]),
    ("espece", lambda s: POKEDEX.get(s["species_id"], "")),
    ("forme", lambda s: s["form"] or ""),
    ("nom_complet", lambda s: s["species"]),
    ("surnom", lambda s: s["nickname"] or ""),
    ("jeu", lambda s: s["game_label"]),
    ("famille_jeux", lambda s: FAMILIES[s["family"]][0]),
    ("generation_jeu", lambda s: generation(s) or ""),
    ("methode", lambda s: s["method"]),
    ("genre", lambda s: GENDERS[s["gender"]].split(" ", 1)[1]),
    ("date_capture", lambda s: s["caught_on"] or ""),
    ("rencontres", lambda s: "" if s["encounters"] is None else s["encounters"]),
    ("temps_chasse", lambda s: "" if s["duration"] is None else clock(s["duration"])),
    ("poke_ball", lambda s: BALLS[s["ball"]][0] if s["ball"] in BALLS else ""),
    ("lieu", lambda s: s["location"] or ""),
    ("charme_chroma", lambda s: "oui" if s["shiny_charm"] else "non"),
    ("statut_phase", lambda s: PHASE_LABELS[phase_status(s)]),
    ("numero_phase", lambda s: s["phase_number"] or ""),
    ("chasse_de", lambda s: s["phase_target"] or ""),
    ("id_cible", lambda s: s["phase_target_id"] or ""),  # relie les phases à leur cible à l'import
    ("nb_phases", lambda s: len(s["phases"]) or ""),
    ("note", lambda s: s["notes"] or ""),
    ("sprite_personnalise", lambda s: s["sprite_url"] or ""),
    ("id", lambda s: s["id"]),
]


def _safe(value):
    """Neutralise les formules : une cellule commençant par = + - @ serait exécutée par Excel."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def to_csv(shinies):
    """Texte CSV pour Excel en français : séparateur « ; », BOM UTF-8 pour les accents."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow([name for name, _ in COLUMNS])
    for s in shinies:
        writer.writerow([_safe(get(s)) for _, get in COLUMNS])
    return "﻿" + out.getvalue()


# --- Format « tracker de shiny » (celui que relit aussi importer.py) ---

TRACKER_GENDERS = {"M": "M", "F": "F", "N": "A"}
TRACKER_SHINY_HEADER = ["Pokémon", "Sexe", "Surnom", "Rencontres", "Méthode", "Jeu", "Lieu",
                        "Charme chroma", "Ball", "Date d'obtention"]
TRACKER_FAILED_HEADER = ["Pokémon", "Sexe", "Rencontres", "Méthode", "Jeu", "Lieu",
                         "Charme chroma", "Motif du fail", "Date d'obtention"]
TRACKER_HUNT_HEADER = ["Pokémon", "Rencontres", "Méthode", "Jeu", "Lieu", "Charme chroma", "Date de début"]


def _note_field(notes, label):
    """Valeur d'une ligne « Label : valeur » de la note (écrite par l'import), ou ""."""
    match = re.search(rf"^{label} : (.*)$", notes or "", re.MULTILINE)
    return match.group(1).strip() if match else ""


def _date_fr(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else ""


def to_tracker_csv(shinies, title, hunts=(), fails=()):
    """CSV en sections façon tracker de shiny : shiny obtenus, shiny manqués, chasses en cours.

    La version du jeu est reprise de la note, où l'import la range.
    """
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow([f"Shiny obtenus - {title}"])
    writer.writerow(TRACKER_SHINY_HEADER)
    for s in shinies:
        notes = s["notes"]
        writer.writerow([_safe(v) for v in (
            s["species"],
            TRACKER_GENDERS[s["gender"]],
            s["nickname"] or "",
            "" if s["encounters"] is None else s["encounters"],
            s["method"],
            _note_field(notes, "Version") or s["game_label"],
            s["location"] or "",
            "oui" if s["shiny_charm"] else "non",
            BALLS[s["ball"]][0].removesuffix(" (Hisui)") if s["ball"] in BALLS else "",
            _date_fr(s["caught_on"]),
        )])
    writer.writerow([])
    writer.writerow(["Shiny manqués"])
    writer.writerow(TRACKER_FAILED_HEADER)
    for f in fails:
        writer.writerow([_safe(v) for v in (
            f["species"],
            TRACKER_GENDERS.get(f["gender"], ""),
            "" if f["encounters"] is None else f["encounters"],
            f["method"],
            f["game_label"],
            f["location"] or "",
            "oui" if f["shiny_charm"] else "non",
            f["reason"] or "",
            _date_fr(f["failed_on"]),
        )])
    writer.writerow([])
    writer.writerow(["Shasses en cours"])
    writer.writerow(TRACKER_HUNT_HEADER)
    for h in hunts:
        writer.writerow([_safe(v) for v in (
            display_name(h["species_id"], h["form"]),
            h["count"],
            h["method"],
            GAMES.get(h["game"], (h["game"],))[0],
            h["location"] or "",
            "oui" if h["shiny_charm"] else "non",
            _date_fr(h["created_at"][:10]),
        )])
    return "﻿" + out.getvalue()
