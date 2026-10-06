import os
import re
import secrets
import sqlite3
import time
from datetime import date
from functools import wraps

import click
from duration import clock, format_duration, parse_duration
from flask import (
    Flask, Response, abort, flash, g, redirect, render_template, request, send_file, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import export
import filters
import importer
import methods
import shinydex
import stats
from pokemon import (
    BALLS, COLLECTIONS, FAMILIES, FORMS, GAME_FAMILY, GAMES, GENDERS, MAIN_COLLECTION, POKEDEX,
    SEPARATE_GAMES, collection_of,
    ball_icon, display_name, find_species, forms_of, sprite_candidates,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me"),
    DATABASE=os.environ.get("DATABASE", os.path.join(BASE_DIR, "krabhunt.db")),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=4 * 1024 * 1024,  # import CSV : 4 Mo max
)


# --- Base de données -------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")  # suppression en cascade des phases
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# Colonnes ajoutées après la création initiale des tables
MIGRATIONS = {
    "users": {
        "stream_token": "TEXT",  # adresse secrète du mode stream (OBS) ; index unique dans init_db
        "api_token": "TEXT",     # clé des raccourcis globaux (modifie les compteurs) ; index unique
    },
    "shinies": {
        "encounters": "INTEGER CHECK (encounters >= 0)",
        "ball": "TEXT",
        "notes": "TEXT",
        "user_id": "INTEGER REFERENCES users(id)",
        "form": "TEXT",
        "location": "TEXT",
        "shiny_charm": "INTEGER NOT NULL DEFAULT 0 CHECK (shiny_charm IN (0, 1))",
        "duration": "INTEGER CHECK (duration >= 0)",
    },
    "hunts": {
        "form": "TEXT",
        "location": "TEXT",
        "shiny_charm": "INTEGER NOT NULL DEFAULT 0 CHECK (shiny_charm IN (0, 1))",
        "mode": "TEXT NOT NULL DEFAULT 'count' CHECK (mode IN ('count', 'timer'))",
        "elapsed": "INTEGER NOT NULL DEFAULT 0 CHECK (elapsed >= 0)",
        "started_at": "INTEGER",
        "last_tick": "INTEGER",
    },
}

NOTE_LOCATION_RE = re.compile(r"^Lieu : (.*)\n?", re.MULTILINE)
NOTE_CHARM_RE = re.compile(r"^Charme chroma : oui$\n?", re.MULTILINE)


def move_note_fields(db):
    """Lieu et charme chroma rangés dans la note par les anciens imports -> colonnes dédiées."""
    rows = db.execute(
        "SELECT id, notes FROM shinies WHERE notes LIKE '%Lieu : %' OR notes LIKE '%Charme chroma : oui%'"
    ).fetchall()
    for row in rows:
        notes = row["notes"]
        location = NOTE_LOCATION_RE.search(notes)
        charm = NOTE_CHARM_RE.search(notes) is not None
        notes = NOTE_CHARM_RE.sub("", NOTE_LOCATION_RE.sub("", notes)).strip()
        db.execute(
            """UPDATE shinies SET location = COALESCE(location, ?), shiny_charm = MAX(shiny_charm, ?),
               notes = ? WHERE id = ?""",
            ((location.group(1).strip() or None) if location else None, int(charm), notes or None, row["id"]),
        )


PHASE_TABLES = {"hunt_phases": "target_id", "hunt_pending_phases": "hunt_id"}


def migrate_phase_tables(db, schema):
    """Anciennes tables de phases (shiny uniquement) -> nouvelles (shiny ou shiny manqué), données gardées."""
    old = [t for t in PHASE_TABLES
           if db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (t,)).fetchone()
           and "fail_id" not in {r["name"] for r in db.execute(f"PRAGMA table_info({t})")}]
    if not old:
        return
    for table in old:
        db.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
    db.executescript(schema)  # recrée les tables au nouveau format
    for table in old:
        owner = PHASE_TABLES[table]
        db.execute(f"INSERT INTO {table} ({owner}, shiny_id, position) "
                   f"SELECT {owner}, shiny_id, position FROM {table}_old")
        db.execute(f"DROP TABLE {table}_old")


def init_db():
    """Crée les tables et colonnes manquantes (sans toucher aux données existantes)."""
    db = get_db()
    with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
        schema = f.read()
    db.executescript(schema)
    migrate_phase_tables(db, schema)
    added = set()
    for table, columns in MIGRATIONS.items():
        existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        for column, definition in columns.items():
            if column not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                added.add((table, column))
    if ("shinies", "shiny_charm") in added:
        move_note_fields(db)
    db.execute("CREATE INDEX IF NOT EXISTS idx_shinies_user ON shinies (user_id)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_stream_token ON users (stream_token)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_api_token ON users (api_token)")
    # Shiny créés avant l'arrivée des comptes multiples : rattachés au plus ancien compte
    db.execute(
        "UPDATE shinies SET user_id = (SELECT MIN(id) FROM users) WHERE user_id IS NULL"
    )
    # Ancienne table « phases » (phases saisies à la main) : supprimée si vide, sinon mise de côté
    if db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'phases'").fetchone():
        if db.execute("SELECT COUNT(*) FROM phases").fetchone()[0]:
            db.execute("ALTER TABLE phases RENAME TO phases_legacy")
        else:
            db.execute("DROP TABLE phases")
    db.commit()


with app.app_context():
    init_db()


@app.cli.command("reset-db")
@click.confirmation_option(prompt="Effacer TOUTES les données ?")
def reset_db_command():
    """Supprime puis recrée toutes les tables."""
    db = get_db()
    db.executescript(
        "DROP TABLE IF EXISTS fails; DROP TABLE IF EXISTS hunt_pending_phases; DROP TABLE IF EXISTS hunts; "
        "DROP TABLE IF EXISTS hunt_phases; DROP TABLE IF EXISTS shinies; "
        "DROP TABLE IF EXISTS users;"
    )
    init_db()
    click.echo("Base de données réinitialisée.")


# Le pseudo apparaît dans l'URL de la collection (/u/<pseudo>)
USERNAME_RE = re.compile(r"[A-Za-z0-9_-]{3,20}")


def find_user(username):
    return get_db().execute(
        "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
    ).fetchone()


def create_user(username, password):
    """Crée un compte ; renvoie (id, None) ou (None, message d'erreur)."""
    if not USERNAME_RE.fullmatch(username):
        return None, "Le pseudo doit faire 3 à 20 caractères : lettres, chiffres, _ ou -."
    if len(password) < 8:
        return None, "Le mot de passe doit faire au moins 8 caractères."
    if find_user(username):
        return None, "Ce pseudo est déjà pris."
    db = get_db()
    cur = db.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, generate_password_hash(password)),
    )
    db.commit()
    return cur.lastrowid, None


@app.cli.command("create-user")
@click.argument("username")
@click.password_option()
def create_user_command(username, password):
    """Crée un compte."""
    _, error = create_user(username, password)
    if error:
        click.echo(error, err=True)
    else:
        click.echo(f"Utilisateur « {username} » créé.")


# --- Authentification ------------------------------------------------------

@app.before_request
def load_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT id, username FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = find_user(username)

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Identifiants invalides.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            next_url = request.args.get("next", "")
            # N'accepte que des chemins internes pour éviter les redirections ouvertes
            if not next_url.startswith("/") or next_url.startswith("//"):
                next_url = url_for("collection", username=user["username"])
            return redirect(next_url)
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("collection", username=g.user["username"]))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if password != request.form.get("password_confirm", ""):
            error = "Les mots de passe ne correspondent pas."
        else:
            user_id, error = create_user(username, password)
        if error is None:
            session.clear()
            session["user_id"] = user_id
            flash(f"Bienvenue {username} ! Ajoutez votre premier shiny ✨", "success")
            return redirect(url_for("collection", username=username))
        flash(error, "error")
    return render_template("register.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Vous êtes déconnecté.", "success")
    return redirect(url_for("home"))


# --- Collection ------------------------------------------------------------

@app.template_filter("date_fr")
def date_fr(value):
    return date.fromisoformat(value).strftime("%d/%m/%Y") if value else ""


