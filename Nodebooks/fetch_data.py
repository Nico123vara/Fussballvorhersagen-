import os
import json
import requests

# ---- Konfiguration ----
API_KEY = "0a51501f0bc740b39ac6633ef6e913d9"   # dein Key von football-data.org
BASE_URL = "https://api.football-data.org/v4"
COMPETITION = "BL1"   # Bundesliga. Andere Codes: PL, SA, FL1, PD, CL, DED ...

HEADERS = {"X-Auth-Token": API_KEY}

# Ordner, in dem die JSON-Dateien gespeichert werden
OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_and_save(endpoint: str, filename: str):
    """Holt Daten von einem Endpunkt und speichert sie als JSON-Datei."""
    url = f"{BASE_URL}/{endpoint}"
    print(f"Hole Daten von: {url}")

    response = requests.get(url, headers=HEADERS)

    if response.status_code != 200:
        print(f"  Fehler: Status {response.status_code} -> {response.text}")
        return

    data = response.json()

    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  Gespeichert unter: {filepath}")


def main():
    # 1. Teams der Liga
    fetch_and_save(f"competitions/{COMPETITION}/teams", "teams_bl1.json")

    # 2. Alle Spiele der aktuellen Saison
    fetch_and_save(f"competitions/{COMPETITION}/matches", "matches_bl1.json")

    # 3. Aktuelle Tabelle
    fetch_and_save(f"competitions/{COMPETITION}/standings", "standings_bl1.json")

    print("\nFertig! Alle Dateien liegen im Ordner 'data/'.")


if __name__ == "__main__":
    main()
