"""Données de référence : Pokédex, jeux, méthodes d'obtention et sprites."""
import json
import os
import re
import unicodedata

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPRITES = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon"
HOME = "other/home/shiny"

with open(os.path.join(BASE_DIR, "data", "pokedex_fr.json"), encoding="utf-8") as f:
    POKEDEX = {int(k): v for k, v in json.load(f).items()}
NAME_TO_ID = {name.lower(): dex for dex, name in POKEDEX.items()}


def species_key(text):
    """Clé de comparaison d'un nom (Pokémon, méthode…) : sans accents, casse, espaces ni ponctuation (« Mr. Mime » = « mrmime »)."""
    text = unicodedata.normalize("NFD", text.lower().replace("♀", "f").replace("♂", "m"))
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in text if unicodedata.category(c) != "Mn"))


SPECIES_BY_KEY = {species_key(name): dex for dex, name in POKEDEX.items()}


def find_species(text):
    """N° de Pokédex d'après le nom (« evoli » trouve Évoli) ou le numéro (« 25 », « #025 ») ; None sinon."""
    text = text.strip()
    number = text.lstrip("#").strip()
    if number.isascii() and number.isdigit():
        return int(number) if int(number) in POKEDEX else None
    return NAME_TO_ID.get(text.lower()) or SPECIES_BY_KEY.get(species_key(text))

# Formes alternatives capturables (régionales, cosmétiques, de genre…), hors formes de combat.
# n° -> {"default": nom de la forme par défaut, "forms": {clé: {name, full, sprite}}}
# « sprite » est le nom du fichier chez PokeAPI : id du Pokémon (ex. 10091) ou « n°-clé » (ex. 201-b).
with open(os.path.join(BASE_DIR, "data", "forms_fr.json"), encoding="utf-8") as f:
    FORMS = {int(k): v for k, v in json.load(f).items()}


def forms_of(dex):
    return FORMS.get(dex, {}).get("forms", {})


def display_name(dex, form=None):
    """Nom complet affiché : « Rattata d’Alola », « Zarbi B », ou simplement « Rattata »."""
    info = forms_of(dex).get(form)
    return info["full"] if info else POKEDEX.get(dex, f"#{dex}")

# clé -> (libellé, génération, dossier de sprites shiny ; None = sprites HOME)
GAMES = {
    "or":        ("Or", 2, "versions/generation-ii/gold/shiny"),
    "argent":    ("Argent", 2, "versions/generation-ii/silver/shiny"),
    "cristal":   ("Cristal", 2, "versions/generation-ii/crystal/shiny"),
    "rs":        ("Rubis / Saphir", 3, "versions/generation-iii/ruby-sapphire/shiny"),
    "emeraude":  ("Émeraude", 3, "versions/generation-iii/emerald/shiny"),
    "rfvf":      ("Rouge Feu / Vert Feuille", 3, "versions/generation-iii/firered-leafgreen/shiny"),
    # Jeux console : pas de sprites dédiés, on reprend ceux du jeu portable de la même génération
    "colosseum": ("Pokémon Colosseum", 3, "versions/generation-iii/emerald/shiny"),
    "xd":        ("Pokémon XD : Le Souffle des Ténèbres", 3, "versions/generation-iii/emerald/shiny"),
    "dp":        ("Diamant / Perle", 4, "versions/generation-iv/diamond-pearl/shiny"),
    "platine":   ("Platine", 4, "versions/generation-iv/platinum/shiny"),
    "pbr":       ("Pokémon Battle Revolution", 4, "versions/generation-iv/platinum/shiny"),
    "hgss":      ("HeartGold / SoulSilver", 4, "versions/generation-iv/heartgold-soulsilver/shiny"),
    "rumble":    ("Pokémon Rumble", 4, None),
    "nb":        ("Noir / Blanc", 5, "versions/generation-v/black-white/animated/shiny"),
    "nb2":       ("Noir 2 / Blanc 2", 5, "versions/generation-v/black-white/animated/shiny"),
    "xy":        ("X / Y", 6, "versions/generation-vi/x-y/shiny"),
    "rosa":      ("Rubis Oméga / Saphir Alpha", 6, "versions/generation-vi/omegaruby-alphasapphire/shiny"),
    "sl":        ("Soleil / Lune", 7, None),
    "usul":      ("Ultra-Soleil / Ultra-Lune", 7, None),
    "lgpe":      ("Let's Go Pikachu / Évoli", 7, None),
    "epee_bouclier": ("Épée / Bouclier", 8, None),
    "deps":      ("Diamant Étincelant / Perle Scintillante", 8, None),
    "lpa":       ("Légendes Pokémon : Arceus", 8, None),
    "ev":        ("Écarlate / Violet", 9, None),
    "lza":       ("Légendes Pokémon : Z-A", 9, None),
    "home":      ("Pokémon HOME", 0, None),
    # Jeux non officiels (collections séparées, voir COLLECTIONS) : sprites HOME
    "pixelmonworld": ("PixelmonWorld", 0, None),
    "cobblemon": ("Cobblemon", 0, None),
}

