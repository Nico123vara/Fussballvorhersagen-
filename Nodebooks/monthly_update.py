import requests
import psycopg2
import os
from datetime import timedelta
from time import sleep

API_KEY  = "0a51501f0bc740b39ac6633ef6e913d9"
BASE_URL = "https://api.football-data.org/v4"
HEADERS  = {"X-Auth-Token": API_KEY}

LIGEN = ['BL1', 'PL', 'SA']

DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "fussball",
    "user":     "fussball",
    "password": "fussball_pw"
}


def get_connection():
    database_url = os.environ.get('DATABASE_URL', None)
    if database_url:
        print("  Verbinde mit Railway DB...")
        return psycopg2.connect(database_url)
    print("  Verbinde mit lokaler DB...")
    return psycopg2.connect(**DB_CONFIG)


def get_last_date(cur, liga_code):
    cur.execute("""
        SELECT MAX(m.utc_date)
        FROM matches m
        JOIN competitions c ON m.competition_id = c.id
        WHERE m.status = 'FINISHED' AND c.code = %s
    """, (liga_code,))
    return cur.fetchone()[0]


def fetch_new_matches(liga_code, last_date):
    date_from = (last_date - timedelta(days=1)).strftime('%Y-%m-%d')
    url = f"{BASE_URL}/competitions/{liga_code}/matches?dateFrom={date_from}&status=FINISHED"
    print(f"  Hole {liga_code} Spiele ab {date_from}...")
    resp = requests.get(url, headers=HEADERS)
    sleep(6)
    if resp.status_code != 200:
        print(f"  Fehler: {resp.status_code}")
        return []
    matches = resp.json().get("matches", [])
    print(f"  {len(matches)} Spiele gefunden")
    return matches


def fetch_teams(liga_code):
    url = f"{BASE_URL}/competitions/{liga_code}/teams"
    resp = requests.get(url, headers=HEADERS)
    sleep(6)
    if resp.status_code != 200:
        return []
    return resp.json().get("teams", [])


def upsert_competition(cur, match):
    comp = match["competition"]
    area = match.get("area", {})
    cur.execute("""
        INSERT INTO competitions (id, name, code, area_name)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, code = EXCLUDED.code
    """, (comp["id"], comp["name"], comp["code"], area.get("name")))


def upsert_season(cur, match):
    s    = match["season"]
    comp = match["competition"]
    cur.execute("""
        INSERT INTO seasons (id, competition_id, start_date, end_date, current_matchday)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET current_matchday = EXCLUDED.current_matchday
    """, (s["id"], comp["id"], s["startDate"], s["endDate"], s.get("currentMatchday")))


def upsert_teams(cur, teams):
    for t in teams:
        cur.execute("""
            INSERT INTO teams (id, name, short_name, tla, crest_url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
        """, (t["id"], t["name"], t.get("shortName"), t.get("tla"), t.get("crest")))


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
            status = EXCLUDED.status,
            home_score_fulltime = EXCLUDED.home_score_fulltime,
            away_score_fulltime = EXCLUDED.away_score_fulltime,
            winner = EXCLUDED.winner,
            last_updated = EXCLUDED.last_updated
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
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
        """, (r["id"], r["name"], r.get("nationality")))
        cur.execute("""
            INSERT INTO match_referees (match_id, referee_id, referee_type)
            VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
        """, (m["id"], r["id"], r.get("type")))


def update_liga(cur, liga_code):
    print(f"\n--- {liga_code} ---")

    last_date = get_last_date(cur, liga_code)
    if not last_date:
        print(f"  Keine Daten für {liga_code} in DB")
        return 0

    print(f"  Letztes Datum: {last_date.strftime('%Y-%m-%d')}")

    teams = fetch_teams(liga_code)
    if teams:
        upsert_teams(cur, teams)
        print(f"  {len(teams)} Teams aktualisiert")

    matches = fetch_new_matches(liga_code, last_date)
    for m in matches:
        upsert_competition(cur, m)
        upsert_season(cur, m)
        upsert_match(cur, m)
        upsert_referees(cur, m)

    return len(matches)


def main():
    print("=== Update: Alle Ligen ===\n")

    conn = get_connection()
    cur  = conn.cursor()

    try:
        total = 0
        for liga_code in LIGEN:
            total += update_liga(cur, liga_code)

        conn.commit()
        print(f"\nFertig! {total} Spiele total verarbeitet.")

    except Exception as e:
        conn.rollback()
        print(f"\nFehler: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
