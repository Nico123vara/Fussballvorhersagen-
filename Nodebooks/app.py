import streamlit as st
import pandas as pd
import psycopg2
import pickle
import requests
from datetime import date, timedelta

API_KEY  = "0a51501f0bc740b39ac6633ef6e913d9"
BASE_URL = "https://api.football-data.org/v4"
HEADERS  = {"X-Auth-Token": API_KEY}

LIGEN = {
    'Bundesliga':     {'code': 'BL1', 'logo': 'https://crests.football-data.org/BL1.png'},
    'Premier League': {'code': 'PL',  'logo': 'https://crests.football-data.org/PL.png'},
    'Serie A':        {'code': 'SA',  'logo': 'https://crests.football-data.org/SA.png'},
}

st.set_page_config(page_title="Fussball Vorhersagen", page_icon="⚽", layout="wide")


@st.cache_resource
def get_connection():
    return psycopg2.connect(st.secrets["DATABASE_URL"])


@st.cache_data
def load_teams(liga_code):
    conn = get_connection()
    query = """
        SELECT DISTINCT t.id, t.name
        FROM teams t
        JOIN matches m ON (m.home_team_id = t.id OR m.away_team_id = t.id)
        JOIN competitions c ON m.competition_id = c.id
        WHERE c.code = %s ORDER BY t.name
    """
    return pd.read_sql(query, conn, params=(liga_code,))


@st.cache_data
def load_matches(liga_code):
    conn = get_connection()
    query = """
        SELECT m.id, m.utc_date, m.matchday, m.season_id,
               m.home_team_id, m.away_team_id,
               t1.name AS home_team, t2.name AS away_team,
               m.home_score_fulltime, m.away_score_fulltime,
               m.winner, m.status
        FROM matches m
        JOIN teams t1 ON m.home_team_id = t1.id
        JOIN teams t2 ON m.away_team_id = t2.id
        JOIN competitions c ON m.competition_id = c.id
        WHERE m.status = 'FINISHED' AND c.code = %s
        ORDER BY m.utc_date ASC
    """
    df = pd.read_sql(query, conn, params=(liga_code,))
    df['utc_date'] = pd.to_datetime(df['utc_date'])
    return df


@st.cache_data
def load_model(liga_code):
    with open(f'data/model_{liga_code}.pkl', 'rb') as f:
        return pickle.load(f)


@st.cache_data(ttl=3600)
def load_prediction_stats(liga_code):
    conn = get_connection()
    try:
        query = """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN p.predicted = m.winner THEN 1 ELSE 0 END) AS korrekt
            FROM predictions p
            JOIN matches m ON p.match_id = m.id
            JOIN competitions c ON m.competition_id = c.id
            WHERE m.status = 'FINISHED' AND c.code = %s
        """
        return pd.read_sql(query, conn, params=(liga_code,)).iloc[0]
    except:
        return None


@st.cache_data(ttl=3600)
def load_prediction_history(liga_code):
    conn = get_connection()
    try:
        query = """
            SELECT m.utc_date, t1.name AS home_team, t2.name AS away_team,
                   p.predicted, m.winner, p.predicted = m.winner AS korrekt
            FROM predictions p
            JOIN matches m ON p.match_id = m.id
            JOIN teams t1 ON m.home_team_id = t1.id
            JOIN teams t2 ON m.away_team_id = t2.id
            JOIN competitions c ON m.competition_id = c.id
            WHERE m.status = 'FINISHED' AND c.code = %s
            ORDER BY m.utc_date DESC
        """
        return pd.read_sql(query, conn, params=(liga_code,))
    except:
        return pd.DataFrame()


@st.cache_data(ttl=86400)
def load_upcoming_matches(liga_code):
    heute = date.today()
    resp  = requests.get(
        f"{BASE_URL}/competitions/{liga_code}/matches"
        f"?dateFrom={heute}&dateTo={heute + timedelta(days=28)}&status=SCHEDULED",
        headers=HEADERS
    )
    if resp.status_code != 200: return []
    return resp.json().get("matches", [])


