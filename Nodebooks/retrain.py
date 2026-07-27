import pandas as pd
import psycopg2
import pickle
import os
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

DB_CONFIG = {
    'host':     'localhost',
    'port':     5432,
    'dbname':   'fussball',
    'user':     'fussball',
    'password': 'fussball_pw'
}

LIGEN = {
    'BL1': 'Bundesliga',
    'PL':  'Premier League',
    'SA':  'Serie A',
}

FEATURES = [
    'home_form', 'away_form',
    'home_form_home', 'away_form_away',
    'heimquote', 'home_streak', 'away_streak',
    'home_goal_diff', 'away_goal_diff',
    'is_promoted_home', 'is_promoted_away',
    'home_table_pos', 'away_table_pos'
]


def get_connection():
    database_url = os.environ.get('DATABASE_URL', None)
    if database_url:
        return psycopg2.connect(database_url)
    return psycopg2.connect(**DB_CONFIG)


def load_data(conn, liga_code):
    print(f"  Lade Daten für {liga_code}...")
    query = """
        SELECT m.id, m.utc_date, m.matchday, m.season_id,
               s.start_date AS season_start,
               m.home_team_id, m.away_team_id,
               m.home_score_fulltime, m.away_score_fulltime,
               m.winner
        FROM matches m
        JOIN seasons s ON m.season_id = s.id
        JOIN competitions c ON m.competition_id = c.id
        WHERE m.status = 'FINISHED' AND c.code = %s
        ORDER BY m.utc_date ASC
    """
    df = pd.read_sql(query, conn, params=(liga_code,))
    df['utc_date']     = pd.to_datetime(df['utc_date'])
    df['season_start'] = pd.to_datetime(df['season_start'])
    df['season']       = df['season_start'].dt.year
    print(f"  {len(df)} Spiele geladen")
    return df


def build_prev_season_map(df):
    season_ids = sorted(df['season_id'].unique())
    return {sid: season_ids[i-1] if i > 0 else sid for i, sid in enumerate(season_ids)}


