import pandas as pd
import psycopg2
import pickle
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

# ─── Konfiguration ───────────────────────────────────────────────────────────
DB_CONFIG = {
    'host':     'localhost',
    'port':     5432,
    'dbname':   'fussball',
    'user':     'fussball',
    'password': 'fussball_pw'
}

FEATURES = [
    'home_form', 'away_form',
    'home_form_home', 'away_form_away',
    'heimquote', 'home_streak', 'away_streak',
    'home_goal_diff', 'away_goal_diff',
    'is_promoted_home', 'is_promoted_away'
]


# ─── Daten laden ─────────────────────────────────────────────────────────────
def load_data():
    print("Lade Daten aus DB...")
    conn = psycopg2.connect(**DB_CONFIG)
    query = """
        SELECT
            m.id,
            m.utc_date,
            m.matchday,
            m.season_id,
            s.start_date AS season_start,
            m.home_team_id,
            m.away_team_id,
            m.home_score_fulltime,
            m.away_score_fulltime,
            m.winner
        FROM matches m
        JOIN seasons s ON m.season_id = s.id
        WHERE m.status = 'FINISHED'
        ORDER BY m.utc_date ASC
    """
    df = pd.read_sql(query, conn)
    conn.close()
    df['utc_date']     = pd.to_datetime(df['utc_date'])
    df['season_start'] = pd.to_datetime(df['season_start'])
    df['season']       = df['season_start'].dt.year
    print(f"  {len(df)} Spiele geladen")
    return df


# ─── Vorsaison Mapping ───────────────────────────────────────────────────────
def build_prev_season_map(df):
    season_ids = sorted(df['season_id'].unique())
    prev_season_map = {}
    for i, sid in enumerate(season_ids):
        prev_season_map[sid] = season_ids[i - 1] if i > 0 else sid
    return prev_season_map


