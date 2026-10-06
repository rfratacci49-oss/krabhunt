"""Filtres et tris de la page collection.

Ils s'appliquent en Python sur les shiny déjà enrichis par `to_view` (une collection
tient en mémoire sans difficulté), ce qui permet de filtrer sur des valeurs calculées :
nom de forme, statut de phase, génération…
"""
import unicodedata
from collections import Counter

from pokemon import BALLS, FAMILIES, GAMES, GENDERS

PHASE_STATUSES = {
    "cible": "Phase finale (avec phases)",
    "phase": "Phase d'une chasse",
    "seul": "Sans phase",
}
FORM_STATUSES = {"base": "Forme de base", "alt": "Forme alternative"}
CHARM_STATUSES = {"oui": "Avec charme chroma", "non": "Sans charme chroma"}
NO_VALUE = "aucun"  # valeur du filtre pour « sans date », « sans Ball »…


def _date_key(s):
    return s["caught_on"] or ""


def _encounters_key(s):
    return s["encounters"] if s["encounters"] is not None else -1


SORTS = {
    "date_desc": ("Date (récent → ancien)", lambda s: (_date_key(s), s["id"]), True),
    "date_asc": ("Date (ancien → récent)", lambda s: (_date_key(s) or "9999", s["id"]), False),
    "ajout": ("Derniers ajoutés", lambda s: s["id"], True),
    "rencontres_desc": ("Rencontres (plus → moins)", _encounters_key, True),
    "rencontres_asc": ("Rencontres (moins → plus)",
                       lambda s: s["encounters"] if s["encounters"] is not None else float("inf"), False),
    "temps_desc": ("Temps de chasse (long → court)",
                   lambda s: s["duration"] if s["duration"] is not None else -1, True),
    "temps_asc": ("Temps de chasse (court → long)",
                  lambda s: s["duration"] if s["duration"] is not None else float("inf"), False),
    "dex": ("N° de Pokédex", lambda s: (s["species_id"], s["form"] or ""), False),
    "nom": ("Nom (A → Z)", lambda s: normalize(s["name"]), False),
}
DEFAULT_SORT = "date_desc"

# Rangement de la page : sections par famille de jeux, par année de capture, ou liste unique
GROUPINGS = {
    "jeu": "Par jeu",
    "date": "Par date de capture",
    "aucun": "Liste unique",
}
DEFAULT_GROUPING = "jeu"
GROUPING_ALIASES = {"1": "jeu", "0": "aucun"}  # anciens liens (?groupe=1 / ?groupe=0)


