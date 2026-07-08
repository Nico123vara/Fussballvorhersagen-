import streamlit as st
import pandas as pd
import psycopg2
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

st.set_page_config(
    page_title="Bundesliga Vorhersagen",
    page_icon="⚽",
    layout="wide"
)

# ─── Styling ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0d1117; }
    .block-container { padding-top: 2rem; }
    .team-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }
    h1 { color: #f0f6fc !important; }
    h2 { color: #c9d1d9 !important; }
    h3 { color: #8b949e !important; }
    .stSelectbox label { color: #8b949e !important; }
    .stTabs [data-baseweb="tab"] { color: #8b949e; }
    .stTabs [aria-selected="true"] { color: #58a6ff !important; border-bottom-color: #58a6ff !important; }
</style>
""", unsafe_allow_html=True)


# ─── Datenbankverbindung ──────────────────────────────────────────────────────
@st.cache_resource
def get_connection():
    return psycopg2.connect(**DB_CONFIG)


@st.cache_data
def load_teams():
    conn = get_connection()
    query = """
        SELECT DISTINCT t.id, t.name
        FROM teams t
        JOIN matches m ON (m.home_team_id = t.id OR m.away_team_id = t.id)
        JOIN seasons s ON m.season_id = s.id
        WHERE s.start_date = (SELECT MAX(start_date) FROM seasons)
        ORDER BY t.name
    """
    return pd.read_sql(query, conn)


@st.cache_data
def load_matches():
    conn = get_connection()
    query = """
        SELECT
            m.id, m.utc_date, m.matchday, m.season_id,
            m.home_team_id, m.away_team_id,
            t1.name AS home_team, t2.name AS away_team,
            m.home_score_fulltime, m.away_score_fulltime,
            m.winner, m.status
        FROM matches m
        JOIN teams t1 ON m.home_team_id = t1.id
        JOIN teams t2 ON m.away_team_id = t2.id
        WHERE m.status = 'FINISHED'
        ORDER BY m.utc_date ASC
    """
    df = pd.read_sql(query, conn)
    df['utc_date'] = pd.to_datetime(df['utc_date'])
    return df


@st.cache_data
def load_models():
    with open('data/model_promoted.pkl', 'rb') as f:
        model_a = pickle.load(f)
    with open('data/model_no_promoted.pkl', 'rb') as f:
        model_b = pickle.load(f)
    return model_a, model_b


@st.cache_data(ttl=3600)
def load_upcoming_matches():
    """Holt alle Spiele der nächsten 7 Tage von der API."""
    heute          = date.today()
    naechste_woche = heute + timedelta(days=7)
    resp = requests.get(
        f"{BASE_URL}/competitions/BL1/matches"
        f"?dateFrom={heute}&dateTo={naechste_woche}&status=SCHEDULED",
        headers=HEADERS
    )
    if resp.status_code != 200:
        return []
    return resp.json().get("matches", [])


# ─── Feature-Funktionen ───────────────────────────────────────────────────────
def get_form(df, team_id, n=5):
    spiele = df[
        (df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)
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


def get_home_form(df, team_id, n=5):
    spiele = df[df['home_team_id'] == team_id].tail(n)
    punkte = 0
    for _, s in spiele.iterrows():
        if s['winner'] == 'HOME_TEAM': punkte += 3
        elif s['winner'] == 'DRAW': punkte += 1
    return punkte


def get_away_form(df, team_id, n=5):
    spiele = df[df['away_team_id'] == team_id].tail(n)
    punkte = 0
    for _, s in spiele.iterrows():
        if s['winner'] == 'AWAY_TEAM': punkte += 3
        elif s['winner'] == 'DRAW': punkte += 1
    return punkte


def get_heimquote(df, team_id, n=12):
    spiele = df[df['home_team_id'] == team_id].tail(n)
    if len(spiele) == 0:
        return 0.5
    return (spiele['winner'] == 'HOME_TEAM').mean()


def get_win_streak(df, team_id):
    spiele = df[
        (df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)
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


def get_goal_diff(df, team_id, n=5):
    spiele = df[
        (df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)
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


def is_promoted(df, team_id, current_season_id):
    vorherige = df[
        ((df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)) &
        (df['season_id'] < current_season_id)
    ]
    return 1 if len(vorherige) == 0 else 0


def get_team_features(df, team_id, current_season_id):
    return {
        'form':      get_form(df, team_id),
        'form_home': get_home_form(df, team_id),
        'form_away': get_away_form(df, team_id),
        'heimquote': get_heimquote(df, team_id),
        'streak':    get_win_streak(df, team_id),
        'goal_diff': get_goal_diff(df, team_id),
        'promoted':  is_promoted(df, team_id, current_season_id)
    }


def make_prediction(matches, teams_df, model_a, model_b, home_id, away_id, current_season_id):
    home_feat = get_team_features(matches, home_id, current_season_id)
    away_feat = get_team_features(matches, away_id, current_season_id)

    if home_feat['promoted'] == 1 or away_feat['promoted'] == 1:
        model_data  = model_a
        modell_name = "Modell mit Aufsteiger"
    else:
        model_data  = model_b
        modell_name = "Standardmodell"

    model    = model_data['model']
    features = model_data['features']

    beispiel = pd.DataFrame([{
        'home_form':        home_feat['form'],
        'away_form':        away_feat['form'],
        'home_form_home':   home_feat['form_home'],
        'away_form_away':   away_feat['form_away'],
        'heimquote':        home_feat['heimquote'],
        'home_streak':      home_feat['streak'],
        'away_streak':      away_feat['streak'],
        'home_goal_diff':   home_feat['goal_diff'],
        'away_goal_diff':   away_feat['goal_diff'],
        'is_promoted_home': home_feat['promoted'],
        'is_promoted_away': away_feat['promoted']
    }])[features]

    probs   = model.predict_proba(beispiel)[0]
    klassen = model.classes_
    label_map = {1: 'Heimsieg', 0: 'Unentschieden', -1: 'Auswärtssieg'}
    prob_dict = {label_map[k]: p for k, p in zip(klassen, probs)}
    return prob_dict, modell_name


# ─── Statistik-Komponenten ────────────────────────────────────────────────────
def show_team_stats(df, team_id, team_name):
    spiele = df[
        (df['home_team_id'] == team_id) | (df['away_team_id'] == team_id)
    ].tail(10).sort_values('utc_date', ascending=False)

    st.markdown(f"### {team_name}")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Form (letzte 5)", f"{get_form(df, team_id)}/15")
    with col2:
        st.metric("Heimquote", f"{get_heimquote(df, team_id)*100:.0f}%")
    with col3:
        st.metric("Siegesserie", get_win_streak(df, team_id))
    with col4:
        gd = get_goal_diff(df, team_id)
        st.metric("Ø Tordifferenz", f"{gd:+.1f}")

    st.markdown("#### Letzte 10 Spiele")
    for _, s in spiele.iterrows():
        heim   = s['home_team'] == team_name
        gegner = s['away_team'] if heim else s['home_team']
        tore_f = s['home_score_fulltime'] if heim else s['away_score_fulltime']
        tore_g = s['away_score_fulltime'] if heim else s['home_score_fulltime']

        if s['winner'] == 'DRAW':
            result, color = "U", "#e3b341"
        elif (heim and s['winner'] == 'HOME_TEAM') or (not heim and s['winner'] == 'AWAY_TEAM'):
            result, color = "S", "#3fb950"
        else:
            result, color = "N", "#f85149"

        ort = "H" if heim else "A"
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:12px;padding:6px 0;'
            f'border-bottom:1px solid #21262d;">'
            f'<span style="color:#8b949e;font-size:0.8rem;width:80px">'
            f'{s["utc_date"].strftime("%d.%m.%Y")}</span>'
            f'<span style="background:#21262d;padding:2px 6px;border-radius:4px;'
            f'font-size:0.75rem;color:#8b949e">{ort}</span>'
            f'<span style="flex:1;color:#c9d1d9">{gegner}</span>'
            f'<span style="color:#c9d1d9;font-weight:600">{int(tore_f)}:{int(tore_g)}</span>'
            f'<span style="background:{color};color:#0d1117;padding:2px 8px;'
            f'border-radius:4px;font-weight:700;font-size:0.8rem">{result}</span>'
            f'</div>',
            unsafe_allow_html=True
        )


def show_prob_bars(prob_dict):
    farben = {
        'Heimsieg':      '#3fb950',
        'Unentschieden': '#e3b341',
        'Auswärtssieg':  '#f85149'
    }
    beste = max(prob_dict, key=prob_dict.get)
    for label, prob in sorted(prob_dict.items(), key=lambda x: -x[1]):
        ist_beste = label == beste
        st.markdown(
            f'<div style="margin:8px 0">'
            f'<div style="display:flex;justify-content:space-between;margin-bottom:4px">'
            f'<span style="color:{"#f0f6fc" if ist_beste else "#8b949e"};'
            f'font-weight:{"700" if ist_beste else "400"}">{label}</span>'
            f'<span style="color:{farben[label]};font-weight:700">{prob*100:.1f}%</span>'
            f'</div>'
            f'<div style="background:#21262d;border-radius:4px;height:8px">'
            f'<div style="background:{farben[label]};width:{prob*100:.1f}%;'
            f'height:8px;border-radius:4px"></div>'
            f'</div></div>',
            unsafe_allow_html=True
        )
    return beste


# ─── Hauptapp ────────────────────────────────────────────────────────────────
def main():
    st.title("⚽ Bundesliga Vorhersagen")
    st.markdown("---")

    teams_df         = load_teams()
    matches          = load_matches()
    model_a, model_b = load_models()
    team_names       = teams_df['name'].tolist()
    current_season_id = matches['season_id'].max()

    # Team-Auswahl
    col1, col2 = st.columns(2)
    with col1:
        home_team = st.selectbox("🏠 Heimteam", team_names, index=0)
    with col2:
        away_options = [t for t in team_names if t != home_team]
        away_team = st.selectbox("✈️ Auswärtsteam", away_options, index=0)

    home_id = teams_df[teams_df['name'] == home_team]['id'].values[0]
    away_id = teams_df[teams_df['name'] == away_team]['id'].values[0]

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Vorhersage",
        f"🏠 {home_team}",
        f"✈️ {away_team}",
        "📅 Nächste Woche"
    ])

    # ── Tab 1: Vorhersage ──
    with tab1:
        st.markdown(f"#### {home_team} vs {away_team}")
        prob_dict, modell_name = make_prediction(
            matches, teams_df, model_a, model_b,
            home_id, away_id, current_season_id
        )
        st.caption(f"Modell: {modell_name}")
        beste = show_prob_bars(prob_dict)
        st.markdown("---")
        st.markdown(f"**Vorhersage: {beste}**")

        st.markdown("#### Teamvergleich")
        home_feat = get_team_features(matches, home_id, current_season_id)
        away_feat = get_team_features(matches, away_id, current_season_id)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Form", f"{home_feat['form']}/15")
            st.metric("Heimquote", f"{home_feat['heimquote']*100:.0f}%")
            st.metric("Ø Tordifferenz", f"{home_feat['goal_diff']:+.1f}")
        with c2:
            st.markdown("<div style='text-align:center;color:#8b949e;padding-top:24px'>vs</div>",
                       unsafe_allow_html=True)
        with c3:
            st.metric("Form", f"{away_feat['form']}/15")
            st.metric("Auswärtsquote", f"{get_away_form(matches, away_id)/15*100:.0f}%")
            st.metric("Ø Tordifferenz", f"{away_feat['goal_diff']:+.1f}")

    # ── Tab 2: Heimteam Stats ──
    with tab2:
        show_team_stats(matches, home_id, home_team)

    # ── Tab 3: Auswärtsteam Stats ──
    with tab3:
        show_team_stats(matches, away_id, away_team)

    # ── Tab 4: Nächste Woche ──
    with tab4:
        st.markdown("### Spiele der nächsten 7 Tage")
        upcoming = load_upcoming_matches()

        if not upcoming:
            st.info("Keine Spiele in den nächsten 7 Tagen — wahrscheinlich Sommerpause. 🌴")
            st.caption("Sobald die Saison startet, werden hier alle kommenden Spiele mit Vorhersagen angezeigt.")
        else:
            for m in upcoming:
                home_name = m['homeTeam']['name']
                away_name = m['awayTeam']['name']
                datum     = m['utcDate'][:10]
                uhrzeit   = m['utcDate'][11:16]

                # Team IDs aus DB holen
                home_row = teams_df[teams_df['name'] == home_name]
                away_row = teams_df[teams_df['name'] == away_name]

                with st.container():
                    col_date, col_match, col_pred = st.columns([1, 2, 2])

                    with col_date:
                        st.markdown(f"**{datum}**")
                        st.caption(f"{uhrzeit} Uhr")

                    with col_match:
                        st.markdown(f"**{home_name}** vs **{away_name}**")
                        st.caption(f"Spieltag {m.get('matchday', '?')}")

                    with col_pred:
                        if not home_row.empty and not away_row.empty:
                            prob_dict, _ = make_prediction(
                                matches, teams_df, model_a, model_b,
                                home_row['id'].values[0],
                                away_row['id'].values[0],
                                current_season_id
                            )
                            beste = max(prob_dict, key=prob_dict.get)
                            farbe = {'Heimsieg': '#3fb950', 'Unentschieden': '#e3b341', 'Auswärtssieg': '#f85149'}[beste]
                            st.markdown(
                                f'<span style="background:{farbe};color:#0d1117;padding:4px 12px;'
                                f'border-radius:6px;font-weight:700">{beste}</span>'
                                f' <span style="color:#8b949e">{prob_dict[beste]*100:.0f}%</span>',
                                unsafe_allow_html=True
                            )
                        else:
                            st.caption("Keine Daten verfügbar")

                st.markdown("---")


if __name__ == "__main__":
    main()