# ─── Feature-Funktionen ───────────────────────────────────────────────────────
def get_form(df, team_id, date, season_id, prev_map, n=5):
    prev_sid = prev_map.get(season_id, season_id)
    spiele = df[
        ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
        (df['utc_date'] < date) &
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


def get_home_form(df, team_id, date, season_id, prev_map, n=5):
    prev_sid = prev_map.get(season_id, season_id)
    spiele = df[
        (df['home_team_id'] == team_id) &
        (df['utc_date'] < date) &
        (df['season_id'] >= prev_sid)
    ].tail(n)
    punkte = 0
    for _, s in spiele.iterrows():
        if s['winner'] == 'HOME_TEAM': punkte += 3
        elif s['winner'] == 'DRAW': punkte += 1
    return punkte


def get_away_form(df, team_id, date, season_id, prev_map, n=5):
    prev_sid = prev_map.get(season_id, season_id)
    spiele = df[
        (df['away_team_id'] == team_id) &
        (df['utc_date'] < date) &
        (df['season_id'] >= prev_sid)
    ].tail(n)
    punkte = 0
    for _, s in spiele.iterrows():
        if s['winner'] == 'AWAY_TEAM': punkte += 3
        elif s['winner'] == 'DRAW': punkte += 1
    return punkte


def get_heimquote(df, team_id, date, season_id, prev_map, n=12):
    prev_sid = prev_map.get(season_id, season_id)
    spiele = df[
        (df['home_team_id'] == team_id) &
        (df['utc_date'] < date) &
        (df['season_id'] >= prev_sid)
    ].tail(n)
    if len(spiele) == 0:
        return 0.5
    return (spiele['winner'] == 'HOME_TEAM').mean()


def get_win_streak(df, team_id, date, season_id, prev_map):
    prev_sid = prev_map.get(season_id, season_id)
    spiele = df[
        ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
        (df['utc_date'] < date) &
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


def get_goal_diff(df, team_id, date, season_id, prev_map, n=5):
    prev_sid = prev_map.get(season_id, season_id)
    spiele = df[
        ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
        (df['utc_date'] < date) &
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


def is_promoted(df, team_id, season_id, matchday, prev_map):
    if matchday > 5:
        return 0
    prev_sid = prev_map.get(season_id, season_id)
    if prev_sid == season_id:
        return 0
    vorherige = df[
        ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
        (df['season_id'] == prev_sid)
    ]
    return 1 if len(vorherige) == 0 else 0


# ─── Feature Engineering ─────────────────────────────────────────────────────
def compute_features(df):
    print("Berechne Features...")
    prev_map = build_prev_season_map(df)
    features = []

    for i, (_, row) in enumerate(df.iterrows()):
        if i % 100 == 0:
            print(f"  {i}/{len(df)} verarbeitet...")

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
            'winner':           row['winner']
        })

    df_features = pd.DataFrame(features)
    print(f"  {len(df_features)} Spiele total")
    return df_features


# ─── Bereinigung ─────────────────────────────────────────────────────────────
def clean_features(df_features):
    print("Bereinige Features...")
    vorher = len(df_features)

    df_features = df_features[df_features['season'] >= 2024]
    df_features = df_features[
        ~((df_features['home_form'] == 0) & (df_features['away_form'] == 0))
    ]
    df_features = df_features[
        ~((df_features['home_form_home'] == 0) & (df_features['away_form_away'] == 0))
    ]

    print(f"  {vorher} → {len(df_features)} Spiele nach Bereinigung")
    return df_features


# ─── Model Training ──────────────────────────────────────────────────────────
def train_model(df_features):
    print("Trainiere Modell...")

    label_map = {'HOME_TEAM': 1, 'DRAW': 0, 'AWAY_TEAM': -1}
    df_features['target'] = df_features['winner'].map(label_map)
    df_features = df_features.dropna(subset=FEATURES + ['target'])

    # Train/Test Split
    train = df_features[
        (df_features['season'] == 2024) |
        ((df_features['season'] == 2025) & (df_features['matchday'] <= 17))
    ]
    test = df_features[
        (df_features['season'] == 2025) & (df_features['matchday'] > 17)
    ]

    X_train = train[FEATURES]
    y_train = train['target']
    X_test  = test[FEATURES]
    y_test  = test['target']

    print(f"  Training: {len(train)} Spiele | Test: {len(test)} Spiele")

    # Baseline
    baseline = accuracy_score(y_test, [1] * len(y_test))
    print(f"  Baseline: {baseline*100:.1f}%")

    # Logistische Regression
    lr = LogisticRegression(max_iter=1000, random_state=42)
    lr.fit(X_train, y_train)
    lr_acc = accuracy_score(y_test, lr.predict(X_test))
    print(f"  Logistische Regression: {lr_acc*100:.1f}%")

    # Random Forest
    rf = RandomForestClassifier(n_estimators=100, random_state=42)
    rf.fit(X_train, y_train)
    rf_acc = accuracy_score(y_test, rf.predict(X_test))
    print(f"  Random Forest: {rf_acc*100:.1f}%")

    # Bestes Modell wählen
    best_model = rf if rf_acc >= lr_acc else lr
    best_acc   = max(rf_acc, lr_acc)
    best_name  = 'Random Forest' if rf_acc >= lr_acc else 'Logistische Regression'

    print(f"\n  Bestes Modell: {best_name} ({best_acc*100:.1f}%)")
    return best_model


# ─── Modell speichern ────────────────────────────────────────────────────────
def save_model(model):
    model_data = {
        'model':    model,
        'features': FEATURES
    }
    with open('data/model.pkl', 'wb') as f:
        pickle.dump(model_data, f)
    print("Modell gespeichert: data/model.pkl")


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    print("=== Retrain — Feature Engineering + Model Training ===\n")

    df          = load_data()
    df_features = compute_features(df)
    df_features = clean_features(df_features)
    model       = train_model(df_features)
    save_model(model)

    print("\nFertig! Modell ist aktuell.")


if __name__ == "__main__":
    main()
