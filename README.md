# ⚽ Fussball Vorhersagen

Machine Learning App zur Vorhersage von Spielergebnissen in der Bundesliga, Premier League und Serie A.

## 🔗 Live App

[fussballvorhersagen.streamlit.app](https://fussballvorhersagen.streamlit.app)

## 📊 Was die App kann

- **Vorhersage** — Wahrscheinlichkeiten für Heimsieg, Unentschieden oder Auswärtssieg
- **Teamvergleich** — Form, Heimquote, Tordifferenz und Tabellenplatz
- **Nächste 4 Wochen** — Alle kommenden Spiele mit Vorhersagen
- **Meine Genauigkeit** — Tracking wie gut das Modell wirklich ist

## 🏆 Ligen

- 🇩🇪 Bundesliga
- 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
- 🇮🇹 Serie A

## 🤖 Machine Learning

**Features (13):**
- Form letzte 5 Spiele (gesamt, Heim, Auswärts)
- Heimquote (letzte 12 Heimspiele)
- Siegesserie
- Ø Tordifferenz (letzte 5 Spiele)
- Aufsteiger-Status (erste 5 Spieltage)
- Tabellenplatz

**Modelle:**
- Logistische Regression
- Random Forest
- Bestes Modell wird automatisch gewählt (~51-53% Genauigkeit)

## 🛠️ Tech Stack

| Komponente | Technologie |
|---|---|
| App | Streamlit |
| Datenbank | PostgreSQL (Railway) |
| ML | scikit-learn |
| Daten | football-data.org API |
| Deployment | Streamlit Cloud |
| CI/CD | GitHub Actions |

## 📁 Projektstruktur

```
Nodebooks/
  app.py                 # Streamlit App
  retrain.py             # Feature Engineering + Model Training
  monthly_update.py      # Neue Spiele laden
  save_predictions.py    # Vorhersagen speichern
  update.py              # Orchestrierung mit Logging
  fetch_data.py          # API → JSON
  load_data.py           # JSON → DB
  create_models_table.py # Models Tabelle erstellen
  requirements.txt       # Dependencies
  data/                  # Lokale Daten (nicht auf GitHub)
  logs/                  # Log Files (nicht auf GitHub)

.github/
  workflows/
    weekly_update.yml    # Automatisches Update jeden Montag
```

## 🔄 Automatisches Update

Jeden Montag 08:00 UTC via GitHub Actions:
1. Neue Spielergebnisse laden
2. Modelle neu trainieren
3. Vorhersagen für nächsten Spieltag speichern

## 🚀 Lokal starten

```bash
# Dependencies installieren
uv sync

# DB URL setzen
$env:DATABASE_URL = "deine-railway-url"

# App starten
uv run python -m streamlit run app.py
```

## 📈 Genauigkeit

Baseline (immer Heimsieg): ~43%  
Unser Modell: ~51-53%

Die echte Genauigkeit wird ab Saison 2026/27 in Tab 3 der App getrackt.