# Familles de jeux, dans l'ordre d'affichage : clé -> (libellé, jeux de GAMES)
FAMILIES = {
    "oac":    ("Or / Argent / Cristal", ["or", "argent", "cristal"]),
    "rse":    ("Rubis / Saphir / Émeraude", ["rs", "emeraude"]),
    "rfvf":   ("Rouge Feu / Vert Feuille", ["rfvf"]),
    "colosseum": ("Pokémon Colosseum", ["colosseum"]),
    "xd":     ("Pokémon XD : Le Souffle des Ténèbres", ["xd"]),
    "dpp":    ("Diamant / Perle / Platine", ["dp", "platine"]),
    "pbr":    ("Pokémon Battle Revolution", ["pbr"]),
    "hgss":   ("HeartGold / SoulSilver", ["hgss"]),
    "rumble": ("Pokémon Rumble", ["rumble"]),
    "nb":     ("Noir / Blanc / Noir 2 / Blanc 2", ["nb", "nb2"]),
    "xy":     ("X / Y", ["xy"]),
    "rosa":   ("Rubis Oméga / Saphir Alpha", ["rosa"]),
    "slusul": ("Soleil / Lune / Ultra-Soleil / Ultra-Lune", ["sl", "usul"]),
    "lgpe":   ("Let's Go Pikachu / Évoli", ["lgpe"]),
    "epee_bouclier": ("Épée / Bouclier", ["epee_bouclier"]),
    "deps":   ("Diamant Étincelant / Perle Scintillante", ["deps"]),
    "lpa":    ("Légendes Pokémon : Arceus", ["lpa"]),
    "ev":     ("Écarlate / Violet", ["ev"]),
    "lza":    ("Légendes Pokémon : Z-A", ["lza"]),
    "home":   ("Pokémon HOME", ["home"]),
    "pixelmonworld": ("PixelmonWorld", ["pixelmonworld"]),
    "cobblemon": ("Cobblemon", ["cobblemon"]),
}
GAME_FAMILY = {game: fam for fam, (_, games) in FAMILIES.items() for game in games}
assert GAME_FAMILY.keys() == GAMES.keys(), "chaque jeu doit appartenir à une seule famille"

# Collections indépendantes d'un même compte : clé -> (libellé, jeux ; None = tous les autres jeux).
# Chacune a sa page, ses filtres, ses statistiques et son Shinydex (national seulement hors principale).
MAIN_COLLECTION = "principale"
COLLECTIONS = {
    MAIN_COLLECTION: ("Jeux officiels", None),
    "pixelmonworld": ("PixelmonWorld", ["pixelmonworld"]),
    "cobblemon": ("Cobblemon", ["cobblemon"]),
}
SEPARATE_GAMES = {game: key for key, (_, games) in COLLECTIONS.items() if games for game in games}
MAIN_FAMILIES = [key for key, (_, games) in FAMILIES.items() if not set(games) & SEPARATE_GAMES.keys()]


def collection_of(game):
    """Collection à laquelle appartient un jeu."""
    return SEPARATE_GAMES.get(game, MAIN_COLLECTION)

