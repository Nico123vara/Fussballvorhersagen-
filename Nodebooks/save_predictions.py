import psycopg2
import pandas as pd
import pickle
import requests
from datetime import date, timedelta

# ─── Konfiguration ───────────────────────────────────────────────────────────
DB_CONFIG = {
    'host':     'localhost',
    'port':     5432,
    'dbname':   'fussball',
    'user':     'fussball',
    'password': 'fussball_pw'
}

API_KEY  = "0a51501f0bc740b39ac6633ef6e913d9"
BASE_URL = "https://api.football-data.org/v4"
HEADERS  = {"X-Auth-Token": API_KEY}


# ─── Tabelle erstellen ────────────────────────────────────────────────────────
def create_predictions_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id          SERIAL PRIMARY KEY,
            match_id    INTEGER REFERENCES matches(id),
            predicted   TEXT,
            prob_home   FLOAT,
            prob_draw   FLOAT,
            prob_away   FLOAT,
            created_at  TIMESTAMP DEFAULT now()
        )
    """)
    print("Tabelle predictions erstellt/vorhanden.")


# ─── Feature-Funktionen ───────────────────────────────────────────────────────
def get_prev_season_id(df, season_id):
    season_ids = sorted(df['season_id'].unique())
    idx = list(season_ids).index(season_id) if season_id in season_ids else -1
    return season_ids[idx - 1] if idx > 0 else season_id


def get_form(df, team_id, season_id, n=5):
    prev_sid = get_prev_season_id(df, season_id)
    spiele = df[
        ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
        (df['season_id'] >= prev_sid)
    ].tail(n)
    punkte = 0
    for _, s in spiele.iterrows():
        if s['home_team_id'] == team_id:
            if s['winner'] == 'HOME_TEAM': punkte += 3
            elif s['winner'] == 'DRAW': punkte += 1
        else:
            if s['winner'] == 'AWAY_TEAM': punkte += 3
            elif s['winner'] == 'DRAW': punkte += 1
    return punkte


def get_home_form(df, team_id, season_id, n=5):
    prev_sid = get_prev_season_id(df, season_id)
    spiele = df[
        (df['home_team_id'] == team_id) &
        (df['season_id'] >= prev_sid)
    ].tail(n)
    punkte = 0
    for _, s in spiele.iterrows():
        if s['winner'] == 'HOME_TEAM': punkte += 3
        elif s['winner'] == 'DRAW': punkte += 1
    return punkte


def get_away_form(df, team_id, season_id, n=5):
    prev_sid = get_prev_season_id(df, season_id)
    spiele = df[
        (df['away_team_id'] == team_id) &
        (df['season_id'] >= prev_sid)
    ].tail(n)
    punkte = 0
    for _, s in spiele.iterrows():
        if s['winner'] == 'AWAY_TEAM': punkte += 3
        elif s['winner'] == 'DRAW': punkte += 1
    return punkte


def get_heimquote(df, team_id, season_id, n=12):
    prev_sid = get_prev_season_id(df, season_id)
    spiele = df[
        (df['home_team_id'] == team_id) &
        (df['season_id'] >= prev_sid)
    ].tail(n)
    if len(spiele) == 0:
        return 0.5
    return (spiele['winner'] == 'HOME_TEAM').mean()


def get_win_streak(df, team_id, season_id):
    prev_sid = get_prev_season_id(df, season_id)
    spiele = df[
        ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
        (df['season_id'] >= prev_sid)
    ].sort_values('utc_date', ascending=False)
    streak = 0
    for _, s in spiele.iterrows():
        gewonnen = (
            (s['home_team_id'] == team_id and s['winner'] == 'HOME_TEAM') or
            (s['away_team_id'] == team_id and s['winner'] == 'AWAY_TEAM')
        )
        if gewonnen: streak += 1
        else: break
    return streak


def get_goal_diff(df, team_id, season_id, n=5):
    prev_sid = get_prev_season_id(df, season_id)
    spiele = df[
        ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
        (df['season_id'] >= prev_sid)
    ].tail(n)
    if len(spiele) == 0:
        return 0
    diff = 0
    for _, s in spiele.iterrows():
        if s['home_team_id'] == team_id:
            diff += s['home_score_fulltime'] - s['away_score_fulltime']
        else:
            diff += s['away_score_fulltime'] - s['home_score_fulltime']
    return diff / len(spiele)


def is_promoted(df, team_id, season_id, matchday):
    if matchday > 5:
        return 0
    prev_sid = get_prev_season_id(df, season_id)
    if prev_sid == season_id:
        return 0
    vorherige = df[
        ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
        (df['season_id'] == prev_sid)
    ]
    return 1 if len(vorherige) == 0 else 0


def make_prediction(df, model_data, home_id, away_id, season_id, matchday):
    model    = model_data['model']
    features = model_data['features']

    beispiel = pd.DataFrame([{
        'home_form':        get_form(df, home_id, season_id),
        'away_form':        get_form(df, away_id, season_id),
        'home_form_home':   get_home_form(df, home_id, season_id),
        'away_form_away':   get_away_form(df, away_id, season_id),
        'heimquote':        get_heimquote(df, home_id, season_id),
        'home_streak':      get_win_streak(df, home_id, season_id),
        'away_streak':      get_win_streak(df, away_id, season_id),
        'home_goal_diff':   get_goal_diff(df, home_id, season_id),
        'away_goal_diff':   get_goal_diff(df, away_id, season_id),
        'is_promoted_home': is_promoted(df, home_id, season_id, matchday),
        'is_promoted_away': is_promoted(df, away_id, season_id, matchday)
    }])[features]

    probs   = model.predict_proba(beispiel)[0]
    klassen = model.classes_

    prob_dict = {k: p for k, p in zip(klassen, probs)}
    beste     = max(prob_dict, key=prob_dict.get)

    label_map = {1: 'HOME_TEAM', 0: 'DRAW', -1: 'AWAY_TEAM'}

    return {
        'predicted': label_map[beste],
        'prob_home': prob_dict.get(1, 0),
        'prob_draw': prob_dict.get(0, 0),
        'prob_away': prob_dict.get(-1, 0)
    }


# ─── Hauptfunktion ────────────────────────────────────────────────────────────
def main():
    print("=== Vorhersagen speichern ===\n")

    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    # Tabelle erstellen falls nicht vorhanden
    create_predictions_table(cur)
    conn.commit()

    # Modell laden
    with open('data/model.pkl', 'rb') as f:
        model_data = pickle.load(f)
    print("Modell geladen.")

    # Alle FINISHED Spiele aus DB laden (für Features)
    query = """
        SELECT
            m.id, m.utc_date, m.matchday, m.season_id,
            m.home_team_id, m.away_team_id,
            m.home_score_fulltime, m.away_score_fulltime,
            m.winner, m.status
        FROM matches m
        WHERE m.status = 'FINISHED'
        ORDER BY m.utc_date ASC
    """
    df = pd.read_sql(query, conn)
    df['utc_date'] = pd.to_datetime(df['utc_date'])
    current_season_id = df['season_id'].max()
    print(f"Spiele geladen: {len(df)}")

    # Kommende Spiele von API holen
    heute           = date.today()
    naechste_wochen = heute + timedelta(days=28)
    resp = requests.get(
        f"{BASE_URL}/competitions/BL1/matches"
        f"?dateFrom={heute}&dateTo={naechste_wochen}&status=SCHEDULED",
        headers=HEADERS
    )

    if resp.status_code != 200:
        print(f"API Fehler: {resp.status_code}")
        return

    upcoming = resp.json().get("matches", [])
    print(f"Kommende Spiele: {len(upcoming)}")

    if not upcoming:
        print("Keine kommenden Spiele — Sommerpause.")
        return

    # Vorhersagen berechnen und speichern
    gespeichert = 0
    übersprungen = 0

    for m in upcoming:
        match_id  = m['id']
        home_id   = m['homeTeam']['id']
        away_id   = m['awayTeam']['id']
        matchday  = m.get('matchday', 99)

        # Prüfen ob Vorhersage schon existiert
        cur.execute("SELECT id FROM predictions WHERE match_id = %s", (match_id,))
        if cur.fetchone():
            übersprungen += 1
            continue

        # Prüfen ob Teams in DB sind
        cur.execute("SELECT id FROM teams WHERE id = %s", (home_id,))
        if not cur.fetchone():
            print(f"  Team {home_id} nicht in DB — übersprungen")
            continue

        cur.execute("SELECT id FROM teams WHERE id = %s", (away_id,))
        if not cur.fetchone():
            print(f"  Team {away_id} nicht in DB — übersprungen")
            continue

        # Vorhersage berechnen
        pred = make_prediction(df, model_data, home_id, away_id, current_season_id, matchday)

        # In DB speichern
        cur.execute("""
            INSERT INTO predictions (match_id, predicted, prob_home, prob_draw, prob_away)
            VALUES (%s, %s, %s, %s, %s)
        """, (match_id, pred['predicted'], pred['prob_home'], pred['prob_draw'], pred['prob_away']))

        gespeichert += 1
        print(f"  Spiel {match_id}: {pred['predicted']} ({pred['prob_home']*100:.0f}% / {pred['prob_draw']*100:.0f}% / {pred['prob_away']*100:.0f}%)")

    conn.commit()
    print(f"\nGespeichert: {gespeichert} | Übersprungen: {übersprungen}")

    # Aktuelle Genauigkeit berechnen
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN p.predicted = m.winner THEN 1 ELSE 0 END) AS korrekt
        FROM predictions p
        JOIN matches m ON p.match_id = m.id
        WHERE m.status = 'FINISHED'
    """)
    result = cur.fetchone()
    if result and result[0] > 0:
        total   = result[0]
        korrekt = result[1]
        print(f"\nAktuelle Genauigkeit: {korrekt}/{total} = {korrekt/total*100:.1f}%")
    else:
        print("\nNoch keine abgeschlossenen Spiele mit Vorhersagen.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