def to_view(row):
    """Enrichit une ligne de la BDD avec les infos d'affichage."""
    shiny = dict(row)
    shiny["species"] = display_name(row["species_id"], row["form"])
    shiny["game_label"] = GAMES.get(row["game"], (row["game"],))[0]
    shiny["family"] = GAME_FAMILY.get(row["game"], "home")
    shiny["gender_label"] = GENDERS[row["gender"]]
    shiny["ball_label"] = BALLS.get(row["ball"], (row["ball"],))[0] if row["ball"] else None
    shiny["ball_icon"] = ball_icon(row["ball"])
    shiny["odds"], _ = methods.odds(row["method"], row["game"], bool(row["shiny_charm"]))
    shiny["sprites"] = (
        [row["sprite_url"]] if row["sprite_url"]
        else sprite_candidates(row["species_id"], row["game"], row["gender"], row["form"])
    )
    shiny["name"] = row["nickname"] or shiny["species"]
    shiny["phases"] = []          # cible : noms de ses phases, dans l'ordre
    shiny["phase_number"] = None  # phase : son numéro dans la chasse
    shiny["phase_target"] = None  # phase : nom de la cible
    shiny["phase_target_id"] = None  # phase : id de la cible (chasse terminée)
    return shiny


def phase_key(row):
    """Clé d'une phase dans les formulaires : "12" (shiny n° 12) ou "f12" (shiny manqué n° 12)."""
    return f"f{row['fail_id']}" if row["fail_id"] else str(row["shiny_id"])


def phase_columns(key):
    """(shiny_id, fail_id) d'une clé de phase."""
    return (None, int(key[1:])) if key.startswith("f") else (int(key), None)


# Nom d'une phase (shiny ou manqué) dans les requêtes sur hunt_phases / hunt_pending_phases (alias p)
PHASE_NAME_JOIN = """LEFT JOIN shinies ps ON ps.id = p.shiny_id LEFT JOIN fails pf ON pf.id = p.fail_id"""
PHASE_NAME_COLUMNS = """COALESCE(ps.species_id, pf.species_id) AS phase_species, COALESCE(ps.form, pf.form) AS phase_form,
                        ps.nickname AS phase_nickname"""


def phase_name(row):
    name = row["phase_nickname"] or display_name(row["phase_species"], row["phase_form"])
    return f"{name} (manqué)" if row["fail_id"] else name


def attach_phases(shinies):
    """Renseigne les infos de phase des shiny donnés (une seule requête).

    Le numéro de phase est le rang dans la chasse (shiny manqués compris) : il se recalcule
    tout seul si une phase est supprimée.
    """
    by_id = {s["id"]: s for s in shinies}
    if not by_id:
        return
    placeholders = ",".join("?" * len(by_id))
    for row in get_db().execute(
        f"""SELECT p.target_id, p.shiny_id, p.fail_id, {PHASE_NAME_COLUMNS}
            FROM hunt_phases p {PHASE_NAME_JOIN}
            WHERE p.target_id IN ({placeholders}) ORDER BY p.target_id, p.position""",
        list(by_id),
    ):
        target = by_id[row["target_id"]]
        target["phases"].append(phase_name(row))
        phase = by_id.get(row["shiny_id"])
        if phase is None:
            continue
        phase["phase_number"] = len(target["phases"])
        phase["phase_target"] = target["name"]
        phase["phase_target_id"] = target["id"]

    # Phases d'une chasse encore en cours au compteur
    for row in get_db().execute(
        f"""SELECT p.shiny_id, h.species_id, h.form,
                   (SELECT COUNT(*) FROM hunt_pending_phases o
                    WHERE o.hunt_id = p.hunt_id AND o.position <= p.position) AS number
            FROM hunt_pending_phases p JOIN hunts h ON h.id = p.hunt_id
            WHERE p.shiny_id IN ({placeholders})""",
        list(by_id),
    ):
        phase = by_id[row["shiny_id"]]
        phase["phase_number"] = row["number"]
        phase["phase_target"] = f"{display_name(row['species_id'], row['form'])} (en cours)"


def get_own_shiny(shiny_id):
    """Shiny de l'utilisateur connecté (404 s'il n'existe pas ou appartient à un autre)."""
    row = get_db().execute(
        "SELECT * FROM shinies WHERE id = ? AND user_id = ?", (shiny_id, g.user["id"])
    ).fetchone()
    if row is None:
        abort(404)
    return row


def redirect_to_own_collection(game=None):
    """Vers la collection de l'utilisateur connecté (celle du jeu donné, sinon la principale)."""
    return redirect(url_for("collection", username=g.user["username"],
                            collection=collection_of(game) if game else MAIN_COLLECTION))


@app.route("/")
def home():
    db = get_db()
    hunters = {
        row["id"]: dict(row, total=0, others={}, preview=[])
        for row in db.execute("SELECT id, username FROM users")
    }
    # Total de la collection principale ; les collections séparées sont comptées à part
    for row in db.execute("SELECT user_id, game, COUNT(*) AS n FROM shinies GROUP BY user_id, game"):
        hunter = hunters.get(row["user_id"])
        if hunter is None:
            continue
        key = collection_of(row["game"])
        if key == MAIN_COLLECTION:
            hunter["total"] += row["n"]
        else:
            hunter["others"][key] = hunter["others"].get(key, 0) + row["n"]
    for hunter in hunters.values():
        hunter["others"] = [(key, COLLECTIONS[key][0], hunter["others"][key])
                            for key in COLLECTIONS if key in hunter["others"]]
    # Les 5 derniers shiny de la collection principale de chaque chasseur, en aperçu
    separate = list(SEPARATE_GAMES)
    for row in db.execute(
        f"""SELECT * FROM (
               SELECT s.*, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY id DESC) AS rank
               FROM shinies s WHERE game NOT IN ({",".join("?" * len(separate))})
           ) WHERE rank <= 5""",
        separate,
    ):
        if row["user_id"] in hunters:
            hunters[row["user_id"]]["preview"].append(to_view(row))
    ranked = sorted(hunters.values(), key=lambda h: (-h["total"], h["username"].lower()))
    return render_template("home.html", hunters=ranked)


def load_collection(owner, collection=MAIN_COLLECTION):
    """Les shiny d'une collection d'un compte, enrichis pour l'affichage avec leurs infos de phase."""
    shinies = [
        to_view(row)
        for row in get_db().execute("SELECT * FROM shinies WHERE user_id = ?", (owner["id"],))
        if collection_of(row["game"]) == collection
    ]
    attach_phases(shinies)  # avant tout filtre : les numéros de phase restent justes
    return shinies


def collection_context(owner, collection):
    """Variables communes aux pages d'une collection : onglets des collections avec leur nombre de shiny."""
    counts = dict.fromkeys(COLLECTIONS, 0)
    for row in get_db().execute(
        "SELECT game, COUNT(*) AS n FROM shinies WHERE user_id = ? GROUP BY game", (owner["id"],)
    ):
        counts[collection_of(row["game"])] += row["n"]
    is_owner = g.user is not None and g.user["id"] == owner["id"]
    fails = sum(1 for row in get_db().execute("SELECT game FROM fails WHERE user_id = ?", (owner["id"],))
                if collection_of(row["game"]) == collection)
    return {
        "owner": owner,
        "is_owner": is_owner,
        "fails_count": fails,
        "coll": collection,
        "coll_label": COLLECTIONS[collection][0],
        # Onglets : toujours pour le propriétaire, sinon seulement les collections non vides
        "collections": [(key, label, counts[key]) for key, (label, _) in COLLECTIONS.items()
                        if is_owner or counts[key] or key == collection],
    }


def find_owner(username, endpoint, collection):
    """(compte, None) ou (None, réponse) : 404 si inconnu, redirection vers la casse exacte du pseudo."""
    owner = find_user(username)
    if owner is None:
        abort(404)
    if owner["username"] != username:
        return None, redirect(url_for(endpoint, username=owner["username"], collection=collection,
                                      **request.args))
    return owner, None


# Collections séparées : /u/<pseudo>/<collection>/… ; la principale reste à /u/<pseudo>/…
SEPARATE = "<any(" + ", ".join(k for k in COLLECTIONS if k != MAIN_COLLECTION) + "):collection>"
MAIN = {"collection": MAIN_COLLECTION}


@app.route("/u/<username>", defaults=MAIN)
@app.route(f"/u/<username>/{SEPARATE}")
def collection(username, collection):
    owner, response = find_owner(username, "collection", collection)
    if response:
        return response

    everything = load_collection(owner, collection)

    # Le dernier rangement choisi est retenu pour les visites suivantes
    grouping = filters.parse_grouping(request.args.get("groupe", ""))
    if grouping:
        session["groupe"] = grouping
    current = filters.parse(request.args, session.get("groupe", filters.DEFAULT_GROUPING))
    shown = filters.apply(everything, current)
    sections = filters.group(shown, current)

    return render_template(
        "collection.html",
        **collection_context(owner, collection),
        sections=sections,
        total=len(everything),
        shown=len(shown),
        f=current,
        active=filters.active_count(current),
        options=filters.options(everything),
        sorts={k: label for k, (label, _, _) in filters.SORTS.items()},
        groupings=filters.GROUPINGS,
    )