# Suggestions proposées dans le formulaire (la saisie reste libre)
# clé -> (libellé, icône dans sprites/items ; None = pas d'icône disponible)
BALLS = {
    "poke-ball":     ("Poké Ball", "poke-ball"),
    "great-ball":    ("Super Ball", "great-ball"),
    "ultra-ball":    ("Hyper Ball", "ultra-ball"),
    "master-ball":   ("Master Ball", "master-ball"),
    "premier-ball":  ("Honor Ball", "premier-ball"),
    "safari-ball":   ("Safari Ball", "safari-ball"),
    "sport-ball":    ("Compét'Ball", "sport-ball"),
    "level-ball":    ("Niveau Ball", "level-ball"),
    "lure-ball":     ("Appât Ball", "lure-ball"),
    "moon-ball":     ("Lune Ball", "moon-ball"),
    "friend-ball":   ("Copain Ball", "friend-ball"),
    "love-ball":     ("Love Ball", "love-ball"),
    "heavy-ball":    ("Masse Ball", "heavy-ball"),
    "fast-ball":     ("Speed Ball", "fast-ball"),
    "repeat-ball":   ("Bis Ball", "repeat-ball"),
    "timer-ball":    ("Chrono Ball", "timer-ball"),
    "nest-ball":     ("Faiblo Ball", "nest-ball"),
    "net-ball":      ("Filet Ball", "net-ball"),
    "dive-ball":     ("Scuba Ball", "dive-ball"),
    "luxury-ball":   ("Luxe Ball", "luxury-ball"),
    "heal-ball":     ("Soin Ball", "heal-ball"),
    "quick-ball":    ("Rapide Ball", "quick-ball"),
    "dusk-ball":     ("Sombre Ball", "dusk-ball"),
    "cherish-ball":  ("Mémoire Ball", "cherish-ball"),
    "park-ball":     ("Parc Ball", "park-ball"),
    "dream-ball":    ("Rêve Ball", "dream-ball"),
    "beast-ball":    ("Ultra Ball", "beast-ball"),
    "strange-ball":  ("Étrange Ball", "lastrange-ball"),
    "hisui-poke-ball":  ("Poké Ball (Hisui)", None),
    "hisui-great-ball": ("Super Ball (Hisui)", None),
    "hisui-ultra-ball": ("Hyper Ball (Hisui)", None),
    "hisui-heavy-ball": ("Masse Ball (Hisui)", None),
    "leaden-ball":   ("Mégamasse Ball", None),
    "gigaton-ball":  ("Gigamasse Ball", None),
    "feather-ball":  ("Plume Ball", None),
    "wing-ball":     ("Aile Ball", None),
    "jet-ball":      ("Jet Ball", None),
    "origin-ball":   ("Origine Ball", None),
}

ITEM_SPRITES = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items"


def ball_icon(ball):
    icon = BALLS.get(ball, (None, None))[1]
    return f"{ITEM_SPRITES}/{icon}.png" if icon else None


GENDERS = {"M": "♂ Mâle", "F": "♀ Femelle", "N": "⚲ Asexué"}

EXT = {"versions/generation-v/black-white/animated/shiny": "gif"}


LOCAL_SPRITES_DIR = os.path.join(BASE_DIR, "static", "sprites")
LOCAL_EXTENSIONS = ("png", "gif", "webp", "jpg")
LOCAL_NAME_RE = re.compile(r"\d{1,4}(-[a-z0-9]+)*")  # « 25 », « 25-f », « 19-alola-f »


def local_sprite(game, name):
    """URL d'un sprite déposé dans static/sprites/<jeu>/<name>.<ext>, ou None.

    Lu à chaque affichage : un fichier ajouté est pris en compte sans redémarrer.
    """
    # Clé de jeu et nom servent à construire un chemin : jamais de valeur arbitraire
    if game not in GAMES or not LOCAL_NAME_RE.fullmatch(name):
        return None
    for ext in LOCAL_EXTENSIONS:
        if os.path.isfile(os.path.join(LOCAL_SPRITES_DIR, game, f"{name}.{ext}")):
            return f"/static/sprites/{game}/{name}.{ext}"
    return None


def sprite_candidates(dex, game, gender, form=None):
    """URLs de sprites à essayer dans l'ordre (le navigateur passe à la suivante en cas d'erreur).

    Ordre : fichiers locaux (femelle puis standard), puis PokeAPI pour le jeu, puis HOME.
    Les sprites femelles n'existent que pour les espèces avec dimorphisme ;
    on les tente en premier puis on retombe sur le sprite standard.
    """
    _, gen, path = GAMES.get(game, (None, 0, None))
    folders = [path, HOME] if path else [HOME]
    form_info = forms_of(dex).get(form)

    # Les sprites déposés dans static/sprites/<jeu>/ passent avant ceux de PokeAPI
    local = f"{dex}-{form}" if form_info else str(dex)
    urls = []
    if gender == "F":
        urls += filter(None, [local_sprite(game, f"{local}-f")])
    urls += filter(None, [local_sprite(game, local)])

    # Sprite PokeAPI : id propre à la forme, sans variante femelle
    api_name = form_info["sprite"] if form_info else str(dex)
    for folder in folders:
        ext = EXT.get(folder, "png")
        # Pas de dimorphisme sexuel avant la 4e génération
        if gender == "F" and not form_info and (folder == HOME or gen >= 4):
            urls.append(f"{SPRITES}/{folder}/female/{api_name}.{ext}")
        urls.append(f"{SPRITES}/{folder}/{api_name}.{ext}")
    if form_info:
        urls.append(f"{SPRITES}/{HOME}/{dex}.png")  # dernier recours : forme de base
    return urls
