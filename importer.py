"""Import CSV d'une collection.

Relit le fichier produit par export.py (aller-retour sans perte, phases comprises), et reste
tolérant pour un CSV fait à la main : séparateur « ; » ou « , », jeux et Balls par nom ou par clé,
espèce par n° ou par nom (« Rattata d’Alola » inclus), dates AAAA-MM-JJ ou JJ/MM/AAAA (heure ignorée).

Lit aussi l'export d'un tracker de shiny (voir export.to_tracker_csv) : fichier en sections
précédées d'un titre (« Shiny obtenus - … », « Shiny manqués », « Shasses en cours ») : les shiny
obtenus vont dans la collection, les chasses en cours dans le compteur, les shiny manqués dans leur liste ; jeux par version (« Violet », « Argent Soulsilver »), genre « A »
pour asexué, colonnes « Lieu » / « Charme chroma » reprises, version gardée dans la note.
"""
import csv
import io
import re
from datetime import date, datetime

from duration import parse_duration
from filters import normalize
from pokemon import BALLS, FORMS, GAMES, POKEDEX, forms_of

MAX_ROWS = 5000


def compact(text):
    """Clé de comparaison très tolérante : « Nidoran-f » = « Nidoran♀ », « M.Mime » = « M. Mime »."""
    text = normalize(text).replace("♀", "f").replace("♂", "m")
    return re.sub(r"[^a-z0-9]", "", text)


# Versions d'un jeu tel qu'enregistré sur le site (clé de GAMES) : « Violet » -> Écarlate / Violet
VERSIONS = {
    "rs": ["Rubis", "Saphir"],
    "rfvf": ["Rouge Feu", "Vert Feuille"],
    "dp": ["Diamant", "Perle"],
    "hgss": ["HeartGold", "SoulSilver", "Or HeartGold", "Argent SoulSilver"],
    "nb": ["Noir", "Blanc"],
    "nb2": ["Noir 2", "Blanc 2"],
    "xy": ["X", "Y"],
    "rosa": ["Rubis Oméga", "Saphir Alpha"],
    "sl": ["Soleil", "Lune"],
    "usul": ["Ultra-Soleil", "Ultra-Lune"],
    "lgpe": ["Let's Go Pikachu", "Let's Go Évoli"],
    "epee_bouclier": ["Épée", "Bouclier"],
    "deps": ["Diamant Étincelant", "Perle Scintillante"],
    "ev": ["Écarlate", "Violet"],
}
# Anciens libellés de Balls (exports antérieurs)
BALL_ALIASES = {"Plomb Ball": "leaden-ball", "Mégaton Ball": "gigaton-ball"}
# Dans Légendes Arceus, les Balls classiques sont leurs variantes de Hisui
HISUI_BALLS = {"poke-ball": "hisui-poke-ball", "great-ball": "hisui-great-ball",
               "ultra-ball": "hisui-ultra-ball", "heavy-ball": "hisui-heavy-ball"}

# Tables de correspondance tolérantes (sans accents, casse, espaces ni ponctuation)
GAME_BY_NAME = (
    {compact(key): key for key in GAMES}
    | {compact(name): key for key, names in VERSIONS.items() for name in names}
    | {compact(label): key for key, (label, _, _) in GAMES.items()}
)
BALL_BY_NAME = (
    {compact(key): key for key in BALLS}
    | {compact(name): key for name, key in BALL_ALIASES.items()}
    | {compact(label): key for key, (label, _) in BALLS.items()}
)
GENDER_BY_NAME = {
    "m": "M", "male": "M", "♂": "M",
    "f": "F", "femelle": "F", "♀": "F",
    "n": "N", "a": "N", "asexue": "N", "⚲": "N", "aucun": "N",
}
SPECIES_BY_NAME = {normalize(name): dex for dex, name in POKEDEX.items()}
SPECIES_BY_KEY = {compact(name): dex for dex, name in POKEDEX.items()}
FORM_BY_FULL_NAME = {
    normalize(info["full"]): (dex, key)
    for dex, data in FORMS.items() for key, info in data["forms"].items()
}
YES = {"oui", "o", "yes", "y", "x", "1", "true", "vrai"}

