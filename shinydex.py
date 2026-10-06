"""Shinydex : Pokédex national et Pokédex régionaux par famille de jeux.

Chaque Pokédex est un fichier modifiable à la main : data/shinydex/<famille>.json
(et national.json), au format décrit dans data/shinydex/LISEZMOI.md :

    {"nom": "Or / Argent / Cristal",
     "sections": [{"titre": "Johto", "debut": 1, "pokemon": ["Germignon", "Macronium", …]}]}

Les fichiers sont relus quand ils changent : pas besoin de redémarrer le site.
Une ligne illisible n'empêche pas le site de fonctionner : elle est ignorée et signalée
sur la page Shinydex (`problems()`).
"""
import difflib
import json
import os
from collections import Counter

from filters import normalize
from pokemon import (
    BASE_DIR, FAMILIES, FORMS, GAMES, MAIN_COLLECTION, MAIN_FAMILIES, POKEDEX, display_name,
    sprite_candidates,
)

NATIONAL = "national"
DEX_DIR = os.path.join(BASE_DIR, "data", "shinydex")

_SPECIES_BY_NAME = {normalize(name): dex for dex, name in POKEDEX.items()}
# Nom complet d'une forme (« Rattata d’Alola », « Zarbi B ») -> (n°, clé de forme)
_FORM_BY_NAME = {
    normalize(info["full"]): (dex, key)
    for dex, data in FORMS.items() for key, info in data["forms"].items()
}
_cache = {}  # clé -> (date de modification, sections, problèmes)


def _resolve(entry):
    """Ligne d'un Pokédex -> (n° national, clé de forme ou None), ou None si illisible.

    Accepte un nom d'espèce (« Pikachu »), un nom de forme (« Rattata d’Alola »), accents et
    majuscules libres, ou un n° national (25, « #25 »).
    """
    if isinstance(entry, int) and not isinstance(entry, bool):
        return (entry, None) if entry in POKEDEX else None
    if not isinstance(entry, str):
        return None
    text = entry.strip()
    number = text.lstrip("#")
    if number.isascii() and number.isdigit():
        return (int(number), None) if int(number) in POKEDEX else None
    name = normalize(text)
    if name in _SPECIES_BY_NAME:
        return _SPECIES_BY_NAME[name], None
    return _FORM_BY_NAME.get(name)


def _suggest(entry):
    names = {**{n: POKEDEX[d] for n, d in _SPECIES_BY_NAME.items()},
             **{n: display_name(d, k) for n, (d, k) in _FORM_BY_NAME.items()}}
    close = difflib.get_close_matches(normalize(str(entry)), names, n=1, cutoff=0.75)
    return f" (vouliez-vous dire « {names[close[0]]} » ?)" if close else ""


def _load(key):
    """Sections d'un Pokédex : [{"name", "entries": [[n° régional, n° national], …]}] + problèmes."""
    path = os.path.join(DEX_DIR, f"{key}.json")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return [], [f"{key}.json : fichier introuvable"]
    if key in _cache and _cache[key][0] == mtime:
        return _cache[key][1], _cache[key][2]

    problems = []
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError) as error:
        problems.append(f"{key}.json : JSON invalide ({error})")
        data = {}

    sections = []
    for i, section in enumerate(data.get("sections", []), start=1):
        title = section.get("titre") or f"Section {i}"
        start = section.get("debut", 1)
        if not isinstance(start, int):
            problems.append(f"{key}.json, « {title} » : « debut » doit être un nombre")
            start = 1
        entries = []
        for position, entry in enumerate(section.get("pokemon", [])):
            resolved = _resolve(entry)
            if resolved is None:
                problems.append(
                    f"{key}.json, « {title} », n° {start + position} : Pokémon inconnu « {entry} »"
                    + _suggest(entry)
                )
                continue
            # Le numéro régional suit la position dans la liste, même si une ligne est ignorée
            entries.append([start + position, *resolved])
        for (species, form), n in Counter((s, f) for _, s, f in entries).items():
            if n > 1:
                problems.append(f"{key}.json, « {title} » : {display_name(species, form)} apparaît {n} fois")
        sections.append({"name": title, "entries": entries})

    _cache[key] = (mtime, sections, problems)
    return sections, problems


def _sections(dex):
    return _load(dex)[0]


def problems():
    """Toutes les erreurs trouvées dans les fichiers de Pokédex."""
    return [p for key in [NATIONAL, *MAIN_FAMILIES] for p in _load(key)[1]]


def dexes(collection):
    """Pokédex proposés : national + familles pour la collection principale, national seul sinon."""
    return [NATIONAL, *MAIN_FAMILIES] if collection == MAIN_COLLECTION else [NATIONAL]


def _entries(dex):
    """Cases distinctes du Pokédex : {(n°, forme)} ; forme None = toutes formes."""
    return {(species, form) for section in _sections(dex) for _, species, form in section["entries"]}


def _in_scope(shinies, dex):
    """Un Pokédex régional ne compte que les captures faites dans les jeux de sa famille."""
    return [s for s in shinies if dex == NATIONAL or s["family"] == dex]


def _index(scope):
    """Shiny regroupés par (n°, forme) et par n° (toutes formes), dans l'ordre de `scope`.

    Une case sans forme accepte toutes les formes de l'espèce ; une case de forme, seulement elle.
    """
    index = {}
    for s in scope:
        index.setdefault((s["species_id"], None), []).append(s)
        if s["form"] is not None:  # forme de base : déjà comptée dans la case sans forme
            index.setdefault((s["species_id"], s["form"]), []).append(s)
    return index


def progress(shinies, collection=MAIN_COLLECTION):
    """[(clé, libellé, cases capturées, taille)] pour le national puis chaque famille de la collection."""
    rows = []
    for dex in dexes(collection):
        entries = _entries(dex)
        index = _index(_in_scope(shinies, dex))
        label = "Pokédex national" if dex == NATIONAL else FAMILIES[dex][0]
        rows.append((dex, label, sum(1 for entry in entries if entry in index), len(entries)))
    return rows


def pixel_art(dex):
    """Vrai si le Pokédex affiche des sprites de jeu en pixel art (à agrandir sans lissage) ;
    les familles récentes n'ont que des sprites HOME, en haute résolution."""
    return dex != NATIONAL and GAMES[FAMILIES[dex][1][-1]][2] is not None


def build(shinies, dex):
    """Sections à afficher : cases (n° régional, n° national, nom, nb de shiny, sprites).

    Sprites : HOME pour le Pokédex national. Pour un Pokédex de famille, le sprite du shiny
    capturé (son jeu, sa forme, son genre) ou, s'il manque, celui du jeu le plus récent
    de la famille (Cristal, Émeraude, Platine…), avec repli sur HOME.
    """
    # Premier shiny capturé (par date) en tête : c'est son sprite qui s'affiche
    index = _index(sorted(_in_scope(shinies, dex), key=lambda s: (s["caught_on"] or "9999", s["id"])))
    game = "home" if dex == NATIONAL else FAMILIES[dex][1][-1]

    def cell(number, species, form):
        found = index.get((species, form), [])
        if found and dex != NATIONAL:
            sprites = found[0]["sprites"]
        else:
            sprites = sprite_candidates(species, game, None, form)
        return {
            "number": number,
            "species_id": species,
            "form": form,
            "name": display_name(species, form),
            "count": len(found),
            "sprites": sprites,
        }

    sections = []
    for section in _sections(dex):
        cells = [cell(*entry) for entry in section["entries"]]
        sections.append({
            "name": section["name"],
            "cells": cells,
            "caught": sum(1 for c in cells if c["count"]),
        })
    return sections
