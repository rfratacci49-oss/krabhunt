CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
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

-- Phases d'une chasse : shiny de la collection trouvés avant la cible.
-- La cible est la « phase finale » ; un shiny ne peut être phase que d'une seule chasse.
CREATE TABLE IF NOT EXISTS hunt_phases (
    target_id  INTEGER NOT NULL REFERENCES shinies(id) ON DELETE CASCADE,
    shiny_id   INTEGER NOT NULL UNIQUE REFERENCES shinies(id) ON DELETE CASCADE,
    position   INTEGER NOT NULL,                  -- ordre d'apparition dans la chasse
    PRIMARY KEY (target_id, shiny_id)
);

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
    elapsed     INTEGER NOT NULL DEFAULT 0 CHECK (elapsed >= 0),  -- timer : secondes cumulées hors période en cours
    started_at  INTEGER,                          -- timer : heure de démarrage (epoch) ; NULL = en pause
    step        INTEGER NOT NULL DEFAULT 1 CHECK (step BETWEEN 1 AND 100),  -- ex. 5 pour les hordes
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_hunts_user ON hunts (user_id);

-- Phases trouvées pendant une chasse en cours (déjà ajoutées à la collection) ;
-- elles deviennent des hunt_phases quand la cible est capturée.
CREATE TABLE IF NOT EXISTS hunt_pending_phases (
    hunt_id   INTEGER NOT NULL REFERENCES hunts(id) ON DELETE CASCADE,
    shiny_id  INTEGER NOT NULL UNIQUE REFERENCES shinies(id) ON DELETE CASCADE,
    position  INTEGER NOT NULL,
    PRIMARY KEY (hunt_id, shiny_id)
);