# Colonnes reconnues -> clé interne (premier nom trouvé dans l'en-tête)
ALIASES = {
    "dex": ["n_pokedex", "numero", "n°", "pokedex", "dex"],
    "species": ["espece", "espèce", "pokemon", "pokémon"],
    "form": ["forme", "form"],
    "full_name": ["nom_complet", "nom"],
    "nickname": ["surnom", "nickname"],
    "game": ["jeu", "game"],
    "method": ["methode", "méthode", "method"],
    "gender": ["genre", "gender", "sexe"],
    "caught_on": ["date_capture", "date d'obtention", "date_obtention", "date de début", "date_debut", "date"],
    "encounters": ["rencontres", "encounters"],
    "duration": ["temps_chasse", "temps de chasse", "duree", "durée"],
    "ball": ["poke_ball", "ball", "pokeball"],
    "notes": ["note", "notes"],
    "location": ["lieu"],
    "charm": ["charme chroma", "charme_chroma"],
    "reason": ["motif du fail", "motif", "raison"],
    "sprite_url": ["sprite_personnalise", "sprite"],
    "phase_number": ["numero_phase"],
    "target_id": ["id_cible"],
    "old_id": ["id"],
}
# Sections d'un export de tracker autres que les shiny obtenus
FAILED_SECTION = re.compile(r"manqu", re.IGNORECASE)
HUNTS_SECTION = re.compile(r"en cours", re.IGNORECASE)


def _unescape(value):
    """Annule la protection anti-formule de l'export (« '=… » -> « =… »)."""
    value = (value or "").strip()
    if len(value) > 1 and value[0] == "'" and value[1] in "=+-@":
        return value[1:]
    return value


def _parse_date(value):
    value = value.split()[0].split("T")[0]  # « 15/07/2025 19:16 » : l'heure est ignorée
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _parse_int(value):
    digits = re.sub(r"[\s  .]", "", value)  # « 1 234 » ou « 1.234 »
    return int(digits) if digits.isascii() and digits.isdigit() else None


def _resolve_species(row):
    """(n°, clé de forme, erreur)."""
    form = row.get("form", "")
    dex = None
    if row.get("dex"):
        n = _parse_int(row["dex"].lstrip("#"))
        if n in POKEDEX:
            dex = n
        else:
            return None, None, f"n° de Pokédex inconnu « {row['dex']} »"
    # Par nom : « Rattata » ou nom complet d'une forme (« Rattata d’Alola »), dans l'une ou l'autre colonne
    for column in ("species", "full_name"):
        if dex is not None or not row.get(column):
            continue
        name = normalize(row[column])
        if name in SPECIES_BY_NAME:
            dex = SPECIES_BY_NAME[name]
        elif name in FORM_BY_FULL_NAME:
            dex, guessed = FORM_BY_FULL_NAME[name]
            form = form or guessed
        elif compact(name) in SPECIES_BY_KEY:  # « Nidoran-f », « M.Mime »
            dex = SPECIES_BY_KEY[compact(name)]
    if dex is None:
        shown = row.get("species") or row.get("full_name") or ""
        return None, None, f"Pokémon inconnu « {shown} »" if shown else "Pokémon manquant"
    if form and form not in forms_of(dex):
        return None, None, f"forme « {form} » inconnue pour {POKEDEX[dex]}"
    return dex, form or None, None


def _sections(text, delimiter):
    """Découpe le fichier en sections {title, header, header_line, rows: [(n° de ligne, valeurs)]}.

    Un CSV classique n'a qu'une section, sans titre. Une ligne d'une seule cellule (sans séparateur)
    est un titre de section ; la ligne suivante est l'en-tête de la section.
    """
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    sections, title, current, line = [], None, None, 1
    for record in reader:
        start, line = line, reader.line_num + 1
        if not any(value.strip() for value in record):
            continue  # ligne vide
        if len(record) == 1:
            title, current = record[0].strip(), None
        elif current is None:
            current = {"title": title, "header": record, "header_line": start, "rows": []}
            sections.append(current)
        else:
            current["rows"].append((start, record))
    return sections


def _columns(header):
    """Clé interne -> index de colonne, d'après l'en-tête."""
    positions = {}
    for index, name in enumerate(header):
        positions.setdefault(normalize(name or "").strip(), index)
    columns = {}
    for key, names in ALIASES.items():
        for name in names:
            if normalize(name) in positions:
                columns[key] = positions[normalize(name)]
                break
    return columns