# ─── Feature-Funktionen ───────────────────────────────────────────────────────
def get_prev_season_id(matches, season_id):
    season_ids = sorted(matches['season_id'].unique())
    idx = list(season_ids).index(season_id) if season_id in season_ids else -1
    return season_ids[idx - 1] if idx > 0 else season_id


def get_form(matches, team_id, season_id, n=5):
    prev_sid = get_prev_season_id(matches, season_id)
    spiele = matches[
        ((matches['home_team_id'] == team_id) | (matches['away_team_id'] == team_id)) &
        (matches['season_id'] >= prev_sid)
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


def get_home_form(matches, team_id, season_id, n=5):
    prev_sid = get_prev_season_id(matches, season_id)
    spiele = matches[(matches['home_team_id'] == team_id) & (matches['season_id'] >= prev_sid)].tail(n)
    punkte = 0
    for _, s in spiele.iterrows():
        if s['winner'] == 'HOME_TEAM': punkte += 3
        elif s['winner'] == 'DRAW': punkte += 1
    return punkte


def get_away_form(matches, team_id, season_id, n=5):
    prev_sid = get_prev_season_id(matches, season_id)
    spiele = matches[(matches['away_team_id'] == team_id) & (matches['season_id'] >= prev_sid)].tail(n)
    punkte = 0
    for _, s in spiele.iterrows():
        if s['winner'] == 'AWAY_TEAM': punkte += 3
        elif s['winner'] == 'DRAW': punkte += 1
    return punkte


def get_heimquote(matches, team_id, season_id, n=12):
    prev_sid = get_prev_season_id(matches, season_id)
    spiele = matches[(matches['home_team_id'] == team_id) & (matches['season_id'] >= prev_sid)].tail(n)
    if len(spiele) == 0: return 0.5
    return (spiele['winner'] == 'HOME_TEAM').mean()


def get_win_streak(matches, team_id, season_id):
    prev_sid = get_prev_season_id(matches, season_id)
    spiele = matches[
        ((matches['home_team_id'] == team_id) | (matches['away_team_id'] == team_id)) &
        (matches['season_id'] >= prev_sid)
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


def get_goal_diff(matches, team_id, season_id, n=5):
    prev_sid = get_prev_season_id(matches, season_id)
    spiele = matches[
        ((matches['home_team_id'] == team_id) | (matches['away_team_id'] == team_id)) &
        (matches['season_id'] >= prev_sid)
    ].tail(n)
    if len(spiele) == 0: return 0
    diff = 0
    for _, s in spiele.iterrows():
        if s['home_team_id'] == team_id:
            diff += s['home_score_fulltime'] - s['away_score_fulltime']
        else:
            diff += s['away_score_fulltime'] - s['home_score_fulltime']
    return diff / len(spiele)


def is_promoted(matches, team_id, season_id, matchday):
    if matchday > 5: return 0
    prev_sid = get_prev_season_id(matches, season_id)
    if prev_sid == season_id: return 0
    vorherige = matches[
        ((matches['home_team_id'] == team_id) | (matches['away_team_id'] == team_id)) &
        (matches['season_id'] == prev_sid)
    ]
    return 1 if len(vorherige) == 0 else 0


def get_table_position(matches, team_id, season_id, matchday):
    """Tabellenposition zum aktuellen Zeitpunkt. Aufsteiger → Platz 18."""
    if is_promoted(matches, team_id, season_id, matchday) == 1:
        return 18

    spiele = matches[matches['season_id'] == season_id]
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


def get_team_features(matches, team_id, season_id, matchday=99):
    return {
        'form':       get_form(matches, team_id, season_id),
        'form_home':  get_home_form(matches, team_id, season_id),
        'form_away':  get_away_form(matches, team_id, season_id),
        'heimquote':  get_heimquote(matches, team_id, season_id),
        'streak':     get_win_streak(matches, team_id, season_id),
        'goal_diff':  get_goal_diff(matches, team_id, season_id),
        'promoted':   is_promoted(matches, team_id, season_id, matchday),
        'table_pos':  get_table_position(matches, team_id, season_id, matchday)
    }


def make_prediction(matches, model_data, home_id, away_id, season_id, matchday=99):
    home_feat = get_team_features(matches, home_id, season_id, matchday)
    away_feat = get_team_features(matches, away_id, season_id, matchday)
    model     = model_data['model']
    features  = model_data['features']
    beispiel  = pd.DataFrame([{
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
        'is_promoted_away': away_feat['promoted'],
        'home_table_pos':   home_feat['table_pos'],
        'away_table_pos':   away_feat['table_pos']
    }])[features]
    probs     = model.predict_proba(beispiel)[0]
    klassen   = model.classes_
    label_map = {1: 'Heimsieg', 0: 'Unentschieden', -1: 'Auswärtssieg'}
    return {label_map[k]: p for k, p in zip(klassen, probs)}


# ─── UI ───────────────────────────────────────────────────────────────────────
def show_prob_bars(prob_dict):
    farben = {'Heimsieg': '#3fb950', 'Unentschieden': '#e3b341', 'Auswärtssieg': '#f85149'}
    beste  = max(prob_dict, key=prob_dict.get)
    for label, prob in sorted(prob_dict.items(), key=lambda x: -x[1]):
        ist_beste = label == beste
        st.markdown(
            f'<div style="margin:8px 0">'
            f'<div style="display:flex;justify-content:space-between;margin-bottom:4px">'
            f'<span style="color:{"#000000" if ist_beste else "#555555"};font-weight:{"700" if ist_beste else "400"}">{label}</span>'
            f'<span style="color:{farben[label]};font-weight:700">{prob*100:.1f}%</span>'
            f'</div>'
            f'<div style="background:#e0e0e0;border-radius:4px;height:8px">'
            f'<div style="background:{farben[label]};width:{prob*100:.1f}%;height:8px;border-radius:4px"></div>'
            f'</div></div>',
            unsafe_allow_html=True
        )
    return beste


def show_team_stats(matches, team_id, team_name, season_id):
    spiele = matches[
        (matches['home_team_id'] == team_id) | (matches['away_team_id'] == team_id)
    ].tail(10).sort_values('utc_date', ascending=False)

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("Punkte letzte 5", f"{get_form(matches, team_id, season_id)}/15")
    with col2: st.metric("Heimquote", f"{get_heimquote(matches, team_id, season_id)*100:.0f}%")
    with col3: st.metric("Siegesserie", get_win_streak(matches, team_id, season_id))
    with col4:
        gd = get_goal_diff(matches, team_id, season_id)
        st.metric("Ø Tordifferenz", f"{gd:+.1f}")
    with col5:
        pos = get_table_position(matches, team_id, season_id, 99)
        st.metric("Tabellenplatz", f"#{pos}")

    st.caption("Punkte letzte 5 — Sieg=3, Unentschieden=1, Niederlage=0. Maximum 15.")
    st.caption("Heimquote — Anteil Heimsiege aus letzten 12 Heimspielen.")
    st.caption("Siegesserie — Aufeinanderfolgende Siege bis zum letzten Spiel.")
    st.caption("Ø Tordifferenz — Durchschnitt letzte 5 Spiele. Positiv = mehr geschossen als kassiert.")
    st.caption("Tabellenplatz — Aktuelle Position in der Tabelle.")

    st.markdown("---")
    st.markdown("#### Letzte 10 Spiele")
    for _, s in spiele.iterrows():
        heim   = s['home_team'] == team_name
        gegner = s['away_team'] if heim else s['home_team']
        tore_f = s['home_score_fulltime'] if heim else s['away_score_fulltime']
        tore_g = s['away_score_fulltime'] if heim else s['home_score_fulltime']
        if s['winner'] == 'DRAW': result, color = "U", "#e3b341"
        elif (heim and s['winner'] == 'HOME_TEAM') or (not heim and s['winner'] == 'AWAY_TEAM'): result, color = "S", "#3fb950"
        else: result, color = "N", "#f85149"
        ort = "H" if heim else "A"
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:12px;padding:6px 0;border-bottom:1px solid #e0e0e0;">'
            f'<span style="color:#888888;font-size:0.8rem;width:80px">{s["utc_date"].strftime("%d.%m.%Y")}</span>'
            f'<span style="background:#f0f0f0;padding:2px 6px;border-radius:4px;font-size:0.75rem;color:#555555">{ort}</span>'
            f'<span style="flex:1;color:#111111">{gegner}</span>'
            f'<span style="color:#111111;font-weight:600">{int(tore_f)}:{int(tore_g)}</span>'
            f'<span style="background:{color};color:#ffffff;padding:2px 8px;border-radius:4px;font-weight:700;font-size:0.8rem">{result}</span>'
            f'</div>', unsafe_allow_html=True
        )


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    if 'liga' not in st.session_state:
        st.session_state.liga = 'Bundesliga'

    liga_cols = st.columns(len(LIGEN))
    for i, (liga_name, info) in enumerate(LIGEN.items()):
        with liga_cols[i]:
            label = f"✅ {liga_name}" if st.session_state.liga == liga_name else liga_name
            if st.button(label, key=f"btn_{liga_name}", use_container_width=True):
                st.session_state.liga = liga_name
                if 'away_team' in st.session_state:
                    del st.session_state['away_team']
                st.rerun()

    liga_name = st.session_state.liga
    liga_code = LIGEN[liga_name]['code']
    liga_logo = LIGEN[liga_name]['logo']

    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:16px;margin:1rem 0">
        <img src="{liga_logo}" width="50">
        <span style="font-size:2rem;font-weight:800;color:#111111">{liga_name} Vorhersagen</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")

    teams_df          = load_teams(liga_code)
    matches           = load_matches(liga_code)
    model_data        = load_model(liga_code)
    team_names        = teams_df['name'].tolist()
    current_season_id = matches['season_id'].max()

    if 'away_team' not in st.session_state or st.session_state.away_team not in team_names:
        st.session_state.away_team = team_names[1] if len(team_names) > 1 else team_names[0]

    col1, col2 = st.columns(2)
    with col1:
        home_team = st.selectbox("🏠 Heimteam", team_names, index=0)
    with col2:
        away_options = [t for t in team_names if t != home_team]
        idx = away_options.index(st.session_state.away_team) if st.session_state.away_team in away_options else 0
        away_team = st.selectbox("✈️ Auswärtsteam", away_options, index=idx, key='away_team')

    home_id = teams_df[teams_df['name'] == home_team]['id'].values[0]
    away_id = teams_df[teams_df['name'] == away_team]['id'].values[0]

    tab1, tab2, tab3 = st.tabs(["📊 Vorhersage", "📅 Nächste 4 Wochen", "🎯 Meine Genauigkeit"])

    with tab1:
        st.markdown(f"#### {home_team} vs {away_team}")
        prob_dict = make_prediction(matches, model_data, home_id, away_id, current_season_id)
        beste = show_prob_bars(prob_dict)
        st.markdown("---")
        st.markdown(f"**Vorhersage: {beste}**")

        st.markdown("#### Teamvergleich")
        home_feat = get_team_features(matches, home_id, current_season_id)
        away_feat = get_team_features(matches, away_id, current_season_id)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Punkte letzte 5", f"{home_feat['form']}/15")
            st.metric("Heimquote", f"{home_feat['heimquote']*100:.0f}%")
            st.metric("Ø Tordifferenz", f"{home_feat['goal_diff']:+.1f}")
            st.metric("Tabellenplatz", f"#{home_feat['table_pos']}")
        with c2:
            st.markdown("<div style='text-align:center;color:#888888;padding-top:24px'>vs</div>", unsafe_allow_html=True)
        with c3:
            st.metric("Punkte letzte 5", f"{away_feat['form']}/15")
            st.metric("Auswärtsform letzte 5", f"{away_feat['form_away']}/15")
            st.metric("Ø Tordifferenz", f"{away_feat['goal_diff']:+.1f}")
            st.metric("Tabellenplatz", f"#{away_feat['table_pos']}")

        st.caption("Punkte letzte 5 — Sieg=3, Unentschieden=1, Niederlage=0. Maximum 15.")
        st.caption("Heimquote — Anteil Heimsiege des Heimteams aus letzten 12 Heimspielen.")
        st.caption("Auswärtsform — Punkte des Auswärtsteams aus letzten 5 Auswärtsspielen.")
        st.caption("Ø Tordifferenz — Durchschnitt letzte 5 Spiele. Positiv = mehr geschossen als kassiert.")
        st.caption("Tabellenplatz — Aktuelle Position in der Tabelle.")

        st.markdown("---")
        st.markdown("#### Teamstatistiken")
        subtab1, subtab2 = st.tabs([f"🏠 {home_team}", f"✈️ {away_team}"])
        with subtab1:
            show_team_stats(matches, home_id, home_team, current_season_id)
        with subtab2:
            show_team_stats(matches, away_id, away_team, current_season_id)

    with tab2:
        st.markdown(f"### Spiele der nächsten 4 Wochen — {liga_name}")
        upcoming = load_upcoming_matches(liga_code)
        if not upcoming:
            st.info("Keine Spiele in den nächsten 4 Wochen — wahrscheinlich Pause. 🌴")
        else:
            for m in upcoming:
                home_name = m['homeTeam']['name']
                away_name = m['awayTeam']['name']
                datum     = m['utcDate'][:10]
                uhrzeit   = m['utcDate'][11:16]
                home_row  = teams_df[teams_df['name'] == home_name]
                away_row  = teams_df[teams_df['name'] == away_name]
                col_date, col_match, col_pred = st.columns([1, 2, 2])
                with col_date:
                    st.markdown(f"**{datum}**")
                    st.caption(f"{uhrzeit} Uhr")
                with col_match:
                    st.markdown(f"**{home_name}** vs **{away_name}**")
                    st.caption(f"Spieltag {m.get('matchday', '?')}")
                with col_pred:
                    if not home_row.empty and not away_row.empty:
                        current_matchday = int(matches['matchday'].max())
                        prob_dict = make_prediction(
                            matches, model_data,
                            home_row['id'].values[0], away_row['id'].values[0],
                            current_season_id, current_matchday
                        )
                        beste = max(prob_dict, key=prob_dict.get)
                        farbe = {'Heimsieg': '#3fb950', 'Unentschieden': '#e3b341', 'Auswärtssieg': '#f85149'}[beste]
                        st.markdown(
                            f'<span style="background:{farbe};color:#ffffff;padding:4px 12px;border-radius:6px;font-weight:700">{beste}</span>'
                            f' <span style="color:#888888">{prob_dict[beste]*100:.0f}%</span>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.caption("Keine Daten verfügbar")
                st.markdown("---")

    with tab3:
        st.markdown(f"### 🎯 Meine Genauigkeit — {liga_name}")
        stats = load_prediction_stats(liga_code)
        if stats is None or stats['total'] == 0:
            st.info("Noch keine abgeschlossenen Spiele mit Vorhersagen.")
        else:
            total       = int(stats['total'])
            korrekt     = int(stats['korrekt'])
            genauigkeit = korrekt / total * 100
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("Korrekte Vorhersagen", f"{korrekt}/{total}")
            with col2: st.metric("Genauigkeit", f"{genauigkeit:.1f}%")
            with col3: st.metric("Baseline (immer Heimsieg)", "~43%")
            st.markdown("---")
            history = load_prediction_history(liga_code)
            if not history.empty:
                label_map = {'HOME_TEAM': 'Heimsieg', 'DRAW': 'Unentschieden', 'AWAY_TEAM': 'Auswärtssieg'}
                for _, row in history.iterrows():
                    korrekt_icon = "✅" if row['korrekt'] else "❌"
                    pred_label   = label_map.get(row['predicted'], row['predicted'])
                    echt_label   = label_map.get(row['winner'], row['winner'])
                    datum        = pd.to_datetime(row['utc_date']).strftime('%d.%m.%Y')
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:12px;padding:6px 0;border-bottom:1px solid #e0e0e0;">'
                        f'<span style="color:#888888;font-size:0.8rem;width:80px">{datum}</span>'
                        f'<span style="flex:1;color:#111111">{row["home_team"]} vs {row["away_team"]}</span>'
                        f'<span style="color:#555555">Tipp: <b>{pred_label}</b></span>'
                        f'<span style="color:#555555;margin-left:12px">Echt: <b>{echt_label}</b></span>'
                        f'<span style="font-size:1.2rem;margin-left:12px">{korrekt_icon}</span>'
                        f'</div>', unsafe_allow_html=True
                    )


if __name__ == "__main__":
    main()
