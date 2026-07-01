import os
import json
import psycopg2

# ---- Konfiguration ----
DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "fussball",
    "user":     "fussball",
    "password": "fussball_pw"
}

DATA_DIR = "data"
SEASONS  = [2023, 2024, 2025]


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def load_teams(cur, season: int):
    filepath = os.path.join(DATA_DIR, f"teams_bl1_{season}.json")
    with open(filepath, encoding="utf-8") as f:
        teams = json.load(f).get("teams", [])

    for t in teams:
        cur.execute("""
            INSERT INTO teams (id, name, short_name, tla, crest_url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name       = EXCLUDED.name,
                short_name = EXCLUDED.short_name,
                tla        = EXCLUDED.tla,
                crest_url  = EXCLUDED.crest_url
        """, (t["id"], t["name"], t.get("shortName"), t.get("tla"), t.get("crest")))

    print(f"  Teams Saison {season}: {len(teams)} geladen")


def load_matches(cur, season: int):
    filepath = os.path.join(DATA_DIR, f"matches_bl1_{season}.json")
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    matches = data.get("matches", [])
    if not matches:
        print(f"  Keine Spiele für Saison {season}")
        return

    # Competition
    comp = data["competition"]
    area = matches[0].get("area", {})
    cur.execute("""
        INSERT INTO competitions (id, name, code, area_name)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (comp["id"], comp["name"], comp["code"], area.get("name")))

    # Season
    s = matches[0]["season"]
    cur.execute("""
        INSERT INTO seasons (id, competition_id, start_date, end_date, current_matchday)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            current_matchday = EXCLUDED.current_matchday
    """, (s["id"], comp["id"], s["startDate"], s["endDate"], s.get("currentMatchday")))

    # Matches + Referees
    for m in matches:
        score     = m.get("score", {})
        full_time = score.get("fullTime", {})
        half_time = score.get("halfTime", {})

        cur.execute("""
            INSERT INTO matches (
                id, competition_id, season_id, matchday, stage, group_name,
                utc_date, status, home_team_id, away_team_id,
                home_score_fulltime, away_score_fulltime,
                home_score_halftime, away_score_halftime,
                winner, last_updated
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                status              = EXCLUDED.status,
                home_score_fulltime = EXCLUDED.home_score_fulltime,
                away_score_fulltime = EXCLUDED.away_score_fulltime,
                home_score_halftime = EXCLUDED.home_score_halftime,
                away_score_halftime = EXCLUDED.away_score_halftime,
                winner              = EXCLUDED.winner,
                last_updated        = EXCLUDED.last_updated
        """, (
            m["id"], comp["id"], s["id"],
            m.get("matchday"), m.get("stage"), m.get("group"),
            m.get("utcDate"), m.get("status"),
            m["homeTeam"]["id"], m["awayTeam"]["id"],
            full_time.get("home"), full_time.get("away"),
            half_time.get("home"), half_time.get("away"),
            score.get("winner"), m.get("lastUpdated")
        ))

        # Schiedsrichter
        for r in m.get("referees", []):
            cur.execute("""
                INSERT INTO referees (id, name, nationality)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name        = EXCLUDED.name,
                    nationality = EXCLUDED.nationality
            """, (r["id"], r["name"], r.get("nationality")))

            cur.execute("""
                INSERT INTO match_referees (match_id, referee_id, referee_type)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (m["id"], r["id"], r.get("type")))

    print(f"  Spiele Saison {season}: {len(matches)} geladen")


def main():
    print("Verbinde mit Datenbank...")
    conn = get_connection()
    cur  = conn.cursor()

    try:
        for season in SEASONS:
            print(f"\n--- Saison {season}/{str(season+1)[-2:]} ---")
            load_teams(cur, season)
            load_matches(cur, season)

        conn.commit()

        # Zusammenfassung
        cur.execute("SELECT COUNT(*) FROM matches")
        total_matches = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM teams")
        total_teams = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM referees")
        total_refs = cur.fetchone()[0]

        print(f"\n=== Zusammenfassung ===")
        print(f"  Spiele total:      {total_matches}")
        print(f"  Teams total:       {total_teams}")
        print(f"  Schiedsrichter:    {total_refs}")
        print("\nFertig!")

    except Exception as e:
        conn.rollback()
        print(f"\nFehler: {e}")
        raise

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