def _plural(n, word):
    return f"{n} {word}{'s' if n > 1 else ''}"


def _parse_common(row, problems):
    """Champs communs aux shiny et aux chasses : (n°, forme, jeu, méthode, date, rencontres)."""
    dex, form, error = _resolve_species(row)
    if error:
        problems.append(error)

    game_name = row.get("game", "")
    game = GAME_BY_NAME.get(compact(game_name)) if game_name else None
    if game is None:
        problems.append(f"jeu inconnu « {game_name} »")

    method = row.get("method", "")
    if not method:
        problems.append("méthode manquante")

    when = None
    if row.get("caught_on"):
        when = _parse_date(row["caught_on"])
        if when is None:
            problems.append(f"date invalide « {row['caught_on']} »")
        elif when > date.today().isoformat():
            problems.append(f"date dans le futur « {row['caught_on']} »")

    encounters = None
    if row.get("encounters"):
        encounters = _parse_int(row["encounters"])
        if encounters is None:
            problems.append(f"rencontres invalides « {row['encounters']} »")
    return dex, form, game, method[:200], when, encounters


def _location_charm(row):
    """(lieu ou None, charme chroma 0/1)."""
    return (row.get("location") or "")[:100] or None, int(normalize(row.get("charm", "")) in YES)


def _parse_hunt(line, row, errors):
    """Ligne de la section « Shasses en cours » -> chasse du compteur (ou None si erreur)."""
    problems = []
    dex, form, game, method, started_on, count = _parse_common(row, problems)
    if problems:
        errors.append((line, "chasse en cours : " + " ; ".join(problems)))
        return None
    location, shiny_charm = _location_charm(row)
    return {
        "line": line,
        "data": {
            "species_id": dex, "form": form, "game": game, "method": method,
            "location": location, "shiny_charm": shiny_charm, "count": count or 0, "created_at": f"{started_on} 00:00:00" if started_on else None,
        },
    }


def _parse_fail(line, row, errors):
    """Ligne de la section « Shiny manqués » -> shiny manqué (ou None si erreur)."""
    problems = []
    dex, form, game, method, failed_on, encounters = _parse_common(row, problems)
    gender = None
    if row.get("gender"):
        gender = GENDER_BY_NAME.get(row["gender"].lower()) or GENDER_BY_NAME.get(normalize(row["gender"]))
        if gender is None:
            problems.append(f"genre inconnu « {row['gender']} »")
    duration = parse_duration(row["duration"]) if row.get("duration") else None
    if problems:
        errors.append((line, "shiny manqué : " + " ; ".join(problems)))
        return None
    location, shiny_charm = _location_charm(row)
    return {
        "line": line,
        "data": {
            "species_id": dex, "form": form, "game": game, "method": method, "gender": gender,
            "encounters": encounters, "duration": duration, "location": location, "shiny_charm": shiny_charm,
            "reason": (row.get("reason") or "")[:200] or None, "failed_on": failed_on,
            "notes": (row.get("notes") or "")[:1000] or None,
        },
    }


def _parse_shiny(line, row, errors, unknown_gender):
    """Ligne de shiny obtenu -> shiny de la collection (ou None si erreur)."""
    problems = []
    dex, form, game, method, caught_on, encounters = _parse_common(row, problems)

    gender_name = row.get("gender", "")
    if gender_name:
        gender = GENDER_BY_NAME.get(gender_name.lower()) or GENDER_BY_NAME.get(normalize(gender_name))
        if gender is None:
            problems.append(f"genre inconnu « {gender_name} »")
    else:
        gender = "N"  # le tracker laisse parfois le sexe vide
        unknown_gender.append(line)

    ball = None
    if row.get("ball"):
        ball = BALL_BY_NAME.get(compact(row["ball"]))
        if ball is None:
            problems.append(f"Poké Ball inconnue « {row['ball']} »")
        elif game == "lpa":
            ball = HISUI_BALLS.get(ball, ball)

    duration = None
    if row.get("duration"):
        duration = parse_duration(row["duration"])
        if duration is None:
            problems.append(f"temps de chasse invalide « {row['duration']} »")

    sprite_url = row.get("sprite_url") or None
    if sprite_url and not sprite_url.startswith("https://"):
        problems.append("le sprite personnalisé doit commencer par https://")

    if problems:
        errors.append((line, " ; ".join(problems)))
        return None

    # Version précise du jeu (pas de colonne dédiée sur le site) : gardée en tête de la note
    game_name = row["game"]
    extra = []
    if compact(game_name) not in (compact(game), compact(GAMES[game][0])):
        extra.append(f"Version : {game_name}")
    location, shiny_charm = _location_charm(row)
    notes = "\n".join(extra + [row.get("notes") or ""]).strip()

    return {
        "line": line,
        "data": {
            "species_id": dex, "form": form, "game": game, "method": method,
            "gender": gender, "caught_on": caught_on, "nickname": (row.get("nickname") or "")[:40] or None,
            "encounters": encounters, "duration": duration, "ball": ball, "location": location, "shiny_charm": shiny_charm,
            "notes": notes[:1000] or None,
            "sprite_url": sprite_url,
        },
        "old_id": _parse_int(row.get("old_id", "")),
        "target_id": _parse_int(row.get("target_id", "")),
        "phase_number": _parse_int(row.get("phase_number", "")),
    }