def get_form(df, team_id, date, season_id, prev_map, n=5):
    prev_sid = prev_map.get(season_id, season_id)
    spiele = df[
        ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
        (df['utc_date'] < date) & (df['season_id'] >= prev_sid)
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


def get_home_form(df, team_id, date, season_id, prev_map, n=5):
    prev_sid = prev_map.get(season_id, season_id)
    spiele = df[(df['home_team_id'] == team_id) & (df['utc_date'] < date) & (df['season_id'] >= prev_sid)].tail(n)
    punkte = 0
    for _, s in spiele.iterrows():
        if s['winner'] == 'HOME_TEAM': punkte += 3
        elif s['winner'] == 'DRAW': punkte += 1
    return punkte


def get_away_form(df, team_id, date, season_id, prev_map, n=5):
    prev_sid = prev_map.get(season_id, season_id)
    spiele = df[(df['away_team_id'] == team_id) & (df['utc_date'] < date) & (df['season_id'] >= prev_sid)].tail(n)
    punkte = 0
    for _, s in spiele.iterrows():
        if s['winner'] == 'AWAY_TEAM': punkte += 3
        elif s['winner'] == 'DRAW': punkte += 1
    return punkte


def get_heimquote(df, team_id, date, season_id, prev_map, n=12):
    prev_sid = prev_map.get(season_id, season_id)
    spiele = df[(df['home_team_id'] == team_id) & (df['utc_date'] < date) & (df['season_id'] >= prev_sid)].tail(n)
    if len(spiele) == 0: return 0.5
    return (spiele['winner'] == 'HOME_TEAM').mean()


def get_win_streak(df, team_id, date, season_id, prev_map):
    prev_sid = prev_map.get(season_id, season_id)
    spiele = df[
        ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
        (df['utc_date'] < date) & (df['season_id'] >= prev_sid)
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


def get_goal_diff(df, team_id, date, season_id, prev_map, n=5):
    prev_sid = prev_map.get(season_id, season_id)
    spiele = df[
        ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
        (df['utc_date'] < date) & (df['season_id'] >= prev_sid)
    ].tail(n)
    if len(spiele) == 0: return 0
    diff = 0
    for _, s in spiele.iterrows():
        if s['home_team_id'] == team_id:
            diff += s['home_score_fulltime'] - s['away_score_fulltime']
        else:
            diff += s['away_score_fulltime'] - s['home_score_fulltime']
    return diff / len(spiele)


def is_promoted(df, team_id, season_id, matchday, prev_map):
    if matchday > 5: return 0
    prev_sid = prev_map.get(season_id, season_id)
    if prev_sid == season_id: return 0
    vorherige = df[
        ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
        (df['season_id'] == prev_sid)
    ]
    return 1 if len(vorherige) == 0 else 0


def get_table_position(df, team_id, date, season_id, matchday, prev_map):
    if is_promoted(df, team_id, season_id, matchday, prev_map) == 1:
        return 18
    spiele = df[(df['season_id'] == season_id) & (df['utc_date'] < date)]
    if len(spiele) == 0: return 10
    teams  = set(spiele['home_team_id'].tolist() + spiele['away_team_id'].tolist())
    punkte = {t: 0 for t in teams}
    for _, s in spiele.iterrows():
        h = s['home_team_id']
        a = s['away_team_id']
        if s['winner'] == 'HOME_TEAM': punkte[h] += 3
        elif s['winner'] == 'AWAY_TEAM': punkte[a] += 3
        elif s['winner'] == 'DRAW':
            punkte[h] += 1
            punkte[a] += 1
    sortiert   = sorted(punkte.items(), key=lambda x: -x[1])
    positionen = {t: i+1 for i, (t, _) in enumerate(sortiert)}
    return positionen.get(team_id, 10)


def compute_features(df):
    print("Berechne Features...")
    prev_map = build_prev_season_map(df)
    features = []
    for i, (_, row) in enumerate(df.iterrows()):
        if i % 100 == 0: print(f"  {i}/{len(df)}...")
        sid = row['season_id']
        hid = row['home_team_id']
        aid = row['away_team_id']
        dat = row['utc_date']
        md  = row['matchday']
        features.append({
            'match_id':         row['id'],
            'utc_date':         dat,
            'matchday':         md,
            'season_id':        sid,
            'season':           row['season'],
            'home_form':        get_form(df, hid, dat, sid, prev_map),
            'away_form':        get_form(df, aid, dat, sid, prev_map),
            'home_form_home':   get_home_form(df, hid, dat, sid, prev_map),
            'away_form_away':   get_away_form(df, aid, dat, sid, prev_map),
            'heimquote':        get_heimquote(df, hid, dat, sid, prev_map),
            'home_streak':      get_win_streak(df, hid, dat, sid, prev_map),
            'away_streak':      get_win_streak(df, aid, dat, sid, prev_map),
            'home_goal_diff':   get_goal_diff(df, hid, dat, sid, prev_map),
            'away_goal_diff':   get_goal_diff(df, aid, dat, sid, prev_map),
            'is_promoted_home': is_promoted(df, hid, sid, md, prev_map),
            'is_promoted_away': is_promoted(df, aid, sid, md, prev_map),
            'home_table_pos':   get_table_position(df, hid, dat, sid, md, prev_map),
            'away_table_pos':   get_table_position(df, aid, dat, sid, md, prev_map),
            'winner':           row['winner']
        })
    df_features = pd.DataFrame(features)
    print(f"  {len(df_features)} Spiele total")
    return df_features


def clean_features(df_features):
    df_features = df_features[df_features['season'] >= 2024]
    df_features = df_features[~((df_features['home_form'] == 0) & (df_features['away_form'] == 0))]
    df_features = df_features[~((df_features['home_form_home'] == 0) & (df_features['away_form_away'] == 0))]
    return df_features


def train_model(df_features):
    label_map = {'HOME_TEAM': 1, 'DRAW': 0, 'AWAY_TEAM': -1}
    df_features['target'] = df_features['winner'].map(label_map)
    df_features = df_features.dropna(subset=FEATURES + ['target'])
    train = df_features[
        (df_features['season'] == 2024) |
        ((df_features['season'] == 2025) & (df_features['matchday'] <= 17))
    ]
    test = df_features[(df_features['season'] == 2025) & (df_features['matchday'] > 17)]
    if len(test) == 0:
        split = int(len(df_features) * 0.8)
        train = df_features.iloc[:split]
        test  = df_features.iloc[split:]
    X_train = train[FEATURES]
    y_train = train['target']
    X_test  = test[FEATURES]
    y_test  = test['target']
    print(f"  Training: {len(train)} | Test: {len(test)}")
    baseline = accuracy_score(y_test, [1] * len(y_test))
    print(f"  Baseline: {baseline*100:.1f}%")
    lr = LogisticRegression(max_iter=1000, random_state=42)
    lr.fit(X_train, y_train)
    lr_acc = accuracy_score(y_test, lr.predict(X_test))
    print(f"  LR: {lr_acc*100:.1f}%")
    rf = RandomForestClassifier(n_estimators=100, random_state=42)
    rf.fit(X_train, y_train)
    rf_acc = accuracy_score(y_test, rf.predict(X_test))
    print(f"  RF: {rf_acc*100:.1f}%")
    best_model = rf if rf_acc >= lr_acc else lr
    best_name  = 'RF' if rf_acc >= lr_acc else 'LR'
    print(f"  Bestes: {best_name} ({max(rf_acc, lr_acc)*100:.1f}%)")
    return best_model


def save_model_to_db(conn, model, liga_code):
    """Modell als Bytes in DB speichern."""
    model_data  = {'model': model, 'features': FEATURES}
    model_bytes = pickle.dumps(model_data)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO models (name, data)
        VALUES (%s, %s)
        ON CONFLICT (name) DO UPDATE SET data = EXCLUDED.data, created_at = now()
    """, (liga_code, psycopg2.Binary(model_bytes)))
    conn.commit()
    cur.close()
    print(f"  Modell '{liga_code}' in DB gespeichert")


def main():
    print("=== Retrain — Alle Ligen ===\n")
    conn = get_connection()

    for liga_code, liga_name in LIGEN.items():
        print(f"--- {liga_name} ({liga_code}) ---")
        df          = load_data(conn, liga_code)
        df_features = compute_features(df)
        df_features = clean_features(df_features)
        print(f"  {len(df_features)} Spiele nach Bereinigung")
        model = train_model(df_features)
        save_model_to_db(conn, model, liga_code)
        print()

    conn.close()
    print("Fertig!")


if __name__ == "__main__":
    main()
