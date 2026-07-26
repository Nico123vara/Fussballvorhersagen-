import json
import os
import psycopg2

# ─── Konfiguration ───────────────────────────────────────────────────────────
DB_CONFIG = {
    'host':     'localhost',
    'port':     5432,
    'dbname':   'fussball',
    'user':     'fussball',
    'password': 'fussball_pw'
}

# file_prefix = wie die Dateien heissen (bl1, PL, SA)
LIGEN = {
    'BL1': {'saisons': [2023, 2024, 2025], 'file_prefix': 'bl1'},
    'PL':  {'saisons': [2023, 2024, 2025], 'file_prefix': 'PL'},
    'SA':  {'saisons': [2023, 2024, 2025], 'file_prefix': 'SA'},
}


def get_connection():
    database_url = os.environ.get('DATABASE_URL', None)
    if database_url:
        print("  Verbinde mit Railway DB...")
        return psycopg2.connect(database_url)
    print("  Verbinde mit lokaler DB...")
    return psycopg2.connect(**DB_CONFIG)


def upsert_competition(cur, comp, area):
    cur.execute("""
        INSERT INTO competitions (id, name, code, area_name)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name, code = EXCLUDED.code, area_name = EXCLUDED.area_name
    """, (comp['id'], comp['name'], comp['code'], area.get('name')))


def upsert_team(cur, t):
    cur.execute("""
        INSERT INTO teams (id, name, short_name, tla, crest_url)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name, short_name = EXCLUDED.short_name,
            tla = EXCLUDED.tla, crest_url = EXCLUDED.crest_url
    """, (t['id'], t['name'], t.get('shortName'), t.get('tla'), t.get('crest')))


def upsert_season(cur, s, competition_id):
    cur.execute("""
        INSERT INTO seasons (id, competition_id, start_date, end_date, current_matchday)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET current_matchday = EXCLUDED.current_matchday
    """, (s['id'], competition_id, s['startDate'], s['endDate'], s.get('currentMatchday')))


def upsert_match(cur, m):
    score     = m.get('score', {})
    full_time = score.get('fullTime', {})
    half_time = score.get('halfTime', {})
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
        m['id'], m['competition']['id'], m['season']['id'],
        m.get('matchday'), m.get('stage'), m.get('group'),
        m.get('utcDate'), m.get('status'),
        m['homeTeam']['id'], m['awayTeam']['id'],
        full_time.get('home'), full_time.get('away'),
        half_time.get('home'), half_time.get('away'),
        score.get('winner'), m.get('lastUpdated')
    ))


def upsert_referee(cur, r, match_id):
    cur.execute("""
        INSERT INTO referees (id, name, nationality)
        VALUES (%s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
    """, (r['id'], r['name'], r.get('nationality')))
    cur.execute("""
        INSERT INTO match_referees (match_id, referee_id, referee_type)
        VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
    """, (match_id, r['id'], r.get('type')))


def load_liga(cur, liga_code, info):
    print(f"\n--- {liga_code} ---")
    prefix = info['file_prefix']
    total_matches = 0

    for saison in info['saisons']:
        # Teams laden
        teams_path = f"data/teams_{prefix}_{saison}.json"
        if os.path.exists(teams_path):
            with open(teams_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for t in data.get('teams', []):
                upsert_team(cur, t)
            print(f"  {saison}: {len(data.get('teams', []))} Teams geladen")
        else:
            print(f"  {saison}: {teams_path} nicht gefunden!")

        # Matches laden
        matches_path = f"data/matches_{prefix}_{saison}.json"
        if os.path.exists(matches_path):
            with open(matches_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            comp = data.get('competition', {})
            area = data.get('area', {})
            upsert_competition(cur, comp, area)

            matches = data.get('matches', [])
            for m in matches:
                upsert_season(cur, m['season'], comp['id'])
                upsert_match(cur, m)
                for r in m.get('referees', []):
                    upsert_referee(cur, r, m['id'])

            finished = len([m for m in matches if m['status'] == 'FINISHED'])
            print(f"  {saison}: {len(matches)} Spiele ({finished} FINISHED)")
            total_matches += len(matches)
        else:
            print(f"  {saison}: {matches_path} nicht gefunden!")

    return total_matches


def main():
    print("=== Daten in DB laden ===\n")

    conn = get_connection()
    cur  = conn.cursor()

    total = 0
    try:
        for liga_code, info in LIGEN.items():
            total += load_liga(cur, liga_code, info)

        conn.commit()
        print(f"\nFertig! {total} Spiele total geladen.")

        cur.execute("SELECT COUNT(*) FROM matches WHERE status = 'FINISHED'")
        print(f"FINISHED Spiele in DB: {cur.fetchone()[0]}")

    except Exception as e:
        conn.rollback()
        print(f"Fehler: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