@app.route("/u/<username>/stats", defaults=MAIN)
@app.route(f"/u/<username>/{SEPARATE}/stats")
def collection_stats(username, collection):
    owner, response = find_owner(username, "collection_stats", collection)
    if response:
        return response
    return render_template(
        "stats.html",
        **collection_context(owner, collection),
        s=stats.compute(load_collection(owner, collection)),
    )


@app.route("/u/<username>/shinydex", defaults=MAIN)
@app.route(f"/u/<username>/{SEPARATE}/shinydex")
def collection_shinydex(username, collection):
    owner, response = find_owner(username, "collection_shinydex", collection)
    if response:
        return response
    dex = request.args.get("dex", shinydex.NATIONAL)
    dex = GAME_FAMILY.get(dex, dex) if dex not in FAMILIES else dex  # ancien lien vers un jeu (ex. nb2)
    if dex not in shinydex.dexes(collection):
        dex = shinydex.NATIONAL
    shinies = load_collection(owner, collection)
    progress = shinydex.progress(shinies, collection)
    return render_template(
        "shinydex.html",
        **collection_context(owner, collection),
        dex=dex,
        current=next(row for row in progress if row[0] == dex),
        progress=progress,
        sections=shinydex.build(shinies, dex),
        problems=shinydex.problems() if collection == MAIN_COLLECTION else [],
        pixel=shinydex.pixel_art(dex),
    )


FAIL_REASONS = ["Fuite", "K.O. par erreur", "Capture ratée (plus de Balls…)", "Auto-destruction / Explosion",
                "Coupure / plantage du jeu", "Mauvaise manipulation", "Pas vu à temps"]


def fail_view(row):
    f = dict(row)
    f["species"] = display_name(row["species_id"], row["form"])
    f["game_label"] = GAMES.get(row["game"], (row["game"],))[0]
    f["gender_label"] = GENDERS.get(row["gender"]) if row["gender"] else None
    f["sprites"] = sprite_candidates(row["species_id"], row["game"], row["gender"], row["form"])
    f["odds"], _ = methods.odds(row["method"], row["game"], bool(row["shiny_charm"]))
    return f


def attach_fail_phases(fails):
    """Numéro de phase et cible des shiny manqués qui sont des phases (chasse terminée ou en cours)."""
    by_id = {f["id"]: f for f in fails}
    for f in fails:
        f["phase_number"] = f["phase_target"] = f["phase_target_id"] = None
    if not by_id:
        return
    placeholders = ",".join("?" * len(by_id))
    db = get_db()
    for row in db.execute(
        f"""SELECT p.fail_id, p.target_id,
                   (SELECT COUNT(*) FROM hunt_phases o WHERE o.target_id = p.target_id
                    AND o.position <= p.position) AS number
            FROM hunt_phases p WHERE p.fail_id IN ({placeholders})""", list(by_id)):
        target = to_view(db.execute("SELECT * FROM shinies WHERE id = ?", (row["target_id"],)).fetchone())
        f = by_id[row["fail_id"]]
        f["phase_number"], f["phase_target"], f["phase_target_id"] = row["number"], target["name"], target["id"]
    for row in db.execute(
        f"""SELECT p.fail_id, h.species_id, h.form,
                   (SELECT COUNT(*) FROM hunt_pending_phases o WHERE o.hunt_id = p.hunt_id
                    AND o.position <= p.position) AS number
            FROM hunt_pending_phases p JOIN hunts h ON h.id = p.hunt_id
            WHERE p.fail_id IN ({placeholders})""", list(by_id)):
        f = by_id[row["fail_id"]]
        f["phase_number"] = row["number"]
        f["phase_target"] = f"{display_name(row['species_id'], row['form'])} (en cours)"


def load_fails(owner, collection):
    rows = get_db().execute(
        "SELECT * FROM fails WHERE user_id = ? ORDER BY failed_on IS NULL, failed_on DESC, id DESC",
        (owner["id"],),
    )
    fails = [fail_view(r) for r in rows if collection_of(r["game"]) == collection]
    attach_fail_phases(fails)
    return fails


@app.route("/u/<username>/manques", defaults=MAIN)
@app.route(f"/u/<username>/{SEPARATE}/manques")
def collection_fails(username, collection):
    owner, response = find_owner(username, "collection_fails", collection)
    if response:
        return response
    return render_template("fails.html", **collection_context(owner, collection),
                           fails=load_fails(owner, collection))


def parse_fail_form(form):
    """Valide le formulaire d'un shiny manqué ; renvoie (données, erreurs)."""
    errors = []
    species_name = form.get("species", "").strip()
    species_id = find_species(species_name)
    if species_id is None:
        errors.append(f"Pokémon inconnu : « {species_name} ».")
    variant, error = parse_variant(species_id, form)
    if error:
        errors.append(error)
    game = form.get("game", "")
    if game not in GAMES:
        errors.append("Jeu invalide.")
    method = form.get("method", "").strip()
    if not method:
        errors.append("La méthode est requise.")
    gender = form.get("gender", "") or None
    if gender is not None and gender not in GENDERS:
        errors.append("Genre invalide.")
    failed_on = form.get("failed_on", "").strip() or None
    if failed_on:
        try:
            date.fromisoformat(failed_on)
        except ValueError:
            errors.append("Date invalide.")
    encounters, ok = parse_count(form.get("encounters", ""))
    if not ok:
        errors.append("Le nombre de rencontres doit être un entier positif.")
    duration = None
    if form.get("duration", "").strip():
        duration = parse_duration(form["duration"])
        if duration is None:
            errors.append("Durée invalide : utilisez H:MM:SS (ex. 2:30:00).")
    location, shiny_charm = parse_location_charm(form)
    return {
        "species_id": species_id, "form": variant, "game": game, "method": method[:200],
        "gender": gender, "encounters": encounters, "duration": duration, "location": location,
        "shiny_charm": shiny_charm, "reason": form.get("reason", "").strip()[:200] or None,
        "failed_on": failed_on, "notes": form.get("notes", "").strip()[:1000] or None,
    }, errors


FAIL_FIELDS = ["species_id", "form", "game", "method", "gender", "encounters", "duration", "location",
               "shiny_charm", "reason", "failed_on", "notes"]


def insert_fail(db, data):
    """Ajoute un shiny manqué au compte connecté ; renvoie son id."""
    columns = ", ".join(FAIL_FIELDS)
    return db.execute(
        f"INSERT INTO fails (user_id, {columns}) VALUES (:user_id, {', '.join(':' + f for f in FAIL_FIELDS)})",
        {**dict.fromkeys(FAIL_FIELDS), "shiny_charm": 0, **data, "user_id": g.user["id"]},
    ).lastrowid


def add_pending_phase(db, hunt_id, shiny_id=None, fail_id=None):
    """Ajoute une phase (shiny ou manqué) à la fin d'une chasse en cours ; renvoie son numéro."""
    position = db.execute(
        "SELECT COALESCE(MAX(position) + 1, 0) FROM hunt_pending_phases WHERE hunt_id = ?", (hunt_id,)
    ).fetchone()[0]
    db.execute("INSERT INTO hunt_pending_phases (hunt_id, shiny_id, fail_id, position) VALUES (?, ?, ?, ?)",
               (hunt_id, shiny_id, fail_id, position))
    return db.execute("SELECT COUNT(*) FROM hunt_pending_phases WHERE hunt_id = ?", (hunt_id,)).fetchone()[0]


def render_fail_form(fail=None, form=None, hunt=None):
    return render_template("fail_form.html", fail=fail, form=form or {}, hunt=hunt, reasons=FAIL_REASONS,
                           hunt_label=display_name(hunt["species_id"], hunt["form"]) if hunt else "",
                           pokedex=POKEDEX, games=GAMES, families=FAMILIES, genders=GENDERS,
                           methods=methods.by_game())


def redirect_to_fails(game):
    return redirect(url_for("collection_fails", username=g.user["username"], collection=collection_of(game)))


