-- Wettbewerbe (Ligen / Pokale)
CREATE TABLE competitions (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    code        TEXT UNIQUE,
    area_name   TEXT
);

-- Saisons je Wettbewerb
CREATE TABLE seasons (
    id                  INTEGER PRIMARY KEY,
    competition_id      INTEGER REFERENCES competitions(id),
    start_date          DATE,
    end_date            DATE,
    current_matchday    INTEGER,
    winner_team_id      INTEGER  -- FK auf teams kommt später, da teams erst unten definiert wird
);

-- Teams
CREATE TABLE teams (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    short_name  TEXT,
    tla         TEXT,
    crest_url   TEXT
);

-- jetzt FK von seasons.winner_team_id nachtragen
ALTER TABLE seasons
    ADD CONSTRAINT fk_season_winner FOREIGN KEY (winner_team_id) REFERENCES teams(id);

-- Schiedsrichter
CREATE TABLE referees (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    nationality TEXT
);

-- Spiele -- zentrale Tabelle
CREATE TABLE matches (
    id                      INTEGER PRIMARY KEY,
    competition_id          INTEGER REFERENCES competitions(id),
    season_id               INTEGER REFERENCES seasons(id),
    matchday                INTEGER,
    stage                   TEXT,
    group_name               TEXT,
    utc_date                 TIMESTAMP,
    status                   TEXT,
    home_team_id              INTEGER REFERENCES teams(id),
    away_team_id              INTEGER REFERENCES teams(id),
    home_score_fulltime        INTEGER,
    away_score_fulltime         INTEGER,
    home_score_halftime          INTEGER,
    away_score_halftime           INTEGER,
    winner                    TEXT,    -- HOME_TEAM, AWAY_TEAM, DRAW
    last_updated                TIMESTAMP,
    inserted_at                 TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_matches_competition ON matches(competition_id);
CREATE INDEX idx_matches_season ON matches(season_id);
CREATE INDEX idx_matches_teams ON matches(home_team_id, away_team_id);
CREATE INDEX idx_matches_status ON matches(status);

-- Zwischentabelle: ein Spiel kann mehrere Schiedsrichter haben
CREATE TABLE match_referees (
    match_id     INTEGER REFERENCES matches(id),
    referee_id   INTEGER REFERENCES referees(id),
    referee_type TEXT,   -- z.B. REFEREE, ASSISTANT_REFEREE_1
    PRIMARY KEY (match_id, referee_id, referee_type)
);
