import os
import json
import time
import requests

# ---- Konfiguration ----
API_KEY     = "0a51501f0bc740b39ac6633ef6e913d9"
BASE_URL    = "https://api.football-data.org/v4"
COMPETITION = "BL1"
HEADERS     = {"X-Auth-Token": API_KEY}

SEASONS    = [2021, 2022, 2023, 2024, 2025]
OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def fetch_and_save(endpoint: str, filename: str):
    url  = f"{BASE_URL}/{endpoint}"
    print(f"  Hole: {url}")
    resp = requests.get(url, headers=HEADERS)

    if resp.status_code != 200:
        print(f"  Fehler: {resp.status_code} -> {resp.text}")
        return

    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(resp.json(), f, ensure_ascii=False, indent=2)
    print(f"  Gespeichert: {filepath}")


def main():
    for season in SEASONS:
        print(f"\n--- Saison {season}/{str(season+1)[-2:]} ---")

        # Teams dieser Saison (wichtig: jede Saison hat andere Teams!)
        fetch_and_save(
            f"competitions/{COMPETITION}/teams?season={season}",
            f"teams_bl1_{season}.json"
        )
        time.sleep(6)

        # Spiele dieser Saison
        fetch_and_save(
            f"competitions/{COMPETITION}/matches?season={season}",
            f"matches_bl1_{season}.json"
        )
        time.sleep(6)

    print("\nFertig! Alle Dateien liegen im Ordner 'data/'.")


if __name__ == "__main__":
    main()
