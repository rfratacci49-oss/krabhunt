"""Statistiques d'une collection, calculées sur les shiny enrichis par `to_view`."""
from collections import Counter
from datetime import date
from statistics import median

from duration import format_duration
from pokemon import BALLS, FAMILIES, GENDERS, POKEDEX, ball_icon

# Plages du Pokédex national par génération d'apparition des espèces
GENERATIONS = [
    (1, 1, 151), (2, 152, 251), (3, 252, 386), (4, 387, 493), (5, 494, 649),
    (6, 650, 721), (7, 722, 809), (8, 810, 905), (9, 906, 1025),
]
# Tranches de l'histogramme des rencontres : (borne basse incluse, borne haute exclue, libellé)
ENCOUNTER_BUCKETS = [
    (0, 100, "< 100"), (100, 500, "100 – 499"), (500, 1000, "500 – 999"),
    (1000, 3000, "1 000 – 2 999"), (3000, 6000, "3 000 – 5 999"),
    (6000, 10000, "6 000 – 9 999"), (10000, None, "10 000 et +"),
]
# Tranches de l'histogramme des temps de chasse, en secondes
DURATION_BUCKETS = [
    (0, 1800, "< 30 min"), (1800, 3600, "30 min – 1 h"), (3600, 7200, "1 – 2 h"),
    (7200, 18000, "2 – 5 h"), (18000, 36000, "5 – 10 h"), (36000, 72000, "10 – 20 h"),
    (72000, None, "20 h et +"),
]
TOP = 8  # au-delà, les catégories sont regroupées dans « Autres »

MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin",
          "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def fr_int(n):
    """1234567 -> « 1 234 567 »."""
    return f"{n:,}".replace(",", " ")


def fr_date(iso):
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def _top(counter, labels=None, icons=None):
    """[(libellé, n, icône)] trié par n décroissant, la queue regroupée dans « Autres »."""
    items = counter.most_common()
    rows = [((labels or {}).get(k, k), n, (icons or {}).get(k)) for k, n in items[:TOP]]
    rest = sum(n for _, n in items[TOP:])
    if rest:
        rows.append((f"Autres ({len(items) - TOP})", rest, None))
    return rows


def _timeline(dates):
    """Captures par mois si l'historique tient sur 2 ans, sinon par année ; périodes vides incluses."""
    if not dates:
        return "année", []
    first, last = min(dates), max(dates)
    months = (last.year - first.year) * 12 + last.month - first.month + 1
    if months <= 24:
        counts = Counter((d.year, d.month) for d in dates)
        rows, y, m = [], first.year, first.month
        for _ in range(months):
            rows.append((f"{MONTHS[m - 1]} {y}", counts[(y, m)]))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return "mois", rows
    counts = Counter(d.year for d in dates)
    return "année", [(str(y), counts[y]) for y in range(first.year, last.year + 1)]


def _histogram(values, buckets):
    """[(libellé, n)] par tranche ; les tranches vides en fin d'échelle sont retirées
    (mais pas au milieu : l'échelle reste lisible)."""
    rows = [
        (label, sum(1 for v in values if v >= low and (high is None or v < high)))
        for low, high, label in buckets
    ]
    while rows and rows[-1][1] == 0:
        rows.pop()
    return rows


def compute(shinies):
    total = len(shinies)
    with_enc = [s for s in shinies if s["encounters"] is not None]
    encounters = [s["encounters"] for s in with_enc]
    with_time = [s for s in shinies if s["duration"] is not None]
    durations = [s["duration"] for s in with_time]
    dated = [s for s in shinies if s["caught_on"]]
    dates = [date.fromisoformat(s["caught_on"]) for s in dated]
    species = {s["species_id"] for s in shinies}
    targets = [s for s in shinies if s["phases"]]
    phases = [s for s in shinies if s["phase_number"]]

    granularity, timeline = _timeline(dates)

    family_counts = Counter(s["family"] for s in shinies)
    by_family = [(label, family_counts[k]) for k, (label, _) in FAMILIES.items() if family_counts[k]]

    gender_counts = Counter(s["gender"] for s in shinies)
    gender = [(k, GENDERS[k], gender_counts[k]) for k in GENDERS if gender_counts[k]]

    buckets = _histogram(encounters, ENCOUNTER_BUCKETS)
    duration_buckets = _histogram(durations, DURATION_BUCKETS)

    pokedex = [
        (gen, len([d for d in species if low <= d <= high]), high - low + 1)
        for gen, low, high in GENERATIONS
    ]

    species_counts = Counter(s["species_id"] for s in shinies)
    top_species = [
        (POKEDEX.get(dex, f"#{dex}"), n, next(s for s in shinies if s["species_id"] == dex))
        for dex, n in species_counts.most_common(5) if n > 1
    ]

    records = []
    if with_enc:
        longest = max(with_enc, key=lambda s: s["encounters"])
        quickest = min(with_enc, key=lambda s: s["encounters"])
        records.append(("Chasse la plus longue (rencontres)", longest, f"{fr_int(longest['encounters'])} rencontres"))
        if quickest is not longest:
            records.append(("Le plus rapide (rencontres)", quickest, f"{fr_int(quickest['encounters'])} rencontres"))
    if with_time:
        longest = max(with_time, key=lambda s: s["duration"])
        quickest = min(with_time, key=lambda s: s["duration"])
        records.append(("Chasse la plus longue (temps)", longest, format_duration(longest["duration"])))
        if quickest is not longest:
            records.append(("Le plus rapide (temps)", quickest, format_duration(quickest["duration"])))
    if targets:
        biggest = max(targets, key=lambda s: len(s["phases"]))
        records.append(("Le plus de phases", biggest, f"phase finale après {len(biggest['phases'])} phase"
                        + ("s" if len(biggest["phases"]) > 1 else "")))
    if dated:
        first = min(dated, key=lambda s: (s["caught_on"], s["id"]))
        last = max(dated, key=lambda s: (s["caught_on"], s["id"]))
        records.append(("Premier shiny", first, fr_date(first["caught_on"])))
        if last is not first:
            records.append(("Dernier shiny", last, fr_date(last["caught_on"])))

    return {
        "total": total,
        "species": len(species),
        "species_total": len(POKEDEX),
        "encounters_total": sum(encounters),
        "encounters_known": len(with_enc),
        "encounters_avg": round(sum(encounters) / len(encounters)) if encounters else None,
        "encounters_median": round(median(encounters)) if encounters else None,
        "duration_total": sum(durations),
        "duration_known": len(with_time),
        "duration_avg": round(sum(durations) / len(durations)) if durations else None,
        "duration_median": round(median(durations)) if durations else None,
        "duration_buckets": duration_buckets,
        "hunts_with_phases": len(targets),
        "phases": len(phases),
        "undated": total - len(dated),
        "granularity": granularity,
        "timeline": timeline,
        "by_family": by_family,
        "by_method": _top(Counter(s["method"] for s in shinies)),
        "by_ball": _top(
            Counter(s["ball"] for s in shinies if s["ball"]),
            labels={k: label for k, (label, _) in BALLS.items()},
            icons={k: ball_icon(k) for k in BALLS},
        ),
        "no_ball": sum(1 for s in shinies if not s["ball"]),
        "gender": gender,
        "buckets": buckets,
        "pokedex": pokedex,
        "top_species": top_species,
        "records": records,
    }