@app.route("/manque/new", methods=["GET", "POST"])
@login_required
def fail_new():
    # Depuis le compteur : la chasse fournit les valeurs par défaut ; elle continue ensuite
    hunt_id = request.values.get("chasse", type=int)
    hunt = get_own_hunt(hunt_id) if hunt_id else None
    if request.method == "POST":
        data, errors = parse_fail_form(request.form)
        if not errors:
            db = get_db()
            fail_id = insert_fail(db, data)
            message = f"{display_name(data['species_id'], data['form'])} ajouté aux shiny manqués 😭"
            if hunt and request.form.get("phase") == "1":
                message += f" (phase {add_pending_phase(db, hunt['id'], fail_id=fail_id)} de la chasse)"
            db.commit()
            flash(message, "success")
            if hunt:
                return redirect(url_for("hunt_counter", hunt_id=hunt["id"]))
            return redirect_to_fails(data["game"])
        for e in errors:
            flash(e, "error")
        return render_fail_form(form=request.form, hunt=hunt)
    form = {"failed_on": date.today().isoformat()}
    if hunt:
        elapsed = hunt_elapsed(hunt)
        form |= {"species": POKEDEX.get(hunt["species_id"], ""), "form": hunt["form"] or "",
                 "game": hunt["game"], "method": hunt["method"], "location": hunt["location"] or "",
                 "shiny_charm": hunt["shiny_charm"],
                 "encounters": hunt["count"] if hunt["mode"] == "count" else "",
                 "duration": clock(elapsed) if elapsed else ""}
    return render_fail_form(form=form, hunt=hunt)


def get_own_fail(fail_id):
    row = get_db().execute("SELECT * FROM fails WHERE id = ? AND user_id = ?", (fail_id, g.user["id"])).fetchone()
    if row is None:
        abort(404)
    return row


@app.route("/manque/<int:fail_id>/edit", methods=["GET", "POST"])
@login_required
def fail_edit(fail_id):
    row = get_own_fail(fail_id)
    if request.method == "POST":
        data, errors = parse_fail_form(request.form)
        if not errors:
            db = get_db()
            db.execute(f"UPDATE fails SET {', '.join(f + ' = :' + f for f in FAIL_FIELDS)} "
                       "WHERE id = :id AND user_id = :user_id", {**data, "id": fail_id, "user_id": g.user["id"]})
            db.commit()
            flash("Modifications enregistrées.", "success")
            return redirect_to_fails(data["game"])
        for e in errors:
            flash(e, "error")
        return render_fail_form(fail=row, form=request.form)
    form = {k: "" if row[k] is None else row[k] for k in row.keys()}
    form["species"] = POKEDEX.get(row["species_id"], "")
    form["duration"] = clock(row["duration"]) if row["duration"] is not None else ""
    return render_fail_form(fail=row, form=form)


@app.route("/manque/<int:fail_id>/delete", methods=["POST"])
@login_required
def fail_delete(fail_id):
    row = get_own_fail(fail_id)
    db = get_db()
    db.execute("DELETE FROM fails WHERE id = ? AND user_id = ?", (fail_id, g.user["id"]))
    db.commit()
    flash("Shiny manqué supprimé.", "success")
    return redirect_to_fails(row["game"])


def export_filename(owner, collection, kind=""):
    parts = ["krabhunt", owner["username"]]
    if collection != MAIN_COLLECTION:
        parts.append(collection)
    if kind:
        parts.append(kind)
    return "-".join(parts + [date.today().isoformat()]) + ".csv"


@app.route("/u/<username>/export.csv", defaults=MAIN)
@app.route(f"/u/<username>/{SEPARATE}/export.csv")
def collection_export(username, collection):
    """La collection en CSV, avec les mêmes filtres et le même tri que la page affichée."""
    owner = find_user(username)
    if owner is None:
        abort(404)
    shinies = filters.apply(load_collection(owner, collection), filters.parse(request.args))
    return Response(
        export.to_csv(shinies),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{export_filename(owner, collection)}"'},
    )


@app.route("/u/<username>/export-tracker.csv", defaults=MAIN)
@app.route(f"/u/<username>/{SEPARATE}/export-tracker.csv")
def collection_export_tracker(username, collection):
    """La collection au format du tracker de shiny (sections « Shiny obtenus » / « Shasses en cours »).

    Les chasses en cours (de la même collection) ne sont incluses que pour le propriétaire
    (le compteur est privé).
    """
    owner = find_user(username)
    if owner is None:
        abort(404)
    shinies = filters.apply(load_collection(owner, collection), filters.parse(request.args))
    hunts = []
    if g.user and g.user["id"] == owner["id"]:
        hunts = [h for h in get_db().execute(
            "SELECT * FROM hunts WHERE user_id = ? ORDER BY id", (owner["id"],)
        ) if collection_of(h["game"]) == collection]
    title = owner["username"] + (f" ({COLLECTIONS[collection][0]})" if collection != MAIN_COLLECTION else "")
    return Response(
        export.to_tracker_csv(shinies, title, hunts, load_fails(owner, collection)),
        mimetype="text/csv",
        headers={"Content-Disposition":
                 f'attachment; filename="{export_filename(owner, collection, "tracker")}"'},
    )