def normalize(text):
    """Minuscules sans accents, pour une recherche tolérante (« eveli » trouve « Évoli »)."""
    text = unicodedata.normalize("NFD", str(text).lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn").replace("’", "'")


def phase_status(s):
    if s["phase_number"]:
        return "phase"
    return "cible" if s["phases"] else "seul"


def generation(s):
    return GAMES.get(s["game"], (None, 0))[1]


def _matches_text(s, query):
    """Chaque mot doit apparaître dans le nom, surnom, méthode, lieu, note ou jeu ;
    un nombre (« 19 » ou « #19 ») désigne exactement un n° de Pokédex."""
    haystack = normalize(" ".join(filter(None, [
        s["species"], s["nickname"], s["method"], s["location"], s["notes"], s["game_label"],
    ])))
    for word in normalize(query).split():
        number = word.lstrip("#")
        if number.isascii() and number.isdigit():
            if int(number) != s["species_id"]:
                return False
        elif word not in haystack:
            return False
    return True


def _in_range(value, low, high):
    if low is None and high is None:
        return True
    if value is None:
        return False
    return (low is None or value >= low) and (high is None or value <= high)


def _int_arg(args, key):
    value = args.get(key, "").strip()
    return int(value) if value.isascii() and value.isdigit() else None


def parse_grouping(value):
    """Clé de GROUPINGS d'après la valeur de l'URL, ou None si absente ou inconnue."""
    value = GROUPING_ALIASES.get(value, value)
    return value if value in GROUPINGS else None


def parse(args, default_grouping=DEFAULT_GROUPING):
    """Lit les filtres de l'URL ; les valeurs inconnues sont ignorées."""
    family = args.get("jeu", "")
    family = next((k for k, (_, games) in FAMILIES.items() if family in games), family)
    gen = _int_arg(args, "gen")
    filters = {
        "q": args.get("q", "").strip(),
        "jeu": family if family in FAMILIES else "",
        "gen": gen if gen is not None and gen in {g for _, g, _ in GAMES.values()} else None,
        "methode": args.get("methode", "").strip(),
        "ball": args.get("ball", "") if args.get("ball", "") in BALLS or args.get("ball") == NO_VALUE else "",
        "charme": args.get("charme", "") if args.get("charme", "") in CHARM_STATUSES else "",
        "genre": args.get("genre", "") if args.get("genre", "") in GENDERS else "",
        "phase": args.get("phase", "") if args.get("phase", "") in PHASE_STATUSES else "",
        "forme": args.get("forme", "") if args.get("forme", "") in FORM_STATUSES else "",
        "annee": args.get("annee", "").strip(),
        "min": _int_arg(args, "min"),
        "max": _int_arg(args, "max"),
        "tri": args.get("tri", "") if args.get("tri", "") in SORTS else DEFAULT_SORT,
        "groupe": parse_grouping(args.get("groupe", "")) or default_grouping,
    }
    return filters


def active_count(filters):
    """Nombre de filtres actifs (hors tri et regroupement)."""
    return sum(
        1 for k, v in filters.items()
        if k not in ("tri", "groupe") and v not in ("", None)
    )


def apply(shinies, f):
    """Filtre puis trie la liste (rangement par date : toujours dans l'ordre chronologique)."""
    def keep(s):
        if f["q"] and not _matches_text(s, f["q"]):
            return False
        if f["jeu"] and s["family"] != f["jeu"]:
            return False
        if f["gen"] is not None and generation(s) != f["gen"]:
            return False
        if f["methode"] and s["method"] != f["methode"]:
            return False
        if f["ball"] and (s["ball"] or NO_VALUE) != f["ball"]:
            return False
        if f["charme"] and ("oui" if s["shiny_charm"] else "non") != f["charme"]:
            return False
        if f["genre"] and s["gender"] != f["genre"]:
            return False
        if f["phase"] and phase_status(s) != f["phase"]:
            return False
        if f["forme"] and ("alt" if s["form"] else "base") != f["forme"]:
            return False
        if f["annee"] and ((s["caught_on"] or "")[:4] or NO_VALUE) != f["annee"]:
            return False
        return _in_range(s["encounters"], f["min"], f["max"])

    sort = f["tri"]
    if f["groupe"] == "date" and sort != "date_asc":
        sort = "date_desc"
    _, key, reverse = SORTS[sort]
    return sorted(filter(keep, shinies), key=key, reverse=reverse)


def group(shinies, f):
    """Sections [(titre ou None, shiny)] selon le rangement choisi ; l'ordre de `shinies` est gardé dans chaque section."""
    if f["groupe"] == "jeu":
        by_family = {key: [] for key in FAMILIES}
        for s in shinies:
            by_family[s["family"]].append(s)
        return [(FAMILIES[key][0], items) for key, items in by_family.items() if items]
    if f["groupe"] == "date":
        by_year = {}  # dans l'ordre de la liste triée par date : années déjà dans le bon ordre
        for s in shinies:
            by_year.setdefault((s["caught_on"] or "")[:4] or "Sans date", []).append(s)
        return list(by_year.items())
    return [(None, shinies)] if shinies else []


def options(shinies):
    """Valeurs proposées dans chaque filtre, limitées à celles présentes dans la collection."""
    def counted(values):
        return Counter(values)

    families = counted(s["family"] for s in shinies)
    gens = counted(generation(s) for s in shinies)
    years = counted((s["caught_on"] or "")[:4] or NO_VALUE for s in shinies)
    return {
        "especes": sorted({s["species"] for s in shinies}, key=normalize),
        "jeu": [(k, label, families[k]) for k, (label, _) in FAMILIES.items() if families[k]],
        "gen": [(g, f"{g}e génération" if g else "Hors génération (HOME, jeux non officiels)", n)
                for g, n in sorted(gens.items())],
        "methode": sorted(counted(s["method"] for s in shinies).items(), key=lambda kv: normalize(kv[0])),
        "ball": [(k, label, n) for k, (label, _) in BALLS.items()
                 if (n := sum(1 for s in shinies if s["ball"] == k))]
                + ([(NO_VALUE, "Sans Ball renseignée", n)]
                   if (n := sum(1 for s in shinies if not s["ball"])) else []),
        "charme": [(k, label, n) for k, label in CHARM_STATUSES.items()
                   if (n := sum(1 for s in shinies if ("oui" if s["shiny_charm"] else "non") == k))],
        "genre": [(k, label, n) for k, label in GENDERS.items()
                  if (n := sum(1 for s in shinies if s["gender"] == k))],
        "phase": [(k, label, n) for k, label in PHASE_STATUSES.items()
                  if (n := sum(1 for s in shinies if phase_status(s) == k))],
        "forme": [(k, label, n) for k, label in FORM_STATUSES.items()
                  if (n := sum(1 for s in shinies if ("alt" if s["form"] else "base") == k))],
        "annee": [(y, "Sans date" if y == NO_VALUE else y, n)
                  # années récentes d'abord, « Sans date » à la fin
                  for y, n in sorted(years.items(), key=lambda kv: (kv[0] != NO_VALUE, kv[0]), reverse=True)],
    }
