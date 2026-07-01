import os
import json
import psycopg2
from psycopg2.extras import execute_values

# ---- Konfiguration ----
DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "fussball",
    "user":     "fussball",
    "password": "fussball_pw"
}

DATA_DIR = "data"


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


# ------------------------------------------------------------------ #
#  1. COMPETITIONS                                                     #
# ------------------------------------------------------------------ #
def load_competitions(cur, matches_data):
    comp = matches_data["competition"]
    area = matches_data.get("matches", [{}])[0].get("area", {})

    cur.execute("""
        INSERT INTO competitions (id, name, code, area_name)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (comp["id"], comp["name"], comp["code"], area.get("name")))

    print(f"  Competition: {comp['name']} ({comp['code']})")


# ------------------------------------------------------------------ #
#  2. TEAMS                                                            #
# ------------------------------------------------------------------ #
def load_teams(cur, teams_data):
    teams = teams_data.get("teams", [])
    count = 0
    for t in teams:
        cur.execute("""
            INSERT INTO teams (id, name, short_name, tla, crest_url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (t["id"], t["name"], t.get("shortName"), t.get("tla"), t.get("crest")))
        count += 1
    print(f"  Teams geladen: {count}")


# ------------------------------------------------------------------ #
#  3. SEASONS                                                          #
# ------------------------------------------------------------------ #
def load_seasons(cur, matches_data):
    season = matches_data["matches"][0]["season"]
    comp   = matches_data["competition"]

    cur.execute("""
        INSERT INTO seasons (id, competition_id, start_date, end_date, current_matchday)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (
        season["id"],
        comp["id"],
        season["startDate"],
        season["endDate"],
        season.get("currentMatchday")
    ))
    print(f"  Season: {season['startDate']} bis {season['endDate']}")


# ------------------------------------------------------------------ #
#  4. MATCHES                                                          #
# ------------------------------------------------------------------ #
def load_matches(cur, matches_data):
    matches = matches_data.get("matches", [])
    count = 0
    for m in matches:
        score     = m.get("score", {})
        full_time = score.get("fullTime", {})
        half_time = score.get("halfTime", {})

        cur.execute("""
            INSERT INTO matches (
                id, competition_id, season_id, matchday, stage, group_name,
                utc_date, status,
                home_team_id, away_team_id,
                home_score_fulltime, away_score_fulltime,
                home_score_halftime, away_score_halftime,
                winner, last_updated
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        """, (
            m["id"],
            m["competition"]["id"],
            m["season"]["id"],
            m.get("matchday"),
            m.get("stage"),
            m.get("group"),
            m.get("utcDate"),
            m.get("status"),
            m["homeTeam"]["id"],
            m["awayTeam"]["id"],
            full_time.get("home"),
            full_time.get("away"),
            half_time.get("home"),
            half_time.get("away"),
            score.get("winner"),
            m.get("lastUpdated")
        ))
        count += 1
    print(f"  Matches geladen: {count}")


# ------------------------------------------------------------------ #
#  5. REFEREES + MATCH_REFEREES                                        #
# ------------------------------------------------------------------ #
def load_referees(cur, matches_data):
    matches     = matches_data.get("matches", [])
    ref_count   = 0
    assoc_count = 0

    for m in matches:
        for r in m.get("referees", []):
            # Schiedsrichter einfügen (nur einmal, egal wie viele Spiele)
            cur.execute("""
                INSERT INTO referees (id, name, nationality)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (r["id"], r["name"], r.get("nationality")))
            ref_count += 1

            # Zuordnung Spiel <-> Schiedsrichter
            cur.execute("""
                INSERT INTO match_referees (match_id, referee_id, referee_type)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (m["id"], r["id"], r.get("type")))
            assoc_count += 1

    print(f"  Schiedsrichter-Einträge: {ref_count} (inkl. Duplikate ignoriert)")
    print(f"  Match-Schiedsrichter Zuordnungen: {assoc_count}")


# ------------------------------------------------------------------ #
#  MAIN                                                                #
# ------------------------------------------------------------------ #
def main():
    print("Lade JSON-Dateien...")
    with open(os.path.join(DATA_DIR, "matches_bl1.json"), encoding="utf-8") as f:
        matches_data = json.load(f)

    with open(os.path.join(DATA_DIR, "teams_bl1.json"), encoding="utf-8") as f:
        teams_data = json.load(f)

    print("Verbinde mit Datenbank...")
    conn = get_connection()
    cur  = conn.cursor()

    try:
        print("\n--- Lade Daten in DB ---")
        load_competitions(cur, matches_data)
        load_teams(cur, teams_data)
        load_seasons(cur, matches_data)
        load_matches(cur, matches_data)
        load_referees(cur, matches_data)

        conn.commit()
        print("\nFertig! Alle Daten erfolgreich gespeichert.")

    except Exception as e:
        conn.rollback()
        print(f"\nFehler: {e}")
        raise

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