def parse(text):
    """Analyse le CSV ; renvoie (shiny valides, chasses en cours valides, shiny manqués valides,
    erreurs [(n° de ligne, message)], remarques [texte])."""
    text = text.lstrip("﻿")
    if not text.strip():
        return [], [], [], [(0, "Le fichier est vide.")], []
    sample = next((l for l in text.splitlines() if ";" in l or "," in l), "")
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","

    rows, hunts, fails, errors, notices, unknown_gender = [], [], [], [], [], []
    sections = _sections(text, delimiter)
    if not sections:
        return [], [], [], [(1, "Aucune ligne d'en-tête trouvée.")], []
    for section in sections:
        title = section["title"] or ""
        is_fails = bool(FAILED_SECTION.search(title))
        is_hunts = not is_fails and bool(HUNTS_SECTION.search(title))
        columns = _columns(section["header"])
        if not ({"dex", "species", "full_name"} & columns.keys()):
            errors.append((section["header_line"], "Colonne Pokémon introuvable : il faut « n_pokedex », « espece » ou « nom_complet »."))
            continue
        required = (("game", "jeu"), ("method", "methode")) + ((("gender", "genre"),) if not (is_hunts or is_fails) else ())
        missing = [label for key, label in required if key not in columns]
        if missing:
            errors.append((section["header_line"], f"Colonne « {missing[0]} » introuvable."))
            continue

        for line, values in section["rows"]:
            if len(rows) + len(hunts) + len(fails) + len(errors) >= MAX_ROWS:
                errors.append((line, f"Limite de {MAX_ROWS} lignes atteinte : la suite est ignorée."))
                return rows, hunts, fails, errors, notices
            row = {key: _unescape(values[i] if i < len(values) else "") for key, i in columns.items()}
            if is_fails:
                fail = _parse_fail(line, row, errors)
                if fail:
                    fails.append(fail)
            elif is_hunts:
                hunt = _parse_hunt(line, row, errors)
                if hunt:
                    hunts.append(hunt)
            else:
                shiny = _parse_shiny(line, row, errors, unknown_gender)
                if shiny:
                    rows.append(shiny)

    if unknown_gender:
        shown = ", ".join(map(str, unknown_gender[:20])) + (" …" if len(unknown_gender) > 20 else "")
        notices.append(f"Sexe non renseigné ({_plural(len(unknown_gender), 'ligne')} : {shown}) : "
                       "enregistré comme asexué, à corriger si besoin.")
    return rows, hunts, fails, errors, notices


def fingerprint(data):
    """Identité d'un shiny pour repérer les doublons (même Pokémon, jeu, genre, date, surnom, rencontres)."""
    return (data["species_id"], data["form"], data["game"], data["gender"],
            data["caught_on"], data["nickname"], data["encounters"])


def fail_fingerprint(data):
    """Identité d'un shiny manqué : même Pokémon, forme, jeu, date, rencontres et motif."""
    return (data["species_id"], data["form"], data["game"], data["failed_on"], data["encounters"], data["reason"])


def hunt_fingerprint(data):
    """Identité d'une chasse en cours : même Pokémon, forme, jeu et méthode."""
    return (data["species_id"], data["form"], data["game"], data["method"])
