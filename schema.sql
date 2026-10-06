CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    stream_token  TEXT,                           -- adresse secrète du mode stream (OBS)
    api_token     TEXT,                           -- clé des raccourcis globaux (tools/krabhunt_raccourcis.py)
    created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS shinies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id),     -- propriétaire du shiny
    species_id  INTEGER NOT NULL,                 -- n° du Pokédex national
    form        TEXT,                             -- clé de forme (data/forms_fr.json) ; NULL = forme de base
    game        TEXT    NOT NULL,                 -- clé de pokemon.GAMES
    method      TEXT    NOT NULL,
    gender      TEXT    NOT NULL CHECK (gender IN ('M', 'F', 'N')),
    caught_on   TEXT,                             -- date ISO (AAAA-MM-JJ)
    nickname    TEXT,
    encounters  INTEGER CHECK (encounters >= 0),  -- nombre de rencontres
    duration    INTEGER CHECK (duration >= 0),    -- temps de chasse en secondes (chasse au timer)
    ball        TEXT,                             -- clé de pokemon.BALLS
    location    TEXT,                             -- lieu de capture (texte libre)
    shiny_charm INTEGER NOT NULL DEFAULT 0 CHECK (shiny_charm IN (0, 1)),  -- charme chroma possédé
    notes       TEXT,
    sprite_url  TEXT,                             -- facultatif : remplace le sprite automatique
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Phases d'une chasse : shiny de la collection ou shiny manqués trouvés avant la cible.
-- La cible est la « phase finale » ; un shiny (ou un manqué) ne peut être phase que d'une seule chasse.
CREATE TABLE IF NOT EXISTS hunt_phases (
    target_id  INTEGER NOT NULL REFERENCES shinies(id) ON DELETE CASCADE,
    shiny_id   INTEGER UNIQUE REFERENCES shinies(id) ON DELETE CASCADE,
    fail_id    INTEGER UNIQUE REFERENCES fails(id) ON DELETE CASCADE,
    position   INTEGER NOT NULL,                  -- ordre d'apparition dans la chasse
    CHECK ((shiny_id IS NULL) != (fail_id IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_hunt_phases_target ON hunt_phases (target_id);

-- Compteur : chasses en cours. À la capture de la cible, la chasse devient un shiny
-- de la collection et la ligne est supprimée.
CREATE TABLE IF NOT EXISTS hunts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    species_id  INTEGER NOT NULL,                 -- Pokémon ciblé
    form        TEXT,                             -- forme ciblée ; NULL = forme de base
    game        TEXT    NOT NULL,                 -- clé de pokemon.GAMES
    method      TEXT    NOT NULL,
    location    TEXT,                             -- lieu de la chasse
    shiny_charm INTEGER NOT NULL DEFAULT 0 CHECK (shiny_charm IN (0, 1)),
    mode        TEXT    NOT NULL DEFAULT 'count' CHECK (mode IN ('count', 'timer')),  -- rencontres ou timer
    count       INTEGER NOT NULL DEFAULT 0 CHECK (count >= 0),
    elapsed     INTEGER NOT NULL DEFAULT 0 CHECK (elapsed >= 0),  -- secondes cumulées (timer, ou temps actif d'une chasse aux rencontres)
    started_at  INTEGER,                          -- timer : heure de démarrage (epoch) ; NULL = en pause
    last_tick   INTEGER,                          -- rencontres : heure du dernier clic (epoch), pour le temps actif
    step        INTEGER NOT NULL DEFAULT 1 CHECK (step BETWEEN 1 AND 100),  -- ex. 5 pour les hordes
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_hunts_user ON hunts (user_id);

-- Phases trouvées pendant une chasse en cours (déjà ajoutées à la collection) ;
-- elles deviennent des hunt_phases quand la cible est capturée.
CREATE TABLE IF NOT EXISTS hunt_pending_phases (
    hunt_id   INTEGER NOT NULL REFERENCES hunts(id) ON DELETE CASCADE,
    shiny_id  INTEGER UNIQUE REFERENCES shinies(id) ON DELETE CASCADE,
    fail_id   INTEGER UNIQUE REFERENCES fails(id) ON DELETE CASCADE,
    position  INTEGER NOT NULL,
    CHECK ((shiny_id IS NULL) != (fail_id IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_hunt_pending_phases_hunt ON hunt_pending_phases (hunt_id);

-- Shiny manqués (fuite, K.O. par erreur…) : gardés à part, ils ne comptent pas dans la collection
CREATE TABLE IF NOT EXISTS fails (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    species_id  INTEGER NOT NULL,
    form        TEXT,
    game        TEXT    NOT NULL,                 -- clé de pokemon.GAMES (décide de la collection)
    method      TEXT    NOT NULL,
    gender      TEXT    CHECK (gender IN ('M', 'F', 'N')),  -- NULL = inconnu
    encounters  INTEGER CHECK (encounters >= 0),
    duration    INTEGER CHECK (duration >= 0),
    location    TEXT,
    shiny_charm INTEGER NOT NULL DEFAULT 0 CHECK (shiny_charm IN (0, 1)),
    reason      TEXT,                             -- motif du fail
    failed_on   TEXT,                             -- date ISO
    notes       TEXT,
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_fails_user ON fails (user_id);