def decode_upload(raw):
    """Texte d'un CSV envoyé : UTF-8 (avec ou sans BOM), sinon Windows-1252 (Excel « CSV » classique)."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def split_duplicates(rows, existing, fingerprint, skip_duplicates):
    """Sépare (à importer, doublons) ; `existing` : empreinte -> id déjà en base."""
    to_import, duplicates, seen = [], [], set()
    for row in rows:
        key = fingerprint(row["data"])
        if skip_duplicates and (key in existing or key in seen):
            row["existing_id"] = existing.get(key)
            duplicates.append(row)
        else:
            to_import.append(row)
        seen.add(key)
    return to_import, duplicates


def plan_import(text, skip_duplicates):
    """Analyse un CSV pour le compte connecté.

    Renvoie un dict : shiny et chasses en cours à importer, leurs doublons, erreurs, remarques.
    """
    rows, hunts, fails, errors, notices = importer.parse(text)
    db = get_db()
    existing, existing_hunts, existing_fails = {}, {}, {}
    for row in db.execute("SELECT * FROM fails WHERE user_id = ?", (g.user["id"],)):
        existing_fails.setdefault(importer.fail_fingerprint(row), row["id"])
    for row in db.execute("SELECT * FROM shinies WHERE user_id = ?", (g.user["id"],)):
        existing.setdefault(importer.fingerprint(row), row["id"])
    for row in db.execute("SELECT * FROM hunts WHERE user_id = ?", (g.user["id"],)):
        existing_hunts.setdefault(importer.hunt_fingerprint(row), row["id"])
    to_import, duplicates = split_duplicates(rows, existing, importer.fingerprint, skip_duplicates)
    hunts, hunt_duplicates = split_duplicates(hunts, existing_hunts, importer.hunt_fingerprint, skip_duplicates)
    fails, fail_duplicates = split_duplicates(fails, existing_fails, importer.fail_fingerprint, skip_duplicates)
    return {"to_import": to_import, "duplicates": duplicates, "hunts": hunts,
            "hunt_duplicates": hunt_duplicates, "fails": fails, "fail_duplicates": fail_duplicates,
            "errors": errors, "notices": notices}


@app.route("/import", methods=["GET", "POST"])
@login_required
def collection_import():
    if request.method == "GET":
        return render_template("import.html", step="upload")

    skip_duplicates = request.form.get("doublons") == "ignorer"
    if request.form.get("action") == "confirm":
        text = request.form.get("csv", "")
    else:
        upload = request.files.get("fichier")
        if not upload or not upload.filename:
            flash("Choisissez un fichier CSV.", "error")
            return render_template("import.html", step="upload")
        text = decode_upload(upload.read())

    plan = plan_import(text, skip_duplicates)
    to_import, duplicates, hunts, errors = plan["to_import"], plan["duplicates"], plan["hunts"], plan["errors"]

    if request.form.get("action") != "confirm":
        preview = [dict(row, view=to_view({**row["data"], "id": 0, "user_id": g.user["id"]}))
                   for row in to_import[:30]]
        hunts_preview = [hunt_view({**row["data"], "id": 0, "user_id": g.user["id"]}) for row in hunts]
        fails_preview = [fail_view({**row["data"], "id": 0, "user_id": g.user["id"]}) for row in plan["fails"]]
        return render_template(
            "import.html", step="preview", csv=text, skip_duplicates=skip_duplicates,
            preview=preview, hunts_preview=hunts_preview, fails_preview=fails_preview, **plan,
        )

    db = get_db()
    new_ids = {}  # ancien id (colonne « id » du fichier) -> id dans la collection
    for row in duplicates:
        if row["old_id"] and row.get("existing_id"):
            new_ids[row["old_id"]] = row["existing_id"]
    for row in to_import:
        shiny_id = insert_shiny(db, row["data"])
        if row["old_id"]:
            new_ids[row["old_id"]] = shiny_id
    for row in hunts:
        hunt = row["data"]
        db.execute(
            """INSERT INTO hunts (user_id, species_id, form, game, method, location, shiny_charm,
                                   count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))""",
            (g.user["id"], hunt["species_id"], hunt["form"], hunt["game"], hunt["method"],
             hunt["location"], hunt["shiny_charm"], hunt["count"], hunt["created_at"]),
        )

    for row in plan["fails"]:
        insert_fail(db, row["data"])

    # Phases : on relie chaque phase importée à sa cible, dans l'ordre des numéros de phase
    by_target = {}
    for row in to_import:
        target = new_ids.get(row["target_id"])
        if target:
            by_target.setdefault(target, []).append((row["phase_number"] or 0, new_ids[row["old_id"]]))
    linked = 0
    for target, phases in by_target.items():
        if db.execute("SELECT 1 FROM hunt_phases WHERE shiny_id = ?", (target,)).fetchone():
            continue  # la cible est elle-même une phase : on ne crée pas de chaîne
        start = db.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) FROM hunt_phases WHERE target_id = ?", (target,)
        ).fetchone()[0]
        for offset, (_, shiny_id) in enumerate(sorted(phases)):
            linked += db.execute(
                "INSERT OR IGNORE INTO hunt_phases (target_id, shiny_id, position) VALUES (?, ?, ?)",
                (target, shiny_id, start + offset),
            ).rowcount
    db.commit()

    message = f"{len(to_import)} shiny importé{'s' if len(to_import) > 1 else ''}"
    if linked:
        message += f", {linked} phase{'s' if linked > 1 else ''} reliée{'s' if linked > 1 else ''}"
    if hunts:
        message += f", {len(hunts)} chasse{'s' if len(hunts) > 1 else ''} en cours ajoutée{'s' if len(hunts) > 1 else ''} au compteur"
    if plan["fails"]:
        n = len(plan["fails"])
        message += f", {n} shiny manqué{'s' if n > 1 else ''}"
    duplicates = duplicates + plan["hunt_duplicates"] + plan["fail_duplicates"]
    if duplicates:
        message += f" ; {len(duplicates)} doublon{'s' if len(duplicates) > 1 else ''} ignoré{'s' if len(duplicates) > 1 else ''}"
    if errors:
        message += f" ; {len(errors)} ligne{'s' if len(errors) > 1 else ''} en erreur non importée{'s' if len(errors) > 1 else ''}"
    flash(message + ".", "success")
    return redirect_to_own_collection()


@app.errorhandler(413)
def too_large(error):
    flash("Fichier trop volumineux (4 Mo maximum).", "error")
    return redirect(url_for("collection_import"))


@app.template_filter("duree")
def duree(value):
    return format_duration(value)


@app.template_filter("chrono")
def chrono(value):
    return clock(value)


@app.template_filter("nombre")
def nombre(value):
    return stats.fr_int(value) if value is not None else "—"


def parse_count(value):
    """Entier positif facultatif ; renvoie (valeur ou None, valide)."""
    value = value.strip()
    if not value:
        return None, True
    if value.isascii() and value.isdigit():
        return int(value), True
    return None, False


def phase_candidates(target_id=None):
    """Shiny et shiny manqués du compte pouvant servir de phase à la cible `target_id`
    (None = nouvelle cible) : {clé de phase: libellé}.

    Exclus : la cible elle-même, les shiny qui sont déjà cibles d'une chasse avec phases,
    et ceux (ou les manqués) déjà rattachés comme phase à une autre chasse.
    """
    target_id = target_id or 0
    rows = get_db().execute(
        """SELECT * FROM shinies
           WHERE user_id = ? AND id != ?
             AND id NOT IN (SELECT target_id FROM hunt_phases)
             AND id NOT IN (SELECT shiny_id FROM hunt_phases WHERE target_id != ?)
           ORDER BY caught_on IS NULL, caught_on, id""",
        (g.user["id"], target_id, target_id),
    )
    candidates = {}
    for row in rows:
        s = to_view(row)
        parts = [s["name"] + (f" ({s['species']})" if row["nickname"] else ""), s["game_label"]]
        if row["caught_on"]:
            parts.append(date_fr(row["caught_on"]))
        candidates[str(row["id"])] = " · ".join(parts)
    for row in get_db().execute(
        """SELECT * FROM fails
           WHERE user_id = ? AND id NOT IN (SELECT fail_id FROM hunt_phases
                                            WHERE fail_id IS NOT NULL AND target_id != ?)
           ORDER BY failed_on IS NULL, failed_on, id""",
        (g.user["id"], target_id),
    ):
        f = fail_view(row)
        parts = [f"😭 {f['species']} (manqué)", f["game_label"]]
        if row["reason"]:
            parts.append(row["reason"])
        if row["failed_on"]:
            parts.append(date_fr(row["failed_on"]))
        candidates[f"f{row['id']}"] = " · ".join(parts)
    return candidates


def parse_phases(form, candidates):
    """Lit les phases choisies (clés de phase, dans l'ordre) ; renvoie (clés, erreurs)."""
    keys, errors = [], []
    for number, value in enumerate(form.getlist("phase_shiny"), start=1):
        if not value:
            continue
        if value not in candidates:
            errors.append(f"Phase {number} : ce shiny ne peut pas être choisi comme phase.")
        elif value in keys:
            errors.append(f"Phase {number} : ce shiny est déjà dans la liste.")
        else:
            keys.append(value)
    return keys, errors


def phase_ids(target_id):
    return [
        phase_key(row)
        for row in get_db().execute(
            "SELECT shiny_id, fail_id FROM hunt_phases WHERE target_id = ? ORDER BY position", (target_id,)
        )
    ]


def phase_of(shiny_id):
    """(numéro, cible) si ce shiny est une phase d'une chasse, sinon None."""
    row = get_db().execute(
        """SELECT h.target_id,
                  (SELECT COUNT(*) FROM hunt_phases o
                   WHERE o.target_id = h.target_id AND o.position <= h.position) AS number
           FROM hunt_phases h WHERE h.shiny_id = ?""",
        (shiny_id,),
    ).fetchone()
    if row is None:
        return None
    target = to_view(get_db().execute(
        "SELECT * FROM shinies WHERE id = ?", (row["target_id"],)).fetchone())
    return row["number"], target


def save_phases(db, target_id, keys):
    """Remplace toutes les phases d'une chasse (clés de phase, dans l'ordre)."""
    db.execute("DELETE FROM hunt_phases WHERE target_id = ?", (target_id,))
    db.executemany(
        "INSERT INTO hunt_phases (target_id, shiny_id, fail_id, position) VALUES (?, ?, ?, ?)",
        [(target_id, *phase_columns(key), position) for position, key in enumerate(keys)],
    )


def phase_list(table, owner_column, owner_id):
    """Phases d'une chasse, dans l'ordre : [{"fail": bool, "view": to_view ou fail_view}]."""
    db = get_db()
    phases = []
    for row in db.execute(f"SELECT shiny_id, fail_id FROM {table} WHERE {owner_column} = ? ORDER BY position",
                          (owner_id,)):
        if row["fail_id"]:
            phases.append({"fail": True, "view": fail_view(
                db.execute("SELECT * FROM fails WHERE id = ?", (row["fail_id"],)).fetchone())})
        else:
            phases.append({"fail": False, "view": to_view(
                db.execute("SELECT * FROM shinies WHERE id = ?", (row["shiny_id"],)).fetchone())})
    return phases


def parse_variant(species_id, form):
    """Forme choisie dans le formulaire (champ « form ») ; renvoie (clé ou None, erreur)."""
    key = form.get("form", "").strip() or None
    if key is None or species_id is None:
        return None, None
    if key not in forms_of(species_id):
        return None, f"Forme invalide pour {POKEDEX[species_id]}."
    return key, None


def parse_location_charm(form):
    """(lieu ou None, charme chroma 0/1) depuis les champs « location » et « shiny_charm »."""
    location = form.get("location", "").strip()[:100] or None
    return location, int(form.get("shiny_charm") == "1")


def parse_form(form):
    """Valide le formulaire ; renvoie (données, erreurs)."""
    errors = []
    species_name = form.get("species", "").strip()
    species_id = find_species(species_name)
    if species_id is None:
        errors.append(f"Pokémon inconnu : « {species_name} ».")

    variant, error = parse_variant(species_id, form)
    if error:
        errors.append(error)

    game = form.get("game", "")
    if game not in GAMES:
        errors.append("Jeu invalide.")

    method = form.get("method", "").strip()
    if not method:
        errors.append("La méthode d'obtention est requise.")

    gender = form.get("gender", "")
    if gender not in GENDERS:
        errors.append("Genre invalide.")

    caught_on = form.get("caught_on", "").strip() or None
    if caught_on:
        try:
            date.fromisoformat(caught_on)
        except ValueError:
            errors.append("Date invalide.")

    encounters, ok = parse_count(form.get("encounters", ""))
    if not ok:
        errors.append("Le nombre de rencontres doit être un entier positif.")

    duration = None
    if form.get("duration", "").strip():
        duration = parse_duration(form["duration"])
        if duration is None:
            errors.append("Durée invalide : utilisez H:MM:SS (ex. 2:30:00).")

    ball = form.get("ball", "") or None
    if ball is not None and ball not in BALLS:
        errors.append("Poké Ball invalide.")

    sprite_url = form.get("sprite_url", "").strip() or None
    if sprite_url and not sprite_url.startswith("https://"):
        errors.append("L'URL du sprite doit commencer par https://")

    location, shiny_charm = parse_location_charm(form)

    data = {
        "species_id": species_id,
        "form": variant,
        "game": game,
        "method": method,
        "gender": gender,
        "caught_on": caught_on,
        "nickname": form.get("nickname", "").strip() or None,
        "encounters": encounters,
        "duration": duration,
        "ball": ball,
        "location": location,
        "shiny_charm": shiny_charm,
        "notes": form.get("notes", "").strip() or None,
        "sprite_url": sprite_url,
    }
    return data, errors


def insert_shiny(db, data):
    """Ajoute un shiny à la collection de l'utilisateur connecté ; renvoie son id."""
    return db.execute(
        """INSERT INTO shinies
           (user_id, species_id, form, game, method, gender, caught_on, nickname,
            encounters, duration, ball, location, shiny_charm, notes, sprite_url)
           VALUES (:user_id, :species_id, :form, :game, :method, :gender, :caught_on, :nickname,
                   :encounters, :duration, :ball, :location, :shiny_charm, :notes, :sprite_url)""",
        {"form": None, "nickname": None, "caught_on": None, "encounters": None, "duration": None,
         "ball": None,
         "location": None, "shiny_charm": 0, "notes": None, "sprite_url": None,
         **data, "user_id": g.user["id"]},
    ).lastrowid


def render_form(shiny=None, form=None, phases=(), candidates=None, phase_info=None, hunt=None):
    return render_template(
        "shiny_form.html",
        shiny=shiny,
        hunt=hunt,                    # chasse du compteur terminée par ce shiny
        form=form or {},
        phases=phases,                # ids des shiny choisis comme phases, dans l'ordre
        candidates=candidates or {},  # id -> libellé des shiny sélectionnables
        phase_info=phase_info,        # (numéro, cible) si ce shiny est lui-même une phase
        pokedex=POKEDEX,
        games=GAMES,
        families=FAMILIES,
        methods=methods.by_game(),
        method_problems=methods.problems(),
        genders=GENDERS,
        balls=BALLS,
    )


@app.route("/shiny/new", methods=["GET", "POST"])
@login_required
def shiny_new():
    candidates = phase_candidates()
    # Arrivée depuis le compteur : la chasse fournit les valeurs par défaut
    hunt_id = request.values.get("chasse", type=int)
    hunt = get_own_hunt(hunt_id) if hunt_id else None

    if request.method == "POST":
        data, errors = parse_form(request.form)
        phases, phase_errors = parse_phases(request.form, candidates)
        errors += phase_errors
        if not errors:
            db = get_db()
            save_phases(db, insert_shiny(db, data), phases)
            if hunt:
                db.execute("DELETE FROM hunts WHERE id = ?", (hunt["id"],))
            db.commit()
            flash(f"{display_name(data['species_id'], data['form'])} shiny ajouté ✨", "success")
            return redirect_to_own_collection(data["game"])
        for e in errors:
            flash(e, "error")
        return render_form(form=request.form, phases=phases, candidates=candidates, hunt=hunt)

    if hunt:
        if hunt["mode"] == "timer":
            pause_timer(get_db(), hunt)
            get_db().commit()
            hunt = get_own_hunt(hunt["id"])
        form = {
            "species": POKEDEX.get(hunt["species_id"], ""),
            "form": hunt["form"] or "",
            "game": hunt["game"],
            "method": hunt["method"],
            "encounters": hunt["count"] if hunt["mode"] == "count" else "",
            "duration": clock(hunt["elapsed"]) if hunt["elapsed"] else "",
            "location": hunt["location"] or "",
            "shiny_charm": hunt["shiny_charm"],
            "caught_on": date.today().isoformat(),
        }
        return render_form(form=form, phases=pending_phase_ids(hunt["id"]),
                           candidates=candidates, hunt=hunt)
    return render_form(candidates=candidates)


@app.route("/shiny/<int:shiny_id>")
def shiny_detail(shiny_id):
    """Fiche détaillée d'un shiny (publique, comme la collection)."""
    db = get_db()
    row = db.execute("SELECT * FROM shinies WHERE id = ?", (shiny_id,)).fetchone()
    if row is None:
        abort(404)
    owner = db.execute("SELECT * FROM users WHERE id = ?", (row["user_id"],)).fetchone()
    s = to_view(row)
    phases = phase_list("hunt_phases", "target_id", shiny_id)
    attach_phases([s])  # nom de la cible si ce shiny est une phase
    if (info := phase_of(shiny_id)):
        s["phase_number"], target = info
        s["phase_target"], s["phase_target_id"] = target["name"], target["id"]
    _, odds_note = methods.odds(row["method"], row["game"], bool(row["shiny_charm"]))
    return render_template(
        "shiny_detail.html",
        **collection_context(owner, collection_of(row["game"])),
        s=s,
        phases=phases,
        odds_note=odds_note,
        luck=stats.luck(row["encounters"], s["odds"]),
        rate=encounter_rate(row["encounters"], row["duration"]),
    )


@app.route("/shiny/<int:shiny_id>/edit", methods=["GET", "POST"])
@login_required
def shiny_edit(shiny_id):
    row = get_own_shiny(shiny_id)
    phase_info = phase_of(shiny_id)
    # Une phase ne peut pas avoir elle-même de phases
    candidates = {} if phase_info else phase_candidates(shiny_id)
    if request.method == "POST":
        data, errors = parse_form(request.form)
        phases, phase_errors = parse_phases(request.form, candidates)
        errors += phase_errors
        if not errors:
            db = get_db()
            db.execute(
                """UPDATE shinies SET species_id = :species_id, form = :form,
                   game = :game, method = :method,
                   gender = :gender, caught_on = :caught_on, nickname = :nickname,
                   encounters = :encounters, duration = :duration, ball = :ball, location = :location,
                   shiny_charm = :shiny_charm, notes = :notes,
                   sprite_url = :sprite_url
                   WHERE id = :id AND user_id = :user_id""",
                {**data, "id": shiny_id, "user_id": g.user["id"]},
            )
            if not phase_info:
                save_phases(db, shiny_id, phases)
            db.commit()
            flash("Modifications enregistrées.", "success")
            return redirect_to_own_collection(data["game"])
        for e in errors:
            flash(e, "error")
        return render_form(shiny=row, form=request.form, phases=phases,
                           candidates=candidates, phase_info=phase_info)

    form = {k: "" if row[k] is None else row[k] for k in row.keys()}
    form["species"] = POKEDEX.get(row["species_id"], "")
    form["duration"] = clock(row["duration"]) if row["duration"] is not None else ""
    return render_form(shiny=row, form=form, phases=phase_ids(shiny_id),
                       candidates=candidates, phase_info=phase_info)


@app.route("/shiny/<int:shiny_id>/delete", methods=["POST"])
@login_required
def shiny_delete(shiny_id):
    row = get_own_shiny(shiny_id)
    db = get_db()
    db.execute("DELETE FROM shinies WHERE id = ? AND user_id = ?", (shiny_id, g.user["id"]))
    db.commit()
    flash("Shiny supprimé.", "success")
    return redirect_to_own_collection(row["game"])


# Formes par n° de Pokédex, pour la liste « Forme » des formulaires (static/forms.js)
FORMS_JSON = {
    dex: {"default": info["default"], "forms": {k: f["name"] for k, f in info["forms"].items()}}
    for dex, info in FORMS.items()
}


@app.route("/formes.json")
def forms_json():
    response = app.json.response(FORMS_JSON)
    response.cache_control.max_age = 86400
    return response


# --- Compteur --------------------------------------------------------------

def get_own_hunt(hunt_id):
    hunt = get_db().execute(
        "SELECT * FROM hunts WHERE id = ? AND user_id = ?", (hunt_id, g.user["id"])
    ).fetchone()
    if hunt is None:
        abort(404)
    return hunt


def pending_phase_ids(hunt_id):
    return [
        phase_key(row)
        for row in get_db().execute(
            "SELECT shiny_id, fail_id FROM hunt_pending_phases WHERE hunt_id = ? ORDER BY position",
            (hunt_id,),
        )
    ]


def hunt_elapsed(hunt):
    """Temps écoulé du timer, période en cours comprise (secondes)."""
    running = int(time.time()) - hunt["started_at"] if hunt["started_at"] else 0
    return hunt["elapsed"] + max(0, running)


def pause_timer(db, hunt):
    db.execute("UPDATE hunts SET elapsed = ?, started_at = NULL WHERE id = ?",
               (hunt_elapsed(hunt), hunt["id"]))


IDLE_GAP = 300  # au-delà de 5 min sans clic, la pause ne compte pas dans le temps actif


def add_encounters(db, hunt, delta):
    """Ajoute `delta` rencontres et le temps écoulé depuis le clic précédent (s'il est récent)."""
    now = int(time.time())
    gap = now - hunt["last_tick"] if hunt["last_tick"] else None
    active = gap if gap is not None and 0 < gap <= IDLE_GAP else 0
    db.execute("UPDATE hunts SET count = MAX(0, count + ?), elapsed = elapsed + ?, last_tick = ? WHERE id = ?",
               (delta, active, now, hunt["id"]))


def encounter_rate(encounters, seconds):
    """Rencontres par heure (arrondi), ou None s'il n'y a pas assez de données (moins d'une minute)."""
    if not encounters or not seconds or seconds < 60:
        return None
    return round(encounters * 3600 / seconds)


def hunt_view(row):
    hunt = {"mode": "count", "elapsed": 0, "started_at": None, **row}  # aperçu d'import : sans timer
    hunt["elapsed_now"] = hunt_elapsed(hunt)
    hunt["rate"] = encounter_rate(hunt.get("count"), hunt["elapsed"]) if hunt["mode"] == "count" else None
    hunt["odds"], hunt["odds_note"] = methods.odds(hunt["method"], hunt["game"], bool(hunt.get("shiny_charm")))
    hunt["species"] = display_name(row["species_id"], row["form"])
    hunt["game_label"] = GAMES.get(row["game"], (row["game"],))[0]
    hunt["sprites"] = sprite_candidates(row["species_id"], row["game"], None, row["form"])
    return hunt


@app.route("/compteur", methods=["GET", "POST"])
@login_required
def hunts():
    db = get_db()
    if request.method == "POST":
        species_name = request.form.get("species", "").strip()
        species_id = find_species(species_name)
        game = request.form.get("game", "")
        method = request.form.get("method", "").strip()
        variant, error = parse_variant(species_id, request.form)
        location, shiny_charm = parse_location_charm(request.form)
        mode = "timer" if request.form.get("mode") == "timer" else "count"
        errors = [error] if error else []
        if species_id is None:
            errors.append(f"Pokémon inconnu : « {species_name} ».")
        if game not in GAMES:
            errors.append("Jeu invalide.")
        if not method:
            errors.append("La méthode est requise.")
        if not errors:
            hunt_id = db.execute(
                """INSERT INTO hunts (user_id, species_id, form, game, method, location, shiny_charm, mode)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (g.user["id"], species_id, variant, game, method, location, shiny_charm, mode),
            ).lastrowid
            db.commit()
            return redirect(url_for("hunt_counter", hunt_id=hunt_id))
        for e in errors:
            flash(e, "error")

    rows = db.execute(
        """SELECT h.*, (SELECT COUNT(*) FROM hunt_pending_phases p WHERE p.hunt_id = h.id) AS phases
           FROM hunts h WHERE user_id = ? ORDER BY id DESC""",
        (g.user["id"],),
    )
    return render_template(
        "hunts.html",
        hunts=[hunt_view(r) for r in rows],
        form=request.form,
        pokedex=POKEDEX,
        games=GAMES,
        families=FAMILIES,
        methods=methods.by_game(),
        method_problems=methods.problems(),
    )


@app.route("/compteur/multi")
@login_required
def hunts_multi():
    """Plusieurs chasses côte à côte (?id=1&id=4…), dans l'ordre demandé."""
    ids = list(dict.fromkeys(request.args.getlist("id", type=int)))
    rows = {}
    if ids:
        rows = {row["id"]: row for row in get_db().execute(
            f"SELECT * FROM hunts WHERE user_id = ? AND id IN ({','.join('?' * len(ids))})",
            [g.user["id"], *ids],
        )}
    hunts = [hunt_view(rows[i]) for i in ids if i in rows]
    if not hunts:
        flash("Cochez au moins une chasse à afficher.", "error")
        return redirect(url_for("hunts"))
    return render_template("hunt_multi.html", hunts=hunts)


@app.route("/compteur/<int:hunt_id>")
@login_required
def hunt_counter(hunt_id):
    hunt = hunt_view(get_own_hunt(hunt_id))
    return render_template(
        "hunt_counter.html",
        hunt=hunt,
        phases=phase_list("hunt_pending_phases", "hunt_id", hunt_id),
        pokedex=POKEDEX,
        genders=GENDERS,
        balls=BALLS,
    )


@app.route("/compteur/<int:hunt_id>/count", methods=["POST"])
@login_required
def hunt_count(hunt_id):
    """API JSON du compteur : {"delta": n} ajoute n, {"value": n} fixe la valeur, {"step": n}."""
    hunt = get_own_hunt(hunt_id)
    payload = request.get_json(silent=True) or {}
    db = get_db()

    def as_int(key):
        value = payload.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    if (delta := as_int("delta")) is not None:
        add_encounters(db, hunt, delta)
    if (value := as_int("value")) is not None and value >= 0:
        db.execute("UPDATE hunts SET count = ? WHERE id = ?", (value, hunt_id))
    if (step := as_int("step")) is not None and 1 <= step <= 100:
        db.execute("UPDATE hunts SET step = ? WHERE id = ?", (step, hunt_id))
    db.commit()
    hunt = get_own_hunt(hunt_id)
    return {"count": hunt["count"], "step": hunt["step"], "elapsed": hunt["elapsed"],
            "rate": encounter_rate(hunt["count"], hunt["elapsed"])}


@app.route("/compteur/<int:hunt_id>/timer", methods=["POST"])
@login_required
def hunt_timer(hunt_id):
    """API JSON du timer : {"action": "start" | "pause"} ou {"value": secondes} pour fixer le temps."""
    hunt = get_own_hunt(hunt_id)
    payload = request.get_json(silent=True) or {}
    db = get_db()
    action = payload.get("action")
    if action == "start" and not hunt["started_at"]:
        db.execute("UPDATE hunts SET started_at = ? WHERE id = ?", (int(time.time()), hunt_id))
    elif action == "pause" and hunt["started_at"]:
        pause_timer(db, hunt)
    value = payload.get("value")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        # Le timer repart de la valeur fixée (et continue s'il tournait)
        db.execute("UPDATE hunts SET elapsed = ?, started_at = CASE WHEN started_at IS NULL THEN NULL ELSE ? END "
                   "WHERE id = ?", (value, int(time.time()), hunt_id))
    db.commit()
    hunt = get_own_hunt(hunt_id)
    return {"elapsed": hunt_elapsed(hunt), "running": hunt["started_at"] is not None}


@app.route("/compteur/<int:hunt_id>/phase", methods=["POST"])
@login_required
def hunt_phase(hunt_id):
    """Un shiny non ciblé est apparu : il entre dans la collection comme phase de la chasse."""
    hunt = get_own_hunt(hunt_id)
    species_name = request.form.get("species", "").strip()
    species_id = find_species(species_name)
    gender = request.form.get("gender", "")
    ball = request.form.get("ball", "") or None
    variant, variant_error = parse_variant(species_id, request.form)
    if species_id is None:
        flash(f"Pokémon inconnu : « {species_name} ».", "error")
    elif variant_error:
        flash(variant_error, "error")
    elif gender not in GENDERS:
        flash("Choisissez le genre de la phase.", "error")
    elif ball is not None and ball not in BALLS:
        flash("Poké Ball invalide.", "error")
    else:
        db = get_db()
        shiny_id = insert_shiny(db, {
            "species_id": species_id,
            "form": variant,
            "game": hunt["game"],
            "method": hunt["method"],
            "location": hunt["location"],
            "shiny_charm": hunt["shiny_charm"],
            "gender": gender,
            "nickname": request.form.get("nickname", "").strip() or None,
            "ball": ball,
            "encounters": hunt["count"] if hunt["mode"] == "count" else None,
            "duration": hunt_elapsed(hunt) or None,
            "caught_on": date.today().isoformat(),
        })
        number = add_pending_phase(db, hunt_id, shiny_id=shiny_id)
        db.commit()
        flash(f"Phase {number} : {display_name(species_id, variant)} ajouté à la collection ✨", "success")
    return redirect(url_for("hunt_counter", hunt_id=hunt_id))


# --- Mode stream (OBS) ------------------------------------------------------
# OBS n'est pas connecté au compte : la page est publique mais à une adresse secrète
# (/stream/<jeton>), en lecture seule.

STREAM_COLOR_RE = re.compile(r"[0-9a-fA-F]{6}")


def user_token(user_id, column, renew=False):
    """Jeton secret de l'utilisateur (`stream_token` ou `api_token`), créé au premier usage."""
    assert column in ("stream_token", "api_token")
    db = get_db()
    token = db.execute(f"SELECT {column} FROM users WHERE id = ?", (user_id,)).fetchone()[0]
    if token is None or renew:
        token = secrets.token_urlsafe(18)
        db.execute(f"UPDATE users SET {column} = ? WHERE id = ?", (token, user_id))
        db.commit()
    return token


def stream_token(user_id, renew=False):
    return user_token(user_id, "stream_token", renew)


def stream_owner(token):
    user = get_db().execute("SELECT id FROM users WHERE stream_token = ?", (token,)).fetchone()
    if user is None:
        abort(404)
    return user


@app.route("/compteur/stream")
@login_required
def stream_settings():
    rows = get_db().execute("SELECT * FROM hunts WHERE user_id = ? ORDER BY id DESC", (g.user["id"],))
    return render_template(
        "stream_settings.html",
        hunts=[hunt_view(r) for r in rows],
        selected=request.args.getlist("id", type=int),
        overlay_url=url_for("stream_overlay", token=stream_token(g.user["id"]), _external=True),
    )


@app.route("/compteur/stream/regenerer", methods=["POST"])
@login_required
def stream_regenerate():
    stream_token(g.user["id"], renew=True)
    flash("Nouvelle adresse créée : remplacez-la dans OBS.", "success")
    return redirect(url_for("stream_settings"))


@app.route("/stream/<token>")
def stream_overlay(token):
    stream_owner(token)
    args = request.args
    flag = lambda key, default: args.get(key, "1" if default else "0") != "0"
    size = args.get("taille", type=int) or 32
    color = args.get("couleur", "")
    opts = {
        "sprite": flag("sprite", True), "name": flag("name", True), "odds": flag("odds", True),
        "phase": flag("phase", True), "game": flag("game", False), "vertical": flag("vertical", False),
        "empty": flag("vide", False),
        "size": min(max(size, 12), 120),
        "color": f"#{color}" if STREAM_COLOR_RE.fullmatch(color) else "#ffd84d",
    }
    data_url = url_for("stream_data", token=token, id=args.getlist("id", type=int))
    response = app.make_response(render_template("stream_overlay.html", opts=opts, data_url=data_url))
    response.headers["X-Robots-Tag"] = "noindex"
    return response


@app.route("/stream/<token>/data")
def stream_data(token):
    """Chasses en cours (toutes, ou celles de ?id=…, dans cet ordre) pour la source OBS."""
    user = stream_owner(token)
    ids = list(dict.fromkeys(request.args.getlist("id", type=int)))
    rows = get_db().execute(
        """SELECT h.*, (SELECT COUNT(*) FROM hunt_pending_phases p WHERE p.hunt_id = h.id) AS phases
           FROM hunts h WHERE user_id = ? ORDER BY id""",
        (user["id"],),
    ).fetchall()
    if ids:
        by_id = {r["id"]: r for r in rows}
        rows = [by_id[i] for i in ids if i in by_id]
    hunts = []
    for row in rows:
        h = hunt_view(row)
        hunts.append({
            "id": h["id"], "species": h["species"], "game": h["game_label"], "sprites": h["sprites"],
            "mode": h["mode"], "count": h["count"], "elapsed": h["elapsed_now"],
            "running": h["started_at"] is not None, "odds": h["odds"], "phases": row["phases"],
        })
    response = app.json.response({"hunts": hunts})
    response.cache_control.no_store = True
    return response


# --- Raccourcis globaux (tools/krabhunt_raccourcis.py) ------------------------
# Le programme tourne sur le PC du joueur, hors du navigateur : il s'authentifie avec la clé
# `api_token`, qui ne permet que de faire avancer les compteurs.

HOTKEY_DEFAULTS = [("num plus", "num minus"), ("page up", "page down"), ("f9", "f10"), ("f11", "f12")]


@app.route("/compteur/raccourcis")
@login_required
def hotkeys_settings():
    rows = get_db().execute("SELECT * FROM hunts WHERE user_id = ? ORDER BY id DESC", (g.user["id"],))
    hunts = [hunt_view(r) for r in rows]
    defaults = [HOTKEY_DEFAULTS[i] if i < len(HOTKEY_DEFAULTS) else ("", "") for i in range(len(hunts))]
    return render_template(
        "hotkeys_settings.html",
        hunts=hunts,
        defaults=defaults,
        site=request.host_url.rstrip("/"),
        api_key=user_token(g.user["id"], "api_token"),
    )


@app.route("/compteur/raccourcis/regenerer", methods=["POST"])
@login_required
def hotkeys_regenerate():
    user_token(g.user["id"], "api_token", renew=True)
    flash("Nouvelle clé créée : re-téléchargez le fichier de configuration.", "success")
    return redirect(url_for("hotkeys_settings"))


TOOLS = {"krabhunt_raccourcis.py", "krabhunt_auto.py"}  # programmes à lancer sur le PC (dossier tools/)


@app.route("/compteur/outils/<name>")
@login_required
def tool_script(name):
    if name not in TOOLS:
        abort(404)
    return send_file(os.path.join(BASE_DIR, "tools", name), mimetype="text/x-python", as_attachment=True)


def api_user(token):
    user = get_db().execute("SELECT id FROM users WHERE api_token = ?", (token,)).fetchone()
    if user is None:
        abort(404)
    return user


@app.route("/api/<token>/chasses")
def api_hunts(token):
    """Chasses en cours du compte (pour choisir la chasse dans les programmes du dossier tools/)."""
    user = api_user(token)
    rows = get_db().execute("SELECT * FROM hunts WHERE user_id = ? ORDER BY id DESC", (user["id"],))
    return {"chasses": [
        {"id": h["id"], "species": h["species"], "game": h["game_label"], "method": h["method"],
         "mode": h["mode"], "count": h["count"]}
        for h in map(hunt_view, rows)
    ]}


@app.route("/api/<token>/chasse/<int:hunt_id>", methods=["POST"])
def api_hunt(token, hunt_id):
    """{"action": "plus" | "moins" | "timer" | "start" | "pause"} -> état de la chasse."""
    user = api_user(token)
    db = get_db()
    hunt = db.execute("SELECT * FROM hunts WHERE id = ? AND user_id = ?", (hunt_id, user["id"])).fetchone()
    if hunt is None:
        abort(404)
    action = (request.get_json(silent=True) or {}).get("action")
    if action in ("plus", "moins"):
        sign = 1 if action == "plus" else -1
        add_encounters(db, hunt, sign * hunt["step"])
    elif action in ("timer", "start", "pause"):
        running = hunt["started_at"] is not None
        if action == "timer":
            action = "pause" if running else "start"
        if action == "start" and not running:
            db.execute("UPDATE hunts SET started_at = ? WHERE id = ?", (int(time.time()), hunt_id))
        elif action == "pause" and running:
            pause_timer(db, hunt)
    else:
        return {"erreur": "action inconnue (plus, moins, timer, start, pause)"}, 400
    db.commit()
    h = hunt_view(db.execute("SELECT * FROM hunts WHERE id = ?", (hunt_id,)).fetchone())
    return {"id": h["id"], "species": h["species"], "mode": h["mode"], "count": h["count"],
            "elapsed": h["elapsed_now"], "running": h["started_at"] is not None}


@app.route("/compteur/<int:hunt_id>/delete", methods=["POST"])
@login_required
def hunt_delete(hunt_id):
    """Abandonne la chasse ; les phases déjà trouvées restent dans la collection."""
    get_own_hunt(hunt_id)
    db = get_db()
    db.execute("DELETE FROM hunts WHERE id = ?", (hunt_id,))
    db.commit()
    flash("Chasse abandonnée.", "success")
    return redirect(url_for("hunts"))


if __name__ == "__main__":
    app.run(debug=True)
