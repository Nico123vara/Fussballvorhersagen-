import psycopg2

DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "fussball",
    "user":     "fussball",
    "password": "fussball_pw"
}

STATEMENTS = [
    # competitions
    "CREATE TABLE IF NOT EXISTS competitions (id INTEGER, name TEXT NOT NULL, code TEXT, area_name TEXT)",
    "ALTER TABLE competitions ADD CONSTRAINT pk_competitions PRIMARY KEY (id)",
    "ALTER TABLE competitions ADD CONSTRAINT uq_competitions_code UNIQUE (code)",

    # seasons (ohne winner FK, kommt nach teams)
    "CREATE TABLE IF NOT EXISTS seasons (id INTEGER, competition_id INTEGER, start_date DATE, end_date DATE, current_matchday INTEGER, winner_team_id INTEGER)",
    "ALTER TABLE seasons ADD CONSTRAINT pk_seasons PRIMARY KEY (id)",
    "ALTER TABLE seasons ADD CONSTRAINT fk_seasons_competition FOREIGN KEY (competition_id) REFERENCES competitions(id)",

    # teams
    "CREATE TABLE IF NOT EXISTS teams (id INTEGER, name TEXT NOT NULL, short_name TEXT, tla TEXT, crest_url TEXT)",
    "ALTER TABLE teams ADD CONSTRAINT pk_teams PRIMARY KEY (id)",

    # seasons winner FK jetzt möglich
    "ALTER TABLE seasons ADD CONSTRAINT fk_seasons_winner FOREIGN KEY (winner_team_id) REFERENCES teams(id)",

    # referees
    "CREATE TABLE IF NOT EXISTS referees (id INTEGER, name TEXT NOT NULL, nationality TEXT)",
    "ALTER TABLE referees ADD CONSTRAINT pk_referees PRIMARY KEY (id)",

    # matches
    """CREATE TABLE IF NOT EXISTS matches (
        id INTEGER, competition_id INTEGER, season_id INTEGER,
        matchday INTEGER, stage TEXT, group_name TEXT,
        utc_date TIMESTAMP, status TEXT,
        home_team_id INTEGER, away_team_id INTEGER,
        home_score_fulltime INTEGER, away_score_fulltime INTEGER,
        home_score_halftime INTEGER, away_score_halftime INTEGER,
        winner TEXT, last_updated TIMESTAMP, inserted_at TIMESTAMP DEFAULT now()
    )""",
    "ALTER TABLE matches ADD CONSTRAINT pk_matches PRIMARY KEY (id)",
    "ALTER TABLE matches ADD CONSTRAINT fk_matches_competition FOREIGN KEY (competition_id) REFERENCES competitions(id)",
    "ALTER TABLE matches ADD CONSTRAINT fk_matches_season FOREIGN KEY (season_id) REFERENCES seasons(id)",
    "ALTER TABLE matches ADD CONSTRAINT fk_matches_home_team FOREIGN KEY (home_team_id) REFERENCES teams(id)",
    "ALTER TABLE matches ADD CONSTRAINT fk_matches_away_team FOREIGN KEY (away_team_id) REFERENCES teams(id)",

    # match_referees
    "CREATE TABLE IF NOT EXISTS match_referees (match_id INTEGER, referee_id INTEGER, referee_type TEXT)",
    "ALTER TABLE match_referees ADD CONSTRAINT pk_match_referees PRIMARY KEY (match_id, referee_id, referee_type)",
    "ALTER TABLE match_referees ADD CONSTRAINT fk_match_refs_match FOREIGN KEY (match_id) REFERENCES matches(id)",
    "ALTER TABLE match_referees ADD CONSTRAINT fk_match_refs_referee FOREIGN KEY (referee_id) REFERENCES referees(id)",
]

def main():
    print("Verbinde mit Datenbank...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    try:
        for stmt in STATEMENTS:
            try:
                cur.execute(stmt)
                conn.commit()
            except psycopg2.errors.DuplicateTable:
                conn.rollback()
            except psycopg2.errors.DuplicateObject:
                conn.rollback()

        print("Fertig! Tabellen erstellt.")

        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = cur.fetchall()
        print("\nVorhandene Tabellen:")
        for t in tables:
            print(f"  - {t[0]}")

    except Exception as e:
        conn.rollback()
        print(f"Fehler: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
