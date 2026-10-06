"""Méthodes de chasse et taux shiny par jeu, lus dans data/methodes.json (format : data/LISEZMOI_methodes.md).

Le fichier est relu dès qu'il change : pas besoin de redémarrer le site.
"""
import json
import os

from pokemon import BASE_DIR, GAMES, species_key

PATH = os.path.join(BASE_DIR, "data", "methodes.json")
FILE = "methodes.json"
_cache = {}


def _rate(value, where, field, problems):
    """Taux « 1 sur N » : entier ≥ 1 ou null (inconnu / variable)."""
    if value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 1):
        return value
    problems.append(f"{FILE}, {where} : « {field} » doit être un nombre entier ≥ 1 ou null")
    return None


def _rows(entries, where, problems):
    """Lignes [{"jeux": [...], "taux", "charme", "note"}] -> {jeu: (taux, charme, note)}."""
    by_game = {}
    if not isinstance(entries, list):
        problems.append(f"{FILE}, {where} : « jeux » doit être une liste, \"standard\" ou \"tous\"")
        return by_game
    for row in entries:
        if not isinstance(row, dict) or not isinstance(row.get("jeux"), list):
            problems.append(f"{FILE}, {where} : chaque ligne doit avoir une liste « jeux »")
            continue
        info = (_rate(row.get("taux"), where, "taux", problems),
                _rate(row.get("charme"), where, "charme", problems),
                row.get("note") or "")
        for game in row["jeux"]:
            if game not in GAMES:
                problems.append(f"{FILE}, {where} : jeu inconnu « {game} » (clés de GAMES dans pokemon.py)")
            else:
                by_game[game] = info
    return by_game


def _load():
    """(méthodes, problèmes) ; méthodes = [{"name", "description", "aliases", "games": {jeu: (taux, charme, note)}}]."""
    try:
        mtime = os.path.getmtime(PATH)
    except OSError:
        return [], [f"{FILE} : fichier introuvable"]
    if _cache.get("mtime") == mtime:
        return _cache["methods"], _cache["problems"]

    problems = []
    try:
        with open(PATH, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError) as error:
        data = {}
        problems.append(f"{FILE} : JSON invalide ({error})")

    standard = _rows(data.get("standard", []), "« standard »", problems)
    methods, seen = [], set()
    for i, entry in enumerate(data.get("methodes", []), start=1):
        name = (entry.get("nom") or "").strip() if isinstance(entry, dict) else ""
        if not name:
            problems.append(f"{FILE}, méthode n° {i} : « nom » manquant")
            continue
        where = f"« {name} »"
        games = entry.get("jeux")
        if games == "standard":
            games = dict(standard)
        elif games == "tous":
            info = (_rate(entry.get("taux"), where, "taux", problems),
                    _rate(entry.get("charme"), where, "charme", problems), entry.get("note") or "")
            games = {game: info for game in GAMES}
        else:
            games = _rows(games, where, problems)
        if "remplace" in entry:  # lignes qui remplacent le taux de certains jeux
            games.update(_rows(entry["remplace"], where, problems))
        for game in entry.get("sauf", []):
            games.pop(game, None)
        aliases = [a for a in entry.get("alias", []) if isinstance(a, str)]
        keys = {species_key(label): label for label in [name, *aliases]}
        for key, label in keys.items():
            if key in seen:
                problems.append(f"{FILE}, {where} : « {label} » est déjà utilisé par une autre méthode")
        seen |= keys.keys()
        methods.append({"name": name, "description": entry.get("description") or "",
                        "aliases": aliases, "games": games})

    _cache.update(mtime=mtime, methods=methods, problems=problems)
    return methods, problems


def problems():
    return _load()[1]


def names():
    """Toutes les méthodes, dans l'ordre du fichier."""
    return [m["name"] for m in _load()[0]]


def find(label):
    """Méthode correspondant à un libellé (nom ou alias, accents et casse ignorés), ou None."""
    key = species_key(label or "")
    return next((m for m in _load()[0]
                 if key in (species_key(n) for n in [m["name"], *m["aliases"]])), None)


def odds(label, game, charm=False):
    """(taux « 1 sur N » ou None, note) pour cette méthode dans ce jeu ; (None, "") si inconnu."""
    method = find(label)
    if method is None or game not in method["games"]:
        return None, ""
    rate, charm_rate, note = method["games"][game]
    return (charm_rate or rate) if charm else rate, note


def by_game():
    """{jeu: [[nom, taux, taux avec charme, note, description], …]} pour les formulaires (static/methods.js)."""
    table = {game: [] for game in GAMES}
    for m in _load()[0]:
        for game, (rate, charm_rate, note) in m["games"].items():
            table[game].append([m["name"], rate, charm_rate, note, m["description"]])
    return table
