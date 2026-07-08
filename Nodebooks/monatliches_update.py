import requests
import psycopg2
from datetime import timedelta

# ---- Konfiguration ----
API_KEY     = "0a51501f0bc740b39ac6633ef6e913d9"
BASE_URL    = "https://api.football-data.org/v4"
COMPETITION = "BL1"
HEADERS     = {"X-Auth-Token": API_KEY}

DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "fussball",
    "user":     "fussball",
    "password": "fussball_pw"
}


# ------------------------------------------------------------------ #
#  DB LESEN                                                            #
# ------------------------------------------------------------------ #
def get_last_date(cur):
    """Letztes Spieldatum in der DB."""
    cur.execute("SELECT MAX(utc_date) FROM matches WHERE status = 'FINISHED'")
    result = cur.fetchone()[0]
    return result


def get_current_season_id(cur):
    """Aktuelle Season ID aus der DB."""
    cur.execute("SELECT id FROM seasons ORDER BY start_date DESC LIMIT 1")
    result = cur.fetchone()
    return result[0] if result else None


# ------------------------------------------------------------------ #
#  API                                                                 #
# ------------------------------------------------------------------ #
def fetch_new_matches(last_date):
    """Holt alle Spiele seit dem letzten Datum."""
    date_from = (last_date - timedelta(days=1)).strftime('%Y-%m-%d')
    url = f"{BASE_URL}/competitions/{COMPETITION}/matches?dateFrom={date_from}&status=FINISHED"
    print(f"  Hole Spiele ab {date_from}...")
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"  Fehler: {resp.status_code}")
        return []
    matches = resp.json().get("matches", [])
    print(f"  {len(matches)} Spiele gefunden")
    return matches


def fetch_teams():
    """Aktuelle Teams holen."""
    url = f"{BASE_URL}/competitions/{COMPETITION}/teams"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return []
    return resp.json().get("teams", [])


# ------------------------------------------------------------------ #
#  UPSERT FUNKTIONEN                                                   #
# ------------------------------------------------------------------ #
def upsert_competition(cur, match):
    comp = match["competition"]
    area = match.get("area", {})
    cur.execute("""
        INSERT INTO competitions (id, name, code, area_name)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            name      = EXCLUDED.name,
            code      = EXCLUDED.code,
            area_name = EXCLUDED.area_name
    """, (comp["id"], comp["name"], comp["code"], area.get("name")))


def upsert_season(cur, match):
    s    = match["season"]
    comp = match["competition"]
    cur.execute("""
        INSERT INTO seasons (id, competition_id, start_date, end_date, current_matchday)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            current_matchday = EXCLUDED.current_matchday
    """, (s["id"], comp["id"], s["startDate"], s["endDate"], s.get("currentMatchday")))


def upsert_teams(cur, teams):
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
    print(f"  {len(teams)} Teams aktualisiert")


def upsert_match(cur, m):
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
        m["id"], m["competition"]["id"], m["season"]["id"],
        m.get("matchday"), m.get("stage"), m.get("group"),
        m.get("utcDate"), m.get("status"),
        m["homeTeam"]["id"], m["awayTeam"]["id"],
        full_time.get("home"), full_time.get("away"),
        half_time.get("home"), half_time.get("away"),
        score.get("winner"), m.get("lastUpdated")
    ))


def upsert_referees(cur, m):
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


# ------------------------------------------------------------------ #
#  MAIN                                                                #
# ------------------------------------------------------------------ #
def main():
    print("=== Update: Neue Spiele laden ===\n")

    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    try:
        # Letztes Datum in DB
        last_date = get_last_date(cur)
        if not last_date:
            print("Keine Spiele in DB — bitte zuerst load_data.py ausführen.")
            return
        print(f"Letztes Spieldatum in DB: {last_date.strftime('%Y-%m-%d')}")

        # Teams aktualisieren
        print("\n--- Teams ---")
        teams = fetch_teams()
        if teams:
            upsert_teams(cur, teams)

        # Neue Spiele holen
        print("\n--- Neue Spiele ---")
        matches = fetch_new_matches(last_date)

        if not matches:
            print("Keine neuen Spiele gefunden — DB ist aktuell.")
            conn.commit()
            return

        # Spiele laden
        neu = 0
        aktualisiert = 0
        for m in matches:
            upsert_competition(cur, m)
            upsert_season(cur, m)
            upsert_match(cur, m)
            upsert_referees(cur, m)
            neu += 1

        conn.commit()

        # Zusammenfassung
        new_last_date = get_last_date(cur)
        print(f"\n  {neu} Spiele verarbeitet")
        print(f"  Neues letztes Datum: {new_last_date.strftime('%Y-%m-%d')}")
        print("\nFertig! DB ist aktuell.")

    except Exception as e:
        conn.rollback()
        print(f"\nFehler: {e}")
        raise

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
